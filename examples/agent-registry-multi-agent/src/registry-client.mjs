import { createHash, createHmac } from 'node:crypto';

const DEFAULT_SERVICE = 'ags';
const DEFAULT_VERSION = '2025-09-20';

function required(value, name) {
  if (typeof value !== 'string' || value.trim() === '') {
    throw new Error(`${name} is required`);
  }
  return value.trim();
}

function sha256(value) {
  return createHash('sha256').update(value).digest('hex');
}

function hmac(key, value, encoding) {
  return createHmac('sha256', key).update(value).digest(encoding);
}

export function createSignedRequest({
  endpoint,
  service = DEFAULT_SERVICE,
  version = DEFAULT_VERSION,
  region,
  action,
  payload,
  secretId,
  secretKey,
  token,
  timestamp = Math.floor(Date.now() / 1000),
}) {
  const url = new URL(required(endpoint, 'AGENT_REGISTRY_ENDPOINT'));
  const body = JSON.stringify(payload ?? {});
  const contentType = 'application/json; charset=utf-8';
  const canonicalHeaders = [
    `content-type:${contentType}`,
    `host:${url.host}`,
    `x-tc-action:${required(action, 'action').toLowerCase()}`,
    '',
  ].join('\n');
  const signedHeaders = 'content-type;host;x-tc-action';
  const canonicalRequest = [
    'POST',
    url.pathname || '/',
    '',
    canonicalHeaders,
    signedHeaders,
    sha256(body),
  ].join('\n');
  const date = new Date(timestamp * 1000).toISOString().slice(0, 10);
  const scope = `${date}/${service}/tc3_request`;
  const stringToSign = [
    'TC3-HMAC-SHA256',
    String(timestamp),
    scope,
    sha256(canonicalRequest),
  ].join('\n');
  const secretDate = hmac(`TC3${required(secretKey, 'secretKey')}`, date);
  const secretService = hmac(secretDate, service);
  const secretSigning = hmac(secretService, 'tc3_request');
  const signature = hmac(secretSigning, stringToSign, 'hex');
  const authorization = 'TC3-HMAC-SHA256 '
    + `Credential=${required(secretId, 'secretId')}/${scope}, `
    + `SignedHeaders=${signedHeaders}, Signature=${signature}`;

  return {
    url: url.toString(),
    body,
    headers: {
      Authorization: authorization,
      'Content-Type': contentType,
      'X-TC-Action': action,
      'X-TC-Version': version,
      'X-TC-Timestamp': String(timestamp),
      'X-TC-Region': required(region, 'region'),
      ...(token ? { 'X-TC-Token': token } : {}),
    },
  };
}

const RETRYABLE_CODES = new Set([
  'InternalError',
  'RequestLimitExceeded',
  'ResourceUnavailable',
]);

function isRetryable(error) {
  return RETRYABLE_CODES.has(error.code)
    || error.status === 429
    || error.status >= 500
    || error.name === 'AbortError'
    || error.name === 'TimeoutError'
    || error instanceof TypeError;
}

export async function callRegistryAction(config, action, payload, options = {}) {
  const fetchImpl = options.fetchImpl || fetch;
  const maxAttempts = options.maxAttempts || 3;
  const retryDelayMs = options.retryDelayMs ?? 250;

  for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
    try {
      const request = createSignedRequest({ ...config, action, payload });
      const response = await fetchImpl(request.url, {
        method: 'POST',
        headers: request.headers,
        body: request.body,
        signal: AbortSignal.timeout(30_000),
      });
      const text = await response.text();
      let envelope;
      try {
        envelope = JSON.parse(text);
      } catch {
        const error = new Error(`Agent Registry returned non-JSON content (HTTP ${response.status})`);
        error.status = response.status;
        throw error;
      }
      const apiError = envelope?.Response?.Error;
      if (!response.ok || apiError) {
        const error = new Error(
          `Agent Registry ${apiError?.Code || `HTTP ${response.status}`}: ${apiError?.Message || 'request failed'}`
            + `${envelope?.Response?.RequestId ? ` (RequestId: ${envelope.Response.RequestId})` : ''}`,
        );
        error.code = apiError?.Code;
        error.status = response.status;
        error.requestId = envelope?.Response?.RequestId;
        throw error;
      }
      if (!envelope?.Response) {
        throw new Error('Agent Registry response is missing the Response envelope');
      }
      return envelope.Response;
    } catch (error) {
      if (attempt === maxAttempts || !isRetryable(error)) throw error;
      await new Promise((resolve) => setTimeout(resolve, retryDelayMs * (2 ** (attempt - 1))));
    }
  }
  throw new Error('Agent Registry request exhausted retries');
}
