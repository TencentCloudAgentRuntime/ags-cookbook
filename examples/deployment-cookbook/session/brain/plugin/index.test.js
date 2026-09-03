import assert from 'node:assert/strict'
import test from 'node:test'

const modulePath = process.env.PLUGIN_MODULE ?? './index.js'
const { AgentRuntimeSessionPersistence } = await import(modulePath)

function backend(request) {
  const value = Object.create(AgentRuntimeSessionPersistence.prototype)
  value.spaceId = 'space-test'
  value.userId = 'user-test'
  value.brainDeploymentId = 'dpl-test'
  value.request = request
  return value
}

test('appendEvents stores a readable projection and the lossless DSH event', async () => {
  const calls = []
  const persistence = backend(async (action, payload) => {
    calls.push({ action, payload })
    return {}
  })
  const event = {
    type: 'user/message',
    seq: 0,
    time: 1,
    data: {
      source: { kind: 'user', rpcId: 'rpc-1' },
      content: [{ type: 'text', text: 'hello' }],
    },
  }

  await persistence.appendEvents('session-test', [event])

  assert.equal(calls.length, 1)
  assert.equal(calls[0].action, 'AppendEvent')
  assert.equal(calls[0].payload.Event.Author, 'user')
  assert.equal(calls[0].payload.Event.InvocationId, 'rpc-1')
  assert.equal(calls[0].payload.Event.Content.Parts[0].Text, 'hello')
  assert.deepEqual(JSON.parse(calls[0].payload.Event.Metadata), {
    source: 'deepseek-harness',
    dshEventType: 'user/message',
    dshSeq: 0,
  })
  assert.deepEqual(JSON.parse(calls[0].payload.Event.Extensions).dshEvent, event)
})

test('appendBatch associates a new Session with the Brain Deployment', async () => {
  const calls = []
  const persistence = backend(async (action, payload) => {
    calls.push({ action, payload })
    return {}
  })
  const meta = { id: 'session-test', version: 0, createdAt: 1 }

  await persistence.appendBatch(meta, [], false)

  assert.equal(calls.length, 1)
  assert.equal(calls[0].action, 'CreateSession')
  assert.deepEqual(calls[0].payload.Metadata, [{
    Name: 'ae.tencentcloud.com/brain-deployment-id',
    Value: 'dpl-test',
  }])
})

test('appendEvents projects chunks, tool calls, tool results, and turn completion', async () => {
  const calls = []
  const persistence = backend(async (action, payload) => {
    calls.push({ action, payload })
    return {}
  })
  const events = [
    {
      type: 'assistant/chunk',
      seq: 0,
      time: 1,
      data: { turn: 1, step: 1, chunk: { type: 'reasoning-delta', index: 0, text: 'thinking' } },
    },
    {
      type: 'tool/call',
      seq: 1,
      time: 2,
      data: { turn: 1, step: 1, callId: 'call-1', name: 'calculator', arguments: '{"a":37,"b":58}' },
    },
    {
      type: 'tool/result',
      seq: 2,
      time: 3,
      data: {
        turn: 1,
        step: 1,
        message: {
          source: { kind: 'tool', callId: 'call-1' },
          content: [{
            type: 'tool-result',
            toolCallId: 'call-1',
            isError: false,
            content: [{ type: 'text', text: '95' }],
          }],
        },
      },
    },
    { type: 'turn/end', seq: 3, time: 4, data: { turn: 1, reason: { kind: 'completed' } } },
  ]

  await persistence.appendEvents('session-test', events)

  assert.deepEqual(calls[0].payload.Event.Content.Parts[0], { Text: 'thinking', Thought: true })
  assert.equal(JSON.parse(calls[0].payload.Event.Metadata).Partial, true)
  assert.deepEqual(JSON.parse(calls[1].payload.Event.Content.Parts[0].FunctionCall), {
    Name: 'calculator',
    Args: { a: 37, b: 58 },
  })
  assert.deepEqual(JSON.parse(calls[2].payload.Event.Content.Parts[0].FunctionResponse), {
    Name: 'call-1',
    Response: { content: '95', isError: false },
  })
  assert.deepEqual(JSON.parse(calls[3].payload.Event.Metadata), {
    source: 'deepseek-harness',
    dshEventType: 'turn/end',
    dshSeq: 3,
    Turn: 1,
    TurnComplete: true,
    Interrupted: false,
  })
})

test('appendEvents projects terminal errors and interrupted turns', async () => {
  const calls = []
  const persistence = backend(async (action, payload) => {
    calls.push({ action, payload })
    return {}
  })

  await persistence.appendEvents('session-test', [{
    type: 'turn/end',
    seq: 0,
    time: 1,
    data: { turn: 1, reason: { kind: 'error', error: { code: 'AUTH', message: 'denied' } } },
  }, {
    type: 'turn/end',
    seq: 1,
    time: 2,
    data: { turn: 2, reason: { kind: 'interrupted' } },
  }])

  assert.equal(calls[0].payload.Event.ErrorCode, 'AUTH')
  assert.equal(calls[0].payload.Event.ErrorMessage, 'denied')
  assert.equal(JSON.parse(calls[1].payload.Event.Metadata).Interrupted, true)
})

