const DEFAULT_BASE_URL = 'https://api.openai.com/v1';
const DEFAULT_MAX_TOKENS = 16_384;
const DEFAULT_TIMEOUT_MS = 600_000;
const DEFAULT_MAX_RETRIES = 1;
const DEFAULT_RETRY_DELAY_MS = 500;

const RETRYABLE_STATUS_CODES = new Set([408, 429]);

function required(value, name) {
  if (typeof value !== 'string' || value.trim() === '') throw new Error(`${name} is required`);
  return value.trim();
}

function positiveInteger(value, name) {
  const number = Number(value);
  if (!Number.isSafeInteger(number) || number <= 0) throw new Error(`${name} must be a positive integer`);
  return number;
}

function nonNegativeInteger(value, name) {
  const number = Number(value);
  if (!Number.isSafeInteger(number) || number < 0) {
    throw new Error(`${name} must be a non-negative integer`);
  }
  return number;
}

function clientError(message, options = {}) {
  const error = new Error(message, options.cause ? { cause: options.cause } : undefined);
  error.code = options.code;
  error.status = options.status;
  error.retryable = options.retryable ?? false;
  return error;
}

function networkError(error) {
  const cancelled = error?.name === 'AbortError';
  return clientError(`OpenAI-compatible request failed: ${error?.message ?? 'network error'}`, {
    cause: error,
    code: error?.code ?? error?.cause?.code,
    retryable: !cancelled,
  });
}

function parseJSONCompletion(text, status) {
  let payload;
  try {
    payload = JSON.parse(text);
  } catch {
    throw clientError(`OpenAI-compatible endpoint returned non-JSON content (HTTP ${status})`);
  }
  const content = payload?.choices?.[0]?.message?.content;
  if (typeof content !== 'string' || content.trim() === '') {
    throw clientError('OpenAI-compatible response is missing choices[0].message.content');
  }
  return content.trim();
}

function parseSSEEvent(eventText) {
  const data = eventText
    .split(/\r?\n/)
    .filter(line => line.startsWith('data:'))
    .map(line => line.slice(5).trimStart())
    .join('\n');
  if (!data) return { content: '', completed: false };
  if (data === '[DONE]') return { content: '', completed: true };
  let payload;
  try {
    payload = JSON.parse(data);
  } catch (error) {
    throw clientError('OpenAI-compatible endpoint returned an invalid SSE event', {
      cause: error,
      retryable: true,
    });
  }
  return {
    content: typeof payload?.choices?.[0]?.delta?.content === 'string'
      ? payload.choices[0].delta.content
      : '',
    completed: payload?.choices?.[0]?.finish_reason != null,
  };
}

async function parseStream(response) {
  if (!response.body) throw clientError('Streaming response is missing a body', { retryable: true });
  const decoder = new TextDecoder();
  let buffer = '';
  let content = '';
  let completed = false;
  try {
    for await (const chunk of response.body) {
      buffer += decoder.decode(chunk, { stream: true });
      const events = buffer.split(/\r?\n\r?\n/);
      buffer = events.pop() ?? '';
      for (const eventText of events) {
        const event = parseSSEEvent(eventText);
        content += event.content;
        completed ||= event.completed;
      }
    }
    buffer += decoder.decode();
    if (buffer.trim()) {
      const event = parseSSEEvent(buffer);
      content += event.content;
      completed ||= event.completed;
    }
  } catch (error) {
    if (error?.retryable !== undefined) throw error;
    throw networkError(error);
  }
  if (!completed) throw clientError('Stream ended before the completion marker', { retryable: true });
  if (content.trim() === '') throw clientError('Stream completed without message content');
  return content.trim();
}

async function waitBeforeRetry(delayMs, signal) {
  if (signal?.aborted) throw signal.reason ?? new Error('Request was aborted');
  await new Promise((resolve, reject) => {
    const timer = setTimeout(resolve, delayMs);
    signal?.addEventListener('abort', () => {
      clearTimeout(timer);
      reject(signal.reason ?? new Error('Request was aborted'));
    }, { once: true });
  });
}

