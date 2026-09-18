import assert from 'node:assert/strict'
import test from 'node:test'
import { apply } from './index.js'

function pluginContext(definitions, sections = [], listeners = {}, agents = []) {
  return {
    effect(register) {
      return register()
    },
    tools: {
      register(definition) {
        definitions.push(definition)
        return () => {}
      },
    },
    systemPrompt: {
      section(definition) {
        sections.push(definition)
        return () => {}
      },
    },
    agents: {
      list() {
        return agents
      },
    },
    on(event, listener) {
      listeners[event] = listener
      return () => {}
    },
  }
}

test('apply registers the three model-facing Registry tools', () => {
  const definitions = []
  const sections = []
  const listeners = {}
  const ctx = pluginContext(definitions, sections, listeners)

  apply(ctx)

  assert.deepEqual(definitions.map(definition => definition.name), [
    'registry_list_registries',
    'registry_list_records',
    'registry_describe_record',
  ])
  assert.equal(sections.length, 1)
  assert.match(sections[0].text, /across any domain/)
  assert.match(sections[0].text, /Task simplicity/)
  assert.match(sections[0].text, /one best candidate for each distinct capability/)
  assert.match(sections[0].text, /nextRecommendedCapability/)
  assert.match(sections[0].text, /different evidence or decisions/)
  assert.match(sections[0].text, /descriptions own their applicability contract/)
  assert.match(sections[0].text, /already looks detailed/)
  assert.equal(typeof listeners['agent/created'], 'function')
  assert.equal(typeof listeners['agent/disposed'], 'function')
  assert.equal(typeof listeners['agent/pre-step'], 'function')
  assert.match(definitions[0].description, /current cloud identity/)
  assert.match(definitions[1].description, /registry_describe_record/)
  assert.match(definitions[1].description, /low-cost discovery step/)
  assert.doesNotMatch(definitions[1].description, /Do not use it for ordinary tasks/)
  assert.match(definitions[1].description, /automatically retries without the text search/)
  assert.match(definitions[2].description, /never invent an endpoint or version/)
})

test('apply installs the discovery policy in existing and newly created Agent scopes', () => {
  const definitions = []
  const sections = []
  const listeners = {}
  const existingSections = []
  const createdSections = []
  const existingAgent = pluginContext([], existingSections)
  existingAgent.ctx = existingAgent
  const createdAgent = pluginContext([], createdSections)
  createdAgent.ctx = createdAgent

  apply(pluginContext(definitions, sections, listeners, [existingAgent]))
  listeners['agent/created']({ agent: createdAgent })
  listeners['agent/created']({ agent: createdAgent })

  assert.equal(existingSections.length, 1)
  assert.equal(createdSections.length, 1)
  assert.equal(existingSections[0].name, 'agent-registry:discovery-policy')
  assert.match(createdSections[0].text, /every non-redundant clear match/)
  assert.match(createdSections[0].text, /exact value as a new capability query/)

  listeners['agent/disposed']({ agent: createdAgent })
})

test('registry_list_records falls back to the candidate list after an empty text search', async () => {
  const definitions = []
  const ctx = pluginContext(definitions)
  const originalFetch = globalThis.fetch
  const originalSecretId = process.env.TENCENTCLOUD_SECRET_ID
  const originalSecretKey = process.env.TENCENTCLOUD_SECRET_KEY
  const payloads = []

  process.env.TENCENTCLOUD_SECRET_ID = 'test-id'
  process.env.TENCENTCLOUD_SECRET_KEY = 'test-key'
  globalThis.fetch = async (_url, options) => {
    payloads.push(JSON.parse(options.body))
    const response = payloads.length === 1
      ? { RequestId: 'request-search', RecordSet: [], TotalCount: 0 }
      : { RequestId: 'request-fallback', RecordSet: [{ RecordId: 'rec-developer' }], TotalCount: 1 }
    return {
      ok: true,
      status: 200,
      async text() {
        return JSON.stringify({ Response: response })
      },
    }
  }

  try {
    apply(ctx, {
      endpoint: 'http://127.0.0.1:8080',
      region: 'ap-test',
      registryId: 'reg-test',
    })
    const result = await definitions[1].execute({
      registry_id: 'reg-test',
      search: 'software engineer',
    }, {})

    assert.equal(payloads.length, 2)
    assert.deepEqual(payloads[0].Filters, [{ Name: 'search', Values: ['software engineer'] }])
    assert.equal(payloads[1].Filters, undefined)
    assert.equal(result.records[0].RecordId, 'rec-developer')
    assert.deepEqual(result.searchFallback, {
      reason: 'NO_TEXT_MATCHES',
      originalSearch: 'software engineer',
      originalRequestIds: ['request-search'],
    })
  } finally {
    globalThis.fetch = originalFetch
    if (originalSecretId === undefined) delete process.env.TENCENTCLOUD_SECRET_ID
    else process.env.TENCENTCLOUD_SECRET_ID = originalSecretId
    if (originalSecretKey === undefined) delete process.env.TENCENTCLOUD_SECRET_KEY
    else process.env.TENCENTCLOUD_SECRET_KEY = originalSecretKey
  }
})