test('loadStored reconstructs the DSH header and contiguous event log', async () => {
  const header = { version: 0, id: 'session-test', createdAt: 1, cwd: '/workspace' }
  const event = { type: 'turn/start', seq: 0, time: 2, data: {} }
  const persistence = backend(async action => {
    if (action === 'DescribeSession') {
      return { Session: { SessionId: 'session-test', State: { CustomState: JSON.stringify({ dshHeader: header }) } } }
    }
    if (action === 'DescribeEvents') {
      return {
        Events: [{ EventId: 'event-0', Extensions: JSON.stringify({ dshEvent: event }) }],
        TotalCount: 1,
      }
    }
    throw new Error(`unexpected action ${action}`)
  })

  assert.deepEqual(await persistence.loadStored('session-test'), {
    meta: header,
    events: [event],
    revision: 'agent-runtime:session-test:1',
  })
})

test('loadStored rejects a non-contiguous DSH sequence', async () => {
  const persistence = backend(async action => {
    if (action === 'DescribeSession') {
      return {
        Session: {
          SessionId: 'session-test',
          State: { CustomState: JSON.stringify({ dshHeader: { version: 0, id: 'session-test', createdAt: 1 } }) },
        },
      }
    }
    return {
      Events: [{ EventId: 'event-1', Extensions: JSON.stringify({ dshEvent: { type: 'turn/end', seq: 1, time: 2, data: {} } }) }],
      TotalCount: 1,
    }
  })

  await assert.rejects(persistence.loadStored('session-test'), /non-contiguous/)
})

test('executeHands reuses the shared Session affinity and returns the Hands result', async () => {
  const calls = []
  const persistence = backend(async (action, payload) => {
    calls.push({ action, payload })
    return {}
  })
  persistence.handsDeploymentId = 'dpl-hands'
  persistence.describeSession = async brainSessionId => {
    assert.equal(brainSessionId, 'brain-session')
    return {
      SessionId: 'brain-session',
      Metadata: [
        { Name: 'ae.tencentcloud.com/brain-deployment-id', Value: 'dpl-brain' },
        { Name: 'ae.tencentcloud.com/hands-deployment-id', Value: 'dpl-hands' },
        { Name: 'ae.tencentcloud.com/hands-affinity-id', Value: 'affinity-a' },
      ],
    }
  }
  persistence.invokeHands = async (operation, args, affinityId) => {
    assert.equal(operation, 'workspace.read_file')
    assert.deepEqual(args, { path: 'result.txt' })
    assert.equal(affinityId, 'affinity-a')
    return { result: { path: 'result.txt', exists: true, content: '95' }, affinityId }
  }

  const result = await persistence.executeHands(
    'workspace.read_file',
    { path: 'result.txt' },
    {
      agent: { session: { header: { id: 'brain-session' } } },
      callId: 'call-1',
      signal: new AbortController().signal,
    },
  )

  assert.deepEqual(result, {
    sessionId: 'brain-session',
    path: 'result.txt',
    exists: true,
    content: '95',
  })
  assert.deepEqual(calls, [])
})

test('executeHands adds Hands metadata without replacing Brain metadata', async () => {
  const calls = []
  const persistence = backend(async (action, payload) => {
    calls.push({ action, payload })
    return {}
  })
  persistence.handsDeploymentId = 'dpl-hands'
  persistence.describeSession = async () => ({
    SessionId: 'brain-session',
    Metadata: [{ Name: 'ae.tencentcloud.com/brain-deployment-id', Value: 'dpl-brain' }],
  })
  persistence.invokeHands = async () => ({
    result: { path: 'result.txt', content: '95' },
    affinityId: 'affinity-a',
  })

  await persistence.executeHands(
    'workspace.write_file',
    { path: 'result.txt', content: '95' },
    {
      agent: { session: { header: { id: 'brain-session' } } },
      callId: 'call-1',
      signal: new AbortController().signal,
    },
  )

  const modify = calls.find(call => call.action === 'ModifySession')
  assert.deepEqual(modify.payload.Metadata, [
    { Name: 'ae.tencentcloud.com/brain-deployment-id', Value: 'dpl-brain' },
    { Name: 'ae.tencentcloud.com/hands-deployment-id', Value: 'dpl-hands' },
    { Name: 'ae.tencentcloud.com/hands-affinity-id', Value: 'affinity-a' },
  ])
})

test('executeHands omits null content when a workspace file does not exist', async () => {
  const persistence = backend(async () => ({}))
  persistence.handsDeploymentId = 'dpl-hands'
  persistence.describeSession = async () => ({
    SessionId: 'brain-session',
    Metadata: [
      { Name: 'ae.tencentcloud.com/hands-deployment-id', Value: 'dpl-hands' },
      { Name: 'ae.tencentcloud.com/hands-affinity-id', Value: 'affinity-a' },
    ],
  })
  persistence.invokeHands = async () => ({
    result: { path: 'missing.txt', exists: false, content: null },
    affinityId: 'affinity-a',
  })

  const result = await persistence.executeHands(
    'workspace.read_file',
    { path: 'missing.txt' },
    {
      agent: { session: { header: { id: 'brain-session' } } },
      callId: 'call-missing',
      signal: new AbortController().signal,
    },
  )

  assert.deepEqual(result, {
    sessionId: 'brain-session',
    path: 'missing.txt',
    exists: false,
  })
})

test('describeEvents ignores Hands events when restoring DSH history', async () => {
  const persistence = backend(async () => ({
    Events: [
      { EventId: 'hands-call', Extensions: '' },
      { EventId: 'dsh-0', Extensions: JSON.stringify({ dshEvent: { type: 'turn/start', seq: 0 } }) },
    ],
    TotalCount: 2,
  }))

  assert.deepEqual(await persistence.describeEvents('brain-session'), [
    { type: 'turn/start', seq: 0 },
  ])
})