export function completionEndpoint(baseURL) {
  const url = new URL(required(baseURL, 'OPENAI_BASE_URL'));
  if (!['http:', 'https:'].includes(url.protocol)) {
    throw new Error('OPENAI_BASE_URL must use http or https');
  }
  url.pathname = url.pathname.replace(/\/$/, '').replace(/\/v1$/, '') + '/v1/chat/completions';
  url.search = '';
  url.hash = '';
  return url.toString();
}

export class OpenAICompatibleClient {
  constructor(options = {}) {
    this.apiKey = required(options.apiKey ?? process.env.OPENAI_API_KEY, 'OPENAI_API_KEY');
    this.endpoint = completionEndpoint(options.baseURL ?? process.env.OPENAI_BASE_URL ?? DEFAULT_BASE_URL);
    this.model = required(options.model ?? process.env.OPENAI_MODEL, 'OPENAI_MODEL');
    this.fetchImpl = options.fetchImpl ?? globalThis.fetch;
    this.timeoutMs = positiveInteger(
      options.timeoutMs ?? process.env.OPENAI_TIMEOUT_MS ?? DEFAULT_TIMEOUT_MS,
      'OPENAI_TIMEOUT_MS',
    );
    this.maxTokens = positiveInteger(
      options.maxTokens ?? process.env.OPENAI_MAX_TOKENS ?? DEFAULT_MAX_TOKENS,
      'OPENAI_MAX_TOKENS',
    );
    this.maxRetries = nonNegativeInteger(
      options.maxRetries ?? process.env.OPENAI_MAX_RETRIES ?? DEFAULT_MAX_RETRIES,
      'OPENAI_MAX_RETRIES',
    );
    this.retryDelayMs = nonNegativeInteger(
      options.retryDelayMs ?? process.env.OPENAI_RETRY_DELAY_MS ?? DEFAULT_RETRY_DELAY_MS,
      'OPENAI_RETRY_DELAY_MS',
    );
  }

  async complete({ systemPrompt, userPrompt, signal, maxTokens }) {
    const generationLimit = maxTokens === undefined
      ? this.maxTokens
      : positiveInteger(maxTokens, 'maxTokens');
    let lastError;
    for (let attempt = 0; attempt <= this.maxRetries; attempt += 1) {
      try {
        return await this.completeOnce({ systemPrompt, userPrompt, signal, maxTokens: generationLimit });
      } catch (error) {
        lastError = error;
        if (signal?.aborted || !error?.retryable || attempt === this.maxRetries) throw error;
        await waitBeforeRetry(this.retryDelayMs * (attempt + 1), signal);
      }
    }
    throw lastError;
  }

  async completeOnce({ systemPrompt, userPrompt, signal, maxTokens }) {
    const timeoutSignal = AbortSignal.timeout(this.timeoutMs);
    const combinedSignal = signal ? AbortSignal.any([signal, timeoutSignal]) : timeoutSignal;
    let response;
    try {
      response = await this.fetchImpl(this.endpoint, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${this.apiKey}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          model: this.model,
          messages: [
            { role: 'system', content: required(systemPrompt, 'systemPrompt') },
            { role: 'user', content: required(userPrompt, 'userPrompt') },
          ],
          max_tokens: maxTokens,
          temperature: 0.2,
          stream: true,
        }),
        signal: combinedSignal,
      });
    } catch (error) {
      if (signal?.aborted) throw error;
      throw networkError(error);
    }

    if (!response.ok) {
      const text = await response.text();
      let payload;
      try { payload = JSON.parse(text); } catch { payload = undefined; }
      throw clientError(
        `OpenAI-compatible endpoint returned HTTP ${response.status}`
          + `${payload?.error?.message ? `: ${payload.error.message}` : ''}`,
        {
          status: response.status,
          code: `HTTP_${response.status}`,
          retryable: RETRYABLE_STATUS_CODES.has(response.status) || response.status >= 500,
        },
      );
    }

    const contentType = response.headers.get('content-type')?.toLowerCase() ?? '';
    return contentType.includes('text/event-stream')
      ? parseStream(response)
      : parseJSONCompletion(await response.text(), response.status);
  }
}
