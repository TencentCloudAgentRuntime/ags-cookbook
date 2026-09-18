import { createHash, createHmac } from 'node:crypto'

const DEFAULT_SERVICE = 'ags'
const DEFAULT_VERSION = '2025-09-20'
const DEFAULT_ENDPOINT = 'https://registry.tencentcloudapi.com/'
const DEFAULT_TIMEOUT_MS = 30_000

function requiredString(value, name) {
  if (typeof value !== 'string' || value.trim() === '') {
    throw new Error(`Agent Registry is not configured: ${name} is required`)
  }
  return value.trim()
}

function optionalString(value) {
  return typeof value === 'string' && value.trim() !== '' ? value.trim() : undefined
}

function sha256Hex(value) {
  return createHash('sha256').update(value).digest('hex')
}

function hmac(key, value, encoding) {
  return createHmac('sha256', key).update(value).digest(encoding)
}

function utcDate(timestamp) {
  return new Date(timestamp * 1000).toISOString().slice(0, 10)
}

function normalizeEndpoint(endpoint) {
  const url = new URL(requiredString(endpoint, 'AGENT_REGISTRY_ENDPOINT'))
  if (url.protocol !== 'https:' && url.protocol !== 'http:') {
    throw new Error('Agent Registry endpoint must use http or https')
  }
  if (url.username !== '' || url.password !== '' || url.search !== '' || url.hash !== '') {
    throw new Error('Agent Registry endpoint must not contain credentials, query parameters, or a fragment')
  }
  return url
}

export function resolveRuntimeConfig(config = {}, env = process.env) {
  const secretIdEnv = optionalString(config.secretIdEnv) ?? 'TENCENTCLOUD_SECRET_ID'
  const secretKeyEnv = optionalString(config.secretKeyEnv) ?? 'TENCENTCLOUD_SECRET_KEY'
  const sessionTokenEnv = optionalString(config.sessionTokenEnv) ?? 'TENCENTCLOUD_TOKEN'

  return {
    endpoint: optionalString(config.endpoint) ?? optionalString(env.AGENT_REGISTRY_ENDPOINT) ?? DEFAULT_ENDPOINT,
    region: optionalString(config.region)
      ?? optionalString(env.TENCENTCLOUD_REGION)
      ?? optionalString(env.AGENT_REGISTRY_REGION),
    registryId: optionalString(config.registryId) ?? optionalString(env.AGENT_REGISTRY_ID),
    service: optionalString(config.service) ?? DEFAULT_SERVICE,
    version: optionalString(config.version) ?? DEFAULT_VERSION,
    timeoutMs: Number.isFinite(config.timeoutMs) ? Number(config.timeoutMs) : DEFAULT_TIMEOUT_MS,
    secretId: optionalString(env[secretIdEnv]),
    secretKey: optionalString(env[secretKeyEnv]),
    sessionToken: optionalString(env[sessionTokenEnv]) ?? optionalString(env.TENCENTCLOUD_SESSION_TOKEN),
  }
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
  sessionToken,
  timestamp = Math.floor(Date.now() / 1000),
}) {
  const url = normalizeEndpoint(endpoint)
  const resolvedService = requiredString(service, 'service')
  const resolvedVersion = requiredString(version, 'version')
  const resolvedRegion = requiredString(region, 'AGENT_REGISTRY_REGION')
  const resolvedAction = requiredString(action, 'action')
  const resolvedSecretId = requiredString(secretId, 'TENCENTCLOUD_SECRET_ID')
  const resolvedSecretKey = requiredString(secretKey, 'TENCENTCLOUD_SECRET_KEY')
  const body = JSON.stringify(payload ?? {})
  const contentType = 'application/json; charset=utf-8'
  const canonicalUri = url.pathname === '' ? '/' : url.pathname
  const canonicalHeaders = [
    `content-type:${contentType}`,
    `host:${url.host}`,
    `x-tc-action:${resolvedAction.toLowerCase()}`,
    '',
  ].join('\n')
  const signedHeaders = 'content-type;host;x-tc-action'
  const canonicalRequest = [
    'POST',
    canonicalUri,
    '',
    canonicalHeaders,
    signedHeaders,
    sha256Hex(body),
  ].join('\n')

  const date = utcDate(timestamp)
  const credentialScope = `${date}/${resolvedService}/tc3_request`
  const stringToSign = [
    'TC3-HMAC-SHA256',
    String(timestamp),
    credentialScope,
    sha256Hex(canonicalRequest),
  ].join('\n')
  const secretDate = hmac(`TC3${resolvedSecretKey}`, date)
  const secretService = hmac(secretDate, resolvedService)
  const secretSigning = hmac(secretService, 'tc3_request')
  const signature = hmac(secretSigning, stringToSign, 'hex')
  const authorization = 'TC3-HMAC-SHA256 '
    + `Credential=${resolvedSecretId}/${credentialScope}, `
    + `SignedHeaders=${signedHeaders}, Signature=${signature}`

  const headers = {
    Authorization: authorization,
    'Content-Type': contentType,
    'X-TC-Action': resolvedAction,
    'X-TC-Version': resolvedVersion,
    'X-TC-Timestamp': String(timestamp),
    'X-TC-Region': resolvedRegion,
  }
  if (sessionToken !== undefined && sessionToken !== '') {
    headers['X-TC-Token'] = sessionToken
  }

  return { url: url.toString(), headers, body }
}

