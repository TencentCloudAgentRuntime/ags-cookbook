import assert from 'node:assert/strict'
import test from 'node:test'

const modulePath = process.env.PLUGIN_MODULE ?? './index.js'
const { AgentRuntimeSessionPersistence } = await import(modulePath)

function backend(request) {
  const value = Object.create(AgentRuntimeSessionPersistence.prototype)
  value.spaceId = 'space-test'
  value.userId = 'user-test'
  value.brainDeploymentIdPromise = undefined
  value.request = request
  return value
}

test('appendEvents stores a readable projection and the original DSH event', async () => {
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




test('describeEvents ignores non-DSH events when restoring history', async () => {
  const persistence = backend(async () => ({
    Events: [
      { EventId: 'other-call', Extensions: '' },
      { EventId: 'dsh-0', Extensions: JSON.stringify({ dshEvent: { type: 'turn/start', seq: 0 } }) },
    ],
    TotalCount: 2,
  }))

  assert.deepEqual(await persistence.describeEvents('brain-session'), [
    { type: 'turn/start', seq: 0 },
  ])
})

test('list reads DSH headers through DescribeSession because DescribeSessions omits State', async () => {
  const header = { version: 0, id: 'session-dsh', createdAt: 1 }
  const stateById = {
    'session-dsh': { CustomState: JSON.stringify({ dshHeader: header }) },
    'session-other': { CustomState: JSON.stringify({ owner: 'another-application' }) },
  }
  const persistence = backend(async (action, payload) => {
    if (action === 'DescribeSessions') {
      return {
        Sessions: Object.keys(stateById).map(SessionId => ({ SessionId })),
        TotalCount: 2,
      }
    }
    if (action === 'DescribeSession') {
      return { Session: { SessionId: payload.SessionId, State: stateById[payload.SessionId] } }
    }
    if (action === 'DescribeEvents') return { Events: [], TotalCount: 0 }
    throw new Error(`unexpected ${action}`)
  })

  assert.deepEqual(await persistence.list(new AbortController().signal), [header])
  const snapshots = await persistence.listSnapshots(new AbortController().signal)
  assert.deepEqual(snapshots.map(snapshot => snapshot.header), [header])
})

test('headers are read once per Session so listing stays under the API rate limit', async () => {
  const header = { version: 0, id: 'session-dsh', createdAt: 1 }
  const calls = []
  const persistence = backend(async (action, payload) => {
    calls.push(action)
    if (action === 'DescribeSessions') return { Sessions: [{ SessionId: 'session-dsh' }], TotalCount: 1 }
    if (action === 'DescribeSession') {
      return {
        Session: {
          SessionId: payload.SessionId,
          EventCount: 0,
          State: { CustomState: JSON.stringify({ dshHeader: header }) },
        },
      }
    }
    if (action === 'DescribeEvents') return { Events: [], TotalCount: 3 }
    throw new Error(`unexpected ${action}`)
  })

  await persistence.list()
  await persistence.list()
  const [snapshot] = await persistence.listSnapshots()
  assert.equal(calls.filter(action => action === 'DescribeSession').length, 1)
  assert.equal(snapshot.revision, 'agent-runtime:session-dsh:3')
})

test('request retries Session API calls rejected by the rate limit', async () => {
  const persistence = Object.create(AgentRuntimeSessionPersistence.prototype)
  persistence.retryDelayMs = () => 0
  let attempts = 0
  persistence.client = {
    request: async () => {
      attempts += 1
      if (attempts < 3) throw Object.assign(new Error('frequency limit'), { code: 'RequestLimitExceeded' })
      return { ok: true }
    },
  }
  assert.deepEqual(await persistence.request('DescribeSession', {}), { ok: true })
  assert.equal(attempts, 3)

  persistence.client = { request: async () => { throw Object.assign(new Error('denied'), { code: 'AuthFailure' }) } }
  await assert.rejects(persistence.request('DescribeSession', {}), /denied/)
})

test('listSnapshots does not hide revision lookup failures', async () => {
  const header = { version: 0, id: 'session-test', createdAt: 1 }
  const persistence = backend(async action => {
    if (action === 'DescribeSessions') {
      return {
        Sessions: [{
          SessionId: 'session-test',
          State: { CustomState: JSON.stringify({ dshHeader: header }) },
        }],
        TotalCount: 1,
      }
    }
    throw new Error('Session API unavailable')
  })

  await assert.rejects(
    persistence.listSnapshots(new AbortController().signal),
    /Session API unavailable/,
  )
})

test('appendBatch creates a Session header without Deployment or tool dependencies', async () => {
  const calls = []
  const persistence = backend(async (action, payload) => { calls.push({ action, payload }); return {} })
  const meta = { id: 'session-test', version: 0, createdAt: 1 }
  await persistence.appendBatch(meta, [{ type: 'turn/start', seq: 0, data: {} }], false)
  assert.deepEqual(calls.map(call => call.action), ['CreateSession', 'AppendEvent'])
  assert.deepEqual(JSON.parse(calls[0].payload.State.CustomState), { dshHeader: meta })
  assert.equal(calls[0].payload.Metadata, undefined)
  assert.deepEqual(AgentRuntimeSessionPersistence.inject, ['sessions'])
})

test('a failed append is surfaced and does not silently skip to the next event', async () => {
  const calls = []
  const persistence = backend(async (action, payload) => {
    calls.push(payload.Event.EventId)
    if (calls.length === 2) throw new Error('write interrupted')
    return {}
  })
  await assert.rejects(persistence.appendBatch({ id: 'session-test' },
    [0, 1, 2].map(seq => ({ type: 'turn/start', seq, data: {} })), true), /write interrupted/)
  assert.deepEqual(calls, ['dsh-session-test-0', 'dsh-session-test-1'])
})