test('registry_list_records discovers and searches every accessible active Registry', async () => {
  const definitions = []
  const ctx = pluginContext(definitions)
  const originalFetch = globalThis.fetch
  const originalSecretId = process.env.TENCENTCLOUD_SECRET_ID
  const originalSecretKey = process.env.TENCENTCLOUD_SECRET_KEY
  const recordPayloads = []

  process.env.TENCENTCLOUD_SECRET_ID = 'test-id'
  process.env.TENCENTCLOUD_SECRET_KEY = 'test-key'
  globalThis.fetch = async (_url, options) => {
    const action = options.headers['X-TC-Action']
    const payload = JSON.parse(options.body)
    let response
    if (action === 'DescribeRegistryList') {
      response = {
        RequestId: 'request-registries',
        RegistrySet: [
          { RegistryId: 'reg-one', Name: 'one', Status: 'ACTIVE' },
          { RegistryId: 'reg-two', Name: 'two', Status: 'ACTIVE' },
        ],
        TotalCount: 2,
      }
    } else {
      recordPayloads.push(payload)
      response = {
        RequestId: `request-${payload.RegistryId}`,
        RecordSet: [{
          RecordId: `record-${payload.RegistryId}`,
          RegistryId: payload.RegistryId,
          Name: `agent-${payload.RegistryId}`,
        }],
        TotalCount: 1,
      }
    }
    return {
      ok: true,
      status: 200,
      async text() {
        return JSON.stringify({ Response: response })
      },
    }
  }

  try {
    apply(ctx, {
      endpoint: 'http://127.0.0.1:8080',
      region: 'ap-test',
      registryId: 'reg-default',
    })
    const result = await definitions[1].execute({
      search: 'delivery',
      descriptor_type: 'A2A',
    }, {})

    assert.equal(result.scope, 'ALL_ACCESSIBLE_REGISTRIES')
    assert.equal(result.registryCount, 2)
    assert.deepEqual(recordPayloads.map(payload => payload.RegistryId), ['reg-one', 'reg-two'])
    assert.deepEqual(result.records.map(record => record.RegistryId), ['reg-one', 'reg-two'])
    assert.equal(result.totalCount, 2)
    assert.deepEqual(result.partialFailures, [])
  } finally {
    globalThis.fetch = originalFetch
    if (originalSecretId === undefined) delete process.env.TENCENTCLOUD_SECRET_ID
    else process.env.TENCENTCLOUD_SECRET_ID = originalSecretId
    if (originalSecretKey === undefined) delete process.env.TENCENTCLOUD_SECRET_KEY
    else process.env.TENCENTCLOUD_SECRET_KEY = originalSecretKey
  }
})

test('registry_describe_record accepts an explicit RegistryId from cross-Registry search', async () => {
  const definitions = []
  const ctx = pluginContext(definitions)
  const originalFetch = globalThis.fetch
  const originalSecretId = process.env.TENCENTCLOUD_SECRET_ID
  const originalSecretKey = process.env.TENCENTCLOUD_SECRET_KEY
  let payload

  process.env.TENCENTCLOUD_SECRET_ID = 'test-id'
  process.env.TENCENTCLOUD_SECRET_KEY = 'test-key'
  globalThis.fetch = async (_url, options) => {
    payload = JSON.parse(options.body)
    return {
      ok: true,
      status: 200,
      async text() {
        return JSON.stringify({ Response: {
          RequestId: 'request-describe',
          Record: { RecordId: 'rec-other', RegistryId: 'reg-other' },
          Version: { VersionId: 'rv-other', Revision: 1 },
        } })
      },
    }
  }

  try {
    apply(ctx, {
      endpoint: 'http://127.0.0.1:8080',
      region: 'ap-test',
      registryId: 'reg-default',
    })
    const result = await definitions[2].execute({
      registry_id: 'reg-other',
      record_id: 'rec-other',
    }, {})
    assert.equal(payload.RegistryId, 'reg-other')
    assert.equal(result.registryId, 'reg-other')
  } finally {
    globalThis.fetch = originalFetch
    if (originalSecretId === undefined) delete process.env.TENCENTCLOUD_SECRET_ID
    else process.env.TENCENTCLOUD_SECRET_ID = originalSecretId
    if (originalSecretKey === undefined) delete process.env.TENCENTCLOUD_SECRET_KEY
    else process.env.TENCENTCLOUD_SECRET_KEY = originalSecretKey
  }
})