function cancellableSignal(callerSignal, timeoutMs) {
  const controller = new AbortController()
  const abortFromCaller = () => controller.abort(callerSignal?.reason)
  if (callerSignal?.aborted) abortFromCaller()
  else callerSignal?.addEventListener('abort', abortFromCaller, { once: true })

  const timer = setTimeout(() => controller.abort(new Error('Agent Registry request timed out')), timeoutMs)
  return {
    signal: controller.signal,
    dispose() {
      clearTimeout(timer)
      callerSignal?.removeEventListener('abort', abortFromCaller)
    },
  }
}

export async function callRegistryAction(config, action, payload, options = {}) {
  const request = createSignedRequest({
    ...config,
    action,
    payload,
    timestamp: options.timestamp,
  })
  const timeoutMs = Number.isFinite(config.timeoutMs) && config.timeoutMs > 0
    ? config.timeoutMs
    : DEFAULT_TIMEOUT_MS
  const fetchImpl = options.fetchImpl ?? globalThis.fetch
  if (typeof fetchImpl !== 'function') throw new Error('fetch is unavailable in this Node runtime')
  const operation = cancellableSignal(options.signal, timeoutMs)

  try {
    const response = await fetchImpl(request.url, {
      method: 'POST',
      headers: request.headers,
      body: request.body,
      signal: operation.signal,
    })
    const text = await response.text()
    let envelope
    try {
      envelope = JSON.parse(text)
    } catch {
      throw new Error(`Agent Registry returned non-JSON content (HTTP ${response.status})`)
    }
    const requestId = optionalString(envelope?.Response?.RequestId)
    const requestIdSuffix = requestId === undefined ? '' : ` (RequestId: ${requestId})`
    if (!response.ok) {
      const message = envelope?.Response?.Error?.Message
      const error = new Error(
        `Agent Registry HTTP ${response.status}${message ? `: ${message}` : ''}${requestIdSuffix}`,
      )
      if (requestId !== undefined) error.requestId = requestId
      throw error
    }
    const apiError = envelope?.Response?.Error
    if (apiError !== undefined) {
      const error = new Error(
        `Agent Registry ${apiError.Code ?? 'UnknownError'}: ${apiError.Message ?? 'request failed'}${requestIdSuffix}`,
      )
      error.code = apiError.Code
      if (requestId !== undefined) error.requestId = requestId
      throw error
    }
    if (envelope?.Response === undefined) {
      throw new Error('Agent Registry response is missing the Response envelope')
    }
    return envelope.Response
  } finally {
    operation.dispose()
  }
}

