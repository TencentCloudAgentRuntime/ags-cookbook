import assert from 'node:assert/strict';
import test from 'node:test';
import { OpenAICompatibleClient, completionEndpoint } from '../src/openai-client.mjs';

test('completionEndpoint accepts base URLs with or without v1', () => {
  assert.equal(completionEndpoint('https://llm.example'), 'https://llm.example/v1/chat/completions');
  assert.equal(completionEndpoint('https://llm.example/v1'), 'https://llm.example/v1/chat/completions');
});

test('client requests streaming and accepts a JSON-compatible response', async () => {
  let captured;
  const client = new OpenAICompatibleClient({
    apiKey: 'secret-for-test',
    baseURL: 'https://llm.example/v1',
    model: 'example-model',
    maxTokens: 4096,
    fetchImpl: async (url, init) => {
      captured = { url, init };
      return new Response(JSON.stringify({ choices: [{ message: { content: 'done' } }] }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    },
  });

  assert.equal(await client.complete({ systemPrompt: 'system', userPrompt: 'user' }), 'done');
  assert.equal(captured.url, 'https://llm.example/v1/chat/completions');
  assert.equal(JSON.parse(captured.init.body).model, 'example-model');
  assert.equal(JSON.parse(captured.init.body).max_tokens, 4096);
  assert.equal(JSON.parse(captured.init.body).stream, true);
  assert.equal(captured.init.headers.Authorization, 'Bearer secret-for-test');
});

test('client assembles content from an SSE stream', async () => {
  const client = new OpenAICompatibleClient({
    apiKey: 'secret-for-test',
    baseURL: 'https://llm.example',
    model: 'example-model',
    fetchImpl: async () => new Response([
      'data: {"choices":[{"delta":{"content":"multi"},"finish_reason":null}]}\n\n',
      'data: {"choices":[{"delta":{"content":" agent"},"finish_reason":"stop"}]}\n\n',
      'data: [DONE]\n\n',
    ].join(''), {
      status: 200,
      headers: { 'Content-Type': 'text/event-stream' },
    }),
  });

  assert.equal(await client.complete({ systemPrompt: 'system', userPrompt: 'user' }), 'multi agent');
});

test('client retries one transient fetch failure', async () => {
  let requests = 0;
  const client = new OpenAICompatibleClient({
    apiKey: 'secret-for-test',
    baseURL: 'https://llm.example',
    model: 'example-model',
    retryDelayMs: 0,
    fetchImpl: async () => {
      requests += 1;
      if (requests === 1) throw new TypeError('fetch failed', { cause: { code: 'ECONNRESET' } });
      return new Response(JSON.stringify({ choices: [{ message: { content: 'retried' } }] }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    },
  });

  assert.equal(await client.complete({ systemPrompt: 'system', userPrompt: 'user' }), 'retried');
  assert.equal(requests, 2);
});