test('first step automatically discovers candidates and injects non-mandatory Registry context', async () => {
  const definitions = []
  const listeners = {}
  const ctx = pluginContext(definitions, [], listeners)
  const originalFetch = globalThis.fetch
  const originalSecretId = process.env.TENCENTCLOUD_SECRET_ID
  const originalSecretKey = process.env.TENCENTCLOUD_SECRET_KEY

  process.env.TENCENTCLOUD_SECRET_ID = 'test-id'
  process.env.TENCENTCLOUD_SECRET_KEY = 'test-key'
  globalThis.fetch = async (_url, options) => {
    const action = options.headers['X-TC-Action']
    const response = action === 'DescribeRegistryList'
      ? {
          RequestId: 'request-registries',
          RegistrySet: [{ RegistryId: 'reg-demo', Name: 'demo', Status: 'ACTIVE' }],
          TotalCount: 1,
        }
      : {
          RequestId: 'request-records',
          RecordSet: [{
            RegistryId: 'reg-demo',
            RecordId: 'rec-review',
            Name: 'team/review-agent',
            Description: 'Independent review for code and documents.',
            DescriptorType: 'A2A',
          }],
          TotalCount: 1,
        }
    return {
      ok: true,
      status: 200,
      async text() {
        return JSON.stringify({ Response: response })
      },
    }
  }

  try {
    apply(ctx, {
      endpoint: 'http://127.0.0.1:8080',
      region: 'ap-test',
      autoDiscover: true,
      autoDiscoverLimit: 5,
    })
    const userMessage = {
      content: [{ type: 'text', text: 'Build a small JSON comparison page.' }],
      source: { kind: 'user' },
    }
    const decision = await listeners['agent/pre-step']({
      messages: [userMessage],
      turn: 1,
      step: 1,
      signal: new AbortController().signal,
    }, async () => ({ kind: 'enter', messages: [userMessage] }))

    assert.equal(decision.messages.length, 2)
    assert.deepEqual(decision.messages[1].source, {
      kind: 'plugin',
      plugin: 'agent-registry:auto-discovery',
    })
    const injected = decision.messages[1].content[0].text
    assert.match(injected, /team\/review-agent/)
    assert.match(injected, /one best candidate per distinct capability/)
    assert.match(injected, /Task simplicity, your own ability/)
    assert.match(injected, /descriptions own their applicability/)
    assert.match(injected, /detailed user input is not a reason to skip/)
    assert.match(injected, /Re-evaluate remaining candidates after every result/)
    assert.match(injected, /different\s+evidence or decisions are non-redundant/)
    assert.match(injected, /nextRecommendedCapability/)
    assert.match(injected, /registry_describe_record/)
  } finally {
    globalThis.fetch = originalFetch
    if (originalSecretId === undefined) delete process.env.TENCENTCLOUD_SECRET_ID
    else process.env.TENCENTCLOUD_SECRET_ID = originalSecretId
    if (originalSecretKey === undefined) delete process.env.TENCENTCLOUD_SECRET_KEY
    else process.env.TENCENTCLOUD_SECRET_KEY = originalSecretKey
  }
})