function normalizedInteger(value, fallback, minimum, maximum, name) {
  const resolved = value ?? fallback
  if (!Number.isInteger(resolved) || resolved < minimum || resolved > maximum) {
    throw new Error(`${name} must be an integer between ${minimum} and ${maximum}`)
  }
  return resolved
}

export function buildListPayload(registryId, args = {}) {
  const filters = []
  const mappings = [
    ['name', args.name],
    ['search', args.search],
    ['descriptor_type', args.descriptor_type],
    ['lifecycle_status', args.lifecycle_status],
  ]
  for (const [name, value] of mappings) {
    const normalized = optionalString(value)
    if (normalized !== undefined) filters.push({ Name: name, Values: [normalized] })
  }
  const payload = {
    RegistryId: requiredString(registryId, 'AGENT_REGISTRY_ID'),
    Offset: normalizedInteger(args.offset, 0, 0, Number.MAX_SAFE_INTEGER, 'offset'),
    Limit: normalizedInteger(args.limit, 20, 1, 100, 'limit'),
  }
  if (filters.length > 0) payload.Filters = filters
  return payload
}

export function buildRegistryListPayload(args = {}) {
  const filters = []
  const mappings = [
    ['name', args.name],
    ['search', args.search],
    ['status', args.status],
    ['archived', args.archived],
  ]
  for (const [name, value] of mappings) {
    const normalized = optionalString(value)
    if (normalized !== undefined) filters.push({ Name: name, Values: [normalized] })
  }
  const payload = {
    Offset: normalizedInteger(args.offset, 0, 0, Number.MAX_SAFE_INTEGER, 'offset'),
    Limit: normalizedInteger(args.limit, 20, 1, 100, 'limit'),
  }
  if (filters.length > 0) payload.Filters = filters
  return payload
}

export function buildDescribePayload(registryId, args = {}) {
  const versionId = optionalString(args.version_id)
  const label = optionalString(args.label)
  if (versionId !== undefined && label !== undefined) {
    throw new Error('version_id and label are mutually exclusive')
  }
  return {
    RegistryId: requiredString(registryId, 'AGENT_REGISTRY_ID'),
    RecordId: requiredString(args.record_id, 'record_id'),
    ...(versionId !== undefined ? { VersionId: versionId } : {}),
    ...(label !== undefined ? { Label: label } : {}),
  }
}

export function normalizeListResult(registryId, response) {
  return {
    registryId,
    requestId: requiredString(response.RequestId, 'Response.RequestId'),
    records: Array.isArray(response.RecordSet) ? response.RecordSet : [],
    totalCount: Number.isFinite(response.TotalCount) ? response.TotalCount : 0,
  }
}

export function normalizeRegistryListResult(response) {
  return {
    requestId: requiredString(response.RequestId, 'Response.RequestId'),
    registries: Array.isArray(response.RegistrySet) ? response.RegistrySet : [],
    totalCount: Number.isFinite(response.TotalCount) ? response.TotalCount : 0,
  }
}

export function normalizeDescribeResult(registryId, response) {
  // Current v1 returns Version; the deployed demo environment may still use
  // the earlier StableVersion field. Normalize both without changing the
  // model-facing contract.
  const version = response.Version ?? response.StableVersion ?? null
  return {
    registryId,
    requestId: requiredString(response.RequestId, 'Response.RequestId'),
    record: response.Record ?? null,
    version,
    ...(response.ResolvedBy !== undefined ? { resolvedBy: response.ResolvedBy } : {}),
    ...(response.ResolvedLabel !== undefined ? { resolvedLabel: response.ResolvedLabel } : {}),
    ...(version?.VersionId !== undefined ? { resolvedVersionId: version.VersionId } : {}),
    ...(version?.Revision !== undefined ? { resolvedRevision: version.Revision } : {}),
  }
}
