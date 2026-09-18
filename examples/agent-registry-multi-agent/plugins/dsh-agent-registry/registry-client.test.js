import assert from 'node:assert/strict'
import test from 'node:test'
import {
  buildDescribePayload,
  buildListPayload,
  buildRegistryListPayload,
  callRegistryAction,
  createSignedRequest,
  normalizeDescribeResult,
  normalizeRegistryListResult,
} from './registry-client.js'

const baseConfig = {
  endpoint: 'https://ags.example.test/',
  region: 'ap-test',
  registryId: 'reg-0123abcd',
  service: 'ags',
  version: '2025-09-20',
  secretId: 'test-secret-id',
  secretKey: 'test-secret-key',
  timeoutMs: 1_000,
}

test('buildListPayload maps model-facing filters to Cloud API filters', () => {
  assert.deepEqual(buildListPayload('reg-0123abcd', {
    search: 'weather analysis',
    descriptor_type: 'A2A',
    lifecycle_status: 'ACTIVE',
    offset: 20,
    limit: 10,
  }), {
    RegistryId: 'reg-0123abcd',
    Offset: 20,
    Limit: 10,
    Filters: [
      { Name: 'search', Values: ['weather analysis'] },
      { Name: 'descriptor_type', Values: ['A2A'] },
      { Name: 'lifecycle_status', Values: ['ACTIVE'] },
    ],
  })
})

test('buildRegistryListPayload maps Registry discovery filters', () => {
  assert.deepEqual(buildRegistryListPayload({
    search: 'team agents',
    status: 'ACTIVE',
    offset: 10,
    limit: 50,
  }), {
    Offset: 10,
    Limit: 50,
    Filters: [
      { Name: 'search', Values: ['team agents'] },
      { Name: 'status', Values: ['ACTIVE'] },
    ],
  })
})

test('normalizeRegistryListResult exposes visible Registries', () => {
  assert.deepEqual(normalizeRegistryListResult({
    RequestId: 'req-registries',
    RegistrySet: [{ RegistryId: 'reg-one', Name: 'one' }],
    TotalCount: 1,
  }), {
    requestId: 'req-registries',
    registries: [{ RegistryId: 'reg-one', Name: 'one' }],
    totalCount: 1,
  })
})

test('buildDescribePayload defaults to stable and rejects two selectors', () => {
  assert.deepEqual(buildDescribePayload('reg-0123abcd', { record_id: 'rec-0123abcd' }), {
    RegistryId: 'reg-0123abcd',
    RecordId: 'rec-0123abcd',
  })
  assert.throws(
    () => buildDescribePayload('reg-0123abcd', {
      record_id: 'rec-0123abcd',
      version_id: 'rv-0123abcd',
      label: 'stable',
    }),
    /mutually exclusive/,
  )
})