test('automatic discovery failure does not block the user step', async () => {
  const definitions = []
  const listeners = {}
  const ctx = pluginContext(definitions, [], listeners)
  const originalFetch = globalThis.fetch
  const originalSecretId = process.env.TENCENTCLOUD_SECRET_ID
  const originalSecretKey = process.env.TENCENTCLOUD_SECRET_KEY

  process.env.TENCENTCLOUD_SECRET_ID = 'test-id'
  process.env.TENCENTCLOUD_SECRET_KEY = 'test-key'
  globalThis.fetch = async () => ({
    ok: true,
    status: 200,
    async text() {
      return JSON.stringify({ Response: { Error: { Code: 'InternalError', Message: 'temporary failure' }, RequestId: 'request-failed' } })
    },
  })

  try {
    apply(ctx, { endpoint: 'http://127.0.0.1:8080', region: 'ap-test' })
    const userMessage = {
      content: [{ type: 'text', text: 'Explain this file.' }],
      source: { kind: 'user' },
    }
    const decision = await listeners['agent/pre-step']({
      messages: [userMessage],
      turn: 1,
      step: 1,
      signal: new AbortController().signal,
    }, async () => ({ kind: 'enter', messages: [userMessage] }))

    assert.equal(decision.kind, 'enter')
    assert.equal(decision.messages.length, 2)
    assert.match(decision.messages[1].content[0].text, /request-failed/)
    assert.match(decision.messages[1].content[0].text, /Continue the user task/)
  } finally {
    globalThis.fetch = originalFetch
    if (originalSecretId === undefined) delete process.env.TENCENTCLOUD_SECRET_ID
    else process.env.TENCENTCLOUD_SECRET_ID = originalSecretId
    if (originalSecretKey === undefined) delete process.env.TENCENTCLOUD_SECRET_KEY
    else process.env.TENCENTCLOUD_SECRET_KEY = originalSecretKey
  }
})

test('automatic discovery prioritizes A2A candidates across Registries before catalog metadata', async () => {
  const definitions = []
  const listeners = {}
  const ctx = pluginContext(definitions, [], listeners)
  const originalFetch = globalThis.fetch
  const originalSecretId = process.env.TENCENTCLOUD_SECRET_ID
  const originalSecretKey = process.env.TENCENTCLOUD_SECRET_KEY

  process.env.TENCENTCLOUD_SECRET_ID = 'test-id'
  process.env.TENCENTCLOUD_SECRET_KEY = 'test-key'
  globalThis.fetch = async (_url, options) => {
    const action = options.headers['X-TC-Action']
    const payload = JSON.parse(options.body)
    let response
    if (action === 'DescribeRegistryList') {
      response = {
        RequestId: 'request-registries',
        RegistrySet: [
          { RegistryId: 'reg-large', Name: 'large', Status: 'ACTIVE' },
          { RegistryId: 'reg-user', Name: 'user', Status: 'ACTIVE' },
        ],
        TotalCount: 2,
      }
    } else if (payload.Filters?.some(filter => filter.Name === 'search')) {
      response = { RequestId: `search-${payload.RegistryId}`, RecordSet: [], TotalCount: 0 }
    } else if (payload.RegistryId === 'reg-large') {
      response = {
        RequestId: 'fallback-large',
        RecordSet: Array.from({ length: 5 }, (_, index) => ({
          RegistryId: 'reg-large',
          RecordId: `rec-skill-${index}`,
          Name: `catalog-skill-${index}`,
          DescriptorType: 'AGENT_SKILLS',
        })),
        TotalCount: 5,
      }
    } else {
      response = {
        RequestId: 'fallback-user',
        RecordSet: [{
          RegistryId: 'reg-user',
          RecordId: 'rec-user-agent',
          Name: 'user/custom-agent',
          DescriptorType: 'A2A',
        }],
        TotalCount: 1,
      }
    }
    return {
      ok: true,
      status: 200,
      async text() {
        return JSON.stringify({ Response: response })
      },
    }
  }

  try {
    apply(ctx, {
      endpoint: 'http://127.0.0.1:8080',
      region: 'ap-test',
      autoDiscoverLimit: 3,
    })
    const userMessage = {
      content: [{ type: 'text', text: 'Create a small page.' }],
      source: { kind: 'user' },
    }
    const decision = await listeners['agent/pre-step']({
      messages: [userMessage],
      turn: 1,
      step: 1,
      signal: new AbortController().signal,
    }, async () => ({ kind: 'enter', messages: [userMessage] }))
    const text = decision.messages[1].content[0].text
    const payload = JSON.parse(text.match(/<agent-registry-discovery>\n([^\n]+)/u)[1])

    assert.equal(payload.candidateSelection, 'A2A_FIRST_CROSS_REGISTRY')
    assert.equal(payload.candidates[0].name, 'user/custom-agent')
    assert.deepEqual(payload.candidates.map(candidate => candidate.registryId), [
      'reg-user',
      'reg-large',
      'reg-large',
    ])
  } finally {
    globalThis.fetch = originalFetch
    if (originalSecretId === undefined) delete process.env.TENCENTCLOUD_SECRET_ID
    else process.env.TENCENTCLOUD_SECRET_ID = originalSecretId
    if (originalSecretKey === undefined) delete process.env.TENCENTCLOUD_SECRET_KEY
    else process.env.TENCENTCLOUD_SECRET_KEY = originalSecretKey
  }
})