test('createSignedRequest is deterministic and does not expose the secret key', () => {
  const request = createSignedRequest({
    ...baseConfig,
    action: 'DescribeRegistryRecordList',
    payload: { RegistryId: 'reg-0123abcd', Offset: 0, Limit: 20 },
    timestamp: 1_787_000_000,
  })
  assert.equal(request.headers['X-TC-Action'], 'DescribeRegistryRecordList')
  assert.equal(request.headers['X-TC-Version'], '2025-09-20')
  assert.equal(request.headers['X-TC-Region'], 'ap-test')
  assert.match(request.headers.Authorization, /^TC3-HMAC-SHA256 Credential=test-secret-id\//)
  assert.match(request.headers.Authorization, /Signature=[a-f0-9]{64}$/)
  assert.match(request.headers.Authorization, /Signature=a69ef65c8776593a5f26487807ab09f110eb5ed48f5c5982ce466b2cb7c67c29$/)
  assert.equal(request.headers.Authorization.includes('test-secret-key'), false)
})

test('callRegistryAction posts a signed request and unwraps Response', async () => {
  const response = await callRegistryAction(
    baseConfig,
    'DescribeRegistryRecordList',
    { RegistryId: 'reg-0123abcd', Offset: 0, Limit: 20 },
    {
      timestamp: 1_787_000_000,
      fetchImpl: async (_url, init) => {
        assert.equal(init.method, 'POST')
        assert.equal(init.headers['X-TC-Action'], 'DescribeRegistryRecordList')
        assert.deepEqual(JSON.parse(init.body), {
          RegistryId: 'reg-0123abcd',
          Offset: 0,
          Limit: 20,
        })
        return new Response(JSON.stringify({
          Response: {
            RequestId: 'req-test',
            RecordSet: [],
            TotalCount: 0,
          },
        }), { status: 200 })
      },
    },
  )
  assert.equal(response.RequestId, 'req-test')
})

test('callRegistryAction preserves the CAPI RequestId on API errors', async () => {
  await assert.rejects(
    callRegistryAction(
      baseConfig,
      'DescribeRegistryRecord',
      { RegistryId: 'reg-0123abcd', RecordId: 'rec-0123abcd' },
      {
        timestamp: 1_787_000_000,
        fetchImpl: async () => new Response(JSON.stringify({
          Response: {
            Error: {
              Code: 'InternalError',
              Message: 'An internal error has occurred.',
            },
            RequestId: 'req-internal-error',
          },
        }), { status: 200 }),
      },
    ),
    error => {
      assert.equal(error.code, 'InternalError')
      assert.equal(error.requestId, 'req-internal-error')
      assert.match(error.message, /RequestId: req-internal-error/)
      return true
    },
  )
})

test('normalizeDescribeResult exposes the resolved stable identity', () => {
  assert.deepEqual(normalizeDescribeResult('reg-0123abcd', {
    RequestId: 'req-test',
    Record: { RecordId: 'rec-0123abcd', Name: 'weather-agent' },
    Version: { VersionId: 'rv-0123abcd', Revision: 3, Descriptors: { name: 'weather-agent' } },
    ResolvedBy: 'DEFAULT_STABLE',
    ResolvedLabel: 'stable',
  }), {
    registryId: 'reg-0123abcd',
    requestId: 'req-test',
    record: { RecordId: 'rec-0123abcd', Name: 'weather-agent' },
    version: { VersionId: 'rv-0123abcd', Revision: 3, Descriptors: { name: 'weather-agent' } },
    resolvedBy: 'DEFAULT_STABLE',
    resolvedLabel: 'stable',
    resolvedVersionId: 'rv-0123abcd',
    resolvedRevision: 3,
  })
})

test('normalizeDescribeResult remains strict JSON before stable is bound', () => {
  const result = normalizeDescribeResult('reg-0123abcd', {
    RequestId: 'req-test',
    Record: { RecordId: 'rec-0123abcd', Name: 'pending-agent' },
    Version: null,
    ResolvedBy: 'DEFAULT_STABLE',
    ResolvedLabel: 'stable',
  })
  assert.deepEqual(result, {
    registryId: 'reg-0123abcd',
    requestId: 'req-test',
    record: { RecordId: 'rec-0123abcd', Name: 'pending-agent' },
    version: null,
    resolvedBy: 'DEFAULT_STABLE',
    resolvedLabel: 'stable',
  })
  assert.doesNotThrow(() => JSON.stringify(result))
})

test('normalizeDescribeResult accepts the deployed StableVersion response shape', () => {
  const result = normalizeDescribeResult('reg-0123abcd', {
    RequestId: 'req-test',
    Record: { RecordId: 'rec-0123abcd', Name: 'legacy-shape-agent' },
    StableVersion: { VersionId: 'rv-legacy123', Revision: 2, Descriptors: { name: 'legacy-shape-agent' } },
  })
  assert.equal(result.resolvedVersionId, 'rv-legacy123')
  assert.equal(result.resolvedRevision, 2)
  assert.equal(result.version.Descriptors.name, 'legacy-shape-agent')
})
