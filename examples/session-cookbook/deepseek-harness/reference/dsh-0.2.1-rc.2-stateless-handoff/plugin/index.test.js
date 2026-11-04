import assert from 'node:assert/strict'
import test from 'node:test'
import {
  SessionAlreadyExistsError,
  SessionAlreadyOwnedError,
  SessionFormatUnsupportedError,
  SessionHandleClosedError,
  SessionPersistenceCorruptionError,
  SessionPersistenceNotFoundError,
  SessionReadOnlyError,
} from '@deepseek-ai/dsh-session-persistence'
import { SESSION_FORMAT_VERSION } from '@deepseek-ai/dsh-session'
import { createHandoffController } from './handoff-controller.js'

const modulePath = process.env.PLUGIN_MODULE ?? './index.js'
const {
  AgentRuntimeBackendTracker,
  AgentRuntimeSessionPersistence,
  SessionPersistenceConflictError,
} = await import(modulePath)

function apiError(code) {
  return Object.assign(new Error(code), { code })
}

// An in-memory Session API with the service's retry semantics: a repeated
// CreateSession is a duplicate, and a repeated EventId is accepted only when the
// event is identical. DescribeSessions applies metadata filters server side.
function sessionStore() {
  const sessions = new Map()
  const calls = []
  const failures = []
  const request = async (action, payload) => {
    calls.push({ action, payload })
    const failure = failures.findIndex(item => item.action === action && item.when(payload))
    if (failure >= 0) throw failures.splice(failure, 1)[0].error
    if (action === 'DescribeSessions') {
      const filter = payload.Filters?.[0]
      const key = filter?.Name.replace(/^metadata:/, '')
      const rows = [...sessions.values()].filter(session => !filter
        || session.Metadata?.some(item => item.Name === key && filter.Values.includes(item.Value)))
      return { Sessions: rows.map(({ SessionId, Metadata }) => ({ SessionId, Metadata })), TotalCount: rows.length }
    }
    if (action === 'CreateSession') {
      if (sessions.has(payload.SessionId)) throw apiError('ResourceInUse.SessionIdDuplicate')
      sessions.set(payload.SessionId, { ...payload, events: [] })
      return {}
    }
    const row = sessions.get(payload.SessionId)
    if (!row) throw apiError('ResourceNotFound.SessionNotExist')
    if (action === 'DescribeSession') return { Session: row }
    if (action === 'AppendEvent') {
      const existing = row.events.find(event => event.EventId === payload.Event.EventId)
      if (existing) {
        if (JSON.stringify(existing) !== JSON.stringify(payload.Event)) throw apiError('ResourceInUse.EventIdDuplicate')
        return {}
      }
      row.events.push(payload.Event)
      return {}
    }
    if (action === 'DescribeEvents') {
      const page = row.events.slice(payload.Offset, payload.Offset + payload.Limit)
      return { Events: page, TotalCount: row.events.length }
    }
    throw new Error(`unexpected ${action}`)
  }
  const failNext = (action, error, when = () => true) => failures.push({ action, error, when })
  return { sessions, calls, request, failNext }
}

function backend(store, agentId) {
  const value = Object.create(AgentRuntimeSessionPersistence.prototype)
  value.spaceId = 'space-test'
  value.userId = 'user-test'
  value.agentId = agentId
  value.tracker = new AgentRuntimeBackendTracker('test')
  value.request = store.request
  return value
}

function header(id, extra = {}) {
  return { version: SESSION_FORMAT_VERSION, id, createdAt: 1, isSeeded: false, ...extra }
}

function turn(seq, turnNumber = 1) {
  return seq % 2 === 0
    ? { type: 'turn/start', seq, time: seq + 1, data: { turn: turnNumber } }
    : { type: 'turn/end', seq, time: seq + 1, data: { turn: turnNumber, reason: { kind: 'completed' } } }
}

function actions(store) {
  return store.calls.map(call => call.action)
}

test('appendEvents stores a readable projection and the original DSH event', async () => {
  const store = sessionStore()
  store.sessions.set('session-test', { SessionId: 'session-test', events: [] })
  const event = {
    type: 'user/message',
    seq: 0,
    time: 1,
    data: {
      id: 'msg-1',
      role: 'user',
      source: { kind: 'user', rpcId: 'rpc-1' },
      content: [{ type: 'text', text: 'hello' }],
    },
  }

  await backend(store).appendEvents('session-test', [event])

  const [call] = store.calls
  assert.equal(call.action, 'AppendEvent')
  assert.equal(call.payload.Event.EventId, 'dsh-session-test-0')
  assert.equal(call.payload.Event.Author, 'user')
  assert.equal(call.payload.Event.InvocationId, 'rpc-1')
  assert.equal(call.payload.Event.Content.Parts[0].Text, 'hello')
  assert.deepEqual(JSON.parse(call.payload.Event.Metadata), {
    source: 'deepseek-harness',
    dshEventType: 'user/message',
    dshSeq: 0,
  })
  assert.deepEqual(JSON.parse(call.payload.Event.Extensions).dshEvent, event)
})

test('appendEvents projects 0.2.1 assistant messages, attempts, tool calls, and tool results', async () => {
  const store = sessionStore()
  store.sessions.set('session-test', { SessionId: 'session-test', events: [] })
  const events = [
    {
      type: 'assistant/message',
      seq: 0,
      time: 1,
      data: {
        turn: 1,
        step: 1,
        stream: [],
        message: {
          id: 'msg-a',
          role: 'assistant',
          source: { kind: 'model', provider: 'custom', model: 'm' },
          content: [
            { type: 'reasoning', text: 'thinking' },
            { type: 'text', text: 'answer' },
            { type: 'tool-call', id: 'call-1', name: 'calculator', arguments: '{"a":37,"b":58}' },
          ],
        },
      },
    },
    { type: 'assistant/attempt', seq: 1, time: 2, data: { turn: 1, step: 1, stream: [] } },
    {
      type: 'tool/call',
      seq: 2,
      time: 3,
      data: { turn: 1, step: 1, callId: 'call-1', name: 'calculator', arguments: '{"a":37,"b":58}' },
    },
    {
      type: 'tool/result',
      seq: 3,
      time: 4,
      data: {
        turn: 1,
        step: 1,
        message: {
          id: 'msg-t',
          role: 'tool',
          source: { kind: 'tool', callId: 'call-1' },
          toolCallId: 'call-1',
          content: [{ type: 'text', text: '95' }],
        },
      },
    },
    { type: 'turn/end', seq: 4, time: 5, data: { turn: 1, reason: { kind: 'completed' } } },
  ]

  await backend(store).appendEvents('session-test', events)

  const stored = store.calls.map(call => call.payload.Event)
  assert.deepEqual(stored[0].Content.Parts, [
    { Text: 'thinking', Thought: true },
    { Text: 'answer' },
    { FunctionCall: JSON.stringify({ Name: 'calculator', Args: { a: 37, b: 58 } }) },
  ])
  assert.equal(stored[1].Content, undefined)
  assert.equal(JSON.parse(stored[1].Metadata).Partial, true)
  assert.deepEqual(JSON.parse(stored[2].Content.Parts[0].FunctionCall), { Name: 'calculator', Args: { a: 37, b: 58 } })
  assert.equal(stored[3].InvocationId, 'call-1')
  assert.deepEqual(JSON.parse(stored[3].Content.Parts[0].FunctionResponse), {
    Name: 'call-1',
    Response: { content: '95', isError: false },
  })
  assert.deepEqual(JSON.parse(stored[4].Metadata), {
    source: 'deepseek-harness',
    dshEventType: 'turn/end',
    dshSeq: 4,
    Turn: 1,
    TurnComplete: true,
    Interrupted: false,
  })
})

test('appendEvents projects turn errors, interrupted turns, and tool failures', async () => {
  const store = sessionStore()
  store.sessions.set('session-test', { SessionId: 'session-test', events: [] })
  const toolMessage = isError => ({
    id: 'msg-t',
    role: 'tool',
    source: { kind: 'tool', callId: 'call-1' },
    toolCallId: 'call-1',
    isError,
    content: [{ type: 'text', text: 'command failed' }],
  })

  await backend(store).appendEvents('session-test', [
    { type: 'turn/end', seq: 0, time: 1, data: { turn: 1, reason: { kind: 'error', error: { code: 'AUTH', message: 'denied' } } } },
    { type: 'turn/end', seq: 1, time: 2, data: { turn: 2, reason: { kind: 'interrupted' } } },
    { type: 'tool/result', seq: 2, time: 3, data: { turn: 3, step: 1, message: toolMessage(true) } },
    {
      type: 'tool/result',
      seq: 3,
      time: 4,
      data: { turn: 3, step: 1, message: toolMessage(true), error: { name: 'Timeout', code: 'TOOL_TIMEOUT', reason: 'took too long' } },
    },
  ])

  const stored = store.calls.map(call => call.payload.Event)
  assert.equal(stored[0].ErrorCode, 'AUTH')
  assert.equal(stored[0].ErrorMessage, 'denied')
  assert.equal(JSON.parse(stored[1].Metadata).Interrupted, true)
  assert.equal(stored[2].ErrorCode, 'TOOL_ERROR')
  assert.equal(stored[2].ErrorMessage, 'command failed')
  assert.equal(stored[3].ErrorCode, 'TOOL_TIMEOUT')
  assert.equal(stored[3].ErrorMessage, 'took too long')
})

test('create defers CreateSession to the first append and the log reopens from the API', async () => {
  const store = sessionStore()
  const persistence = backend(store)
  const handle = await persistence.create(header('session-a', { cwd: '/workspace' }))

  assert.deepEqual(actions(store), ['DescribeSession'])
  assert.equal((await persistence.stat('session-a')).header.id, 'session-a')

  await handle.append([turn(0), turn(1)])
  assert.deepEqual(actions(store).slice(1), ['CreateSession', 'AppendEvent', 'AppendEvent'])
  assert.deepEqual(JSON.parse(store.sessions.get('session-a').State.CustomState), {
    dshHeader: header('session-a', { cwd: '/workspace' }),
  })
  assert.deepEqual((await handle.read()).events, [turn(0), turn(1)])
  await handle.close()

  const reopened = await backend(store).open('session-a', 'write')
  assert.deepEqual(reopened.header, header('session-a', { cwd: '/workspace' }))
  assert.equal(reopened.inheritedEventCount, 0)
  const { eventState, events } = await reopened.read()
  assert.equal(eventState, 'shared-frozen')
  assert.deepEqual(events, [turn(0), turn(1)])
  assert.ok(Object.isFrozen(events[0].data))
  await reopened.append([turn(2, 2)])
  assert.equal(store.sessions.get('session-a').events.length, 3)
  await reopened.close()
})

test('a created Session that is closed without writes never existed', async () => {
  const store = sessionStore()
  const persistence = backend(store)
  const handle = await persistence.create(header('session-empty'))
  assert.equal((await persistence.list()).length, 1)
  await handle.close()

  assert.equal(store.sessions.size, 0)
  assert.equal(await persistence.stat('session-empty'), undefined)
  assert.deepEqual(await persistence.list(), [])
  await assert.rejects(handle.read(), SessionHandleClosedError)
})

test('flush materializes an empty created Session', async () => {
  const store = sessionStore()
  const persistence = backend(store)
  const handle = await persistence.create(header('session-flushed'))
  await handle.flush()
  await handle.flush()
  await handle.close()

  assert.equal(actions(store).filter(action => action === 'CreateSession').length, 1)
  assert.deepEqual((await persistence.list()).map(snapshot => snapshot.header.id), ['session-flushed'])
})

test('one writer per Session and no duplicate creation', async () => {
  const store = sessionStore()
  const persistence = backend(store)
  const created = await persistence.create(header('session-owned'))
  await assert.rejects(persistence.create(header('session-owned')), SessionAlreadyExistsError)
  await assert.rejects(persistence.open('session-owned', 'write'), SessionAlreadyOwnedError)
  await created.append([turn(0)])
  await created.close()

  const writer = await persistence.open('session-owned', 'write')
  await assert.rejects(persistence.open('session-owned', 'write'), SessionAlreadyOwnedError)
  await assert.rejects(backend(store).create(header('session-owned')), SessionAlreadyExistsError)
  await writer.close()
  await (await persistence.open('session-owned', 'write')).close()
  await assert.rejects(persistence.open('session-missing', 'write'), SessionPersistenceNotFoundError)
  await (await persistence.open('session-owned', 'write')).close()
})

test('append refuses gaps and read handles refuse writes', async () => {
  const store = sessionStore()
  const persistence = backend(store)
  const handle = await persistence.create(header('session-gap'))
  await assert.rejects(handle.append([turn(1)]), /append seq mismatch/)
  await handle.append([turn(0)])
  await handle.close()

  const reader = await persistence.open('session-gap', 'read')
  await assert.rejects(reader.append([turn(1)]), SessionReadOnlyError)
  await assert.rejects(reader.flush(), SessionReadOnlyError)
  await reader.close()
})

test('read handles see the in-process writer log before it reaches the API', async () => {
  const store = sessionStore()
  const persistence = backend(store)
  const writer = await persistence.create(header('session-live'))
  const reader = await persistence.open('session-live', 'read')
  assert.deepEqual((await reader.read()).events, [])

  await writer.append([turn(0), turn(1)])
  assert.deepEqual((await reader.read(1)).events, [turn(1)])
  await writer.close()
  assert.deepEqual((await reader.read()).events, [turn(0), turn(1)])
  await reader.close()
})

test('a failed batch keeps the cursor and its retry resends the stored prefix', async () => {
  const store = sessionStore()
  const persistence = backend(store)
  const handle = await persistence.create(header('session-retry'))
  store.failNext('AppendEvent', new Error('write interrupted'), payload => payload.Event.EventId.endsWith('-1'))

  await assert.rejects(handle.append([turn(0), turn(1)]), /write interrupted/)
  assert.equal(store.sessions.get('session-retry').events.length, 1)
  assert.deepEqual((await handle.read()).events, [])

  await handle.append([turn(0), turn(1)])
  assert.deepEqual(store.sessions.get('session-retry').events.map(event => event.EventId), [
    'dsh-session-retry-0',
    'dsh-session-retry-1',
  ])
  await handle.close()
})

test('a retried CreateSession accepts its own header and refuses another', async () => {
  const store = sessionStore()
  const persistence = backend(store)
  const handle = await persistence.create(header('session-race'))
  store.sessions.set('session-race', {
    SessionId: 'session-race',
    State: { CustomState: JSON.stringify({ dshHeader: header('session-race') }) },
    events: [],
  })
  await handle.flush()
  await handle.close()

  const other = await backend(store).create(header('session-other'))
  store.sessions.set('session-other', {
    SessionId: 'session-other',
    State: { CustomState: JSON.stringify({ dshHeader: header('session-other', { createdAt: 2 }) }) },
    events: [],
  })
  await assert.rejects(other.flush(), SessionAlreadyExistsError)
})

test('live events batch through the handle and session/flush drains them', async () => {
  const store = sessionStore()
  const persistence = backend(store)
  const handle = await persistence.create(header('session-routed'))
  handle.enqueueLive(turn(0), assert.fail)
  handle.enqueueLive(turn(1), assert.fail)
  assert.equal(store.sessions.size, 0)

  await persistence.flush()
  assert.equal(store.sessions.get('session-routed').events.length, 2)

  handle.enqueueLive(turn(2, 2), assert.fail)
  await handle.close()
  assert.equal(store.sessions.get('session-routed').events.length, 3)
})

test('a failed live drain keeps its events for the next flush', async () => {
  const store = sessionStore()
  const persistence = backend(store)
  const handle = await persistence.create(header('session-drain'))
  store.failNext('CreateSession', new Error('network down'))
  handle.enqueueLive(turn(0), () => {})

  await assert.rejects(persistence.flush(), AggregateError)
  assert.equal(handle.buffered.length, 1)
  await persistence.flush()
  assert.equal(store.sessions.get('session-drain').events.length, 1)
  await handle.close()
})

test('an EventId conflict makes the handle permanent and stops further writes', async () => {
  const store = sessionStore()
  const persistence = backend(store)
  const handle = await persistence.create(header('session-conflicted'))
  await handle.append([turn(0)])
  // Another writer stored different content at the next EventId first.
  store.sessions.get('session-conflicted').events.push({
    EventId: 'dsh-session-conflicted-1',
    InvocationId: 'other',
    Author: 'other',
  })

  await assert.rejects(handle.append([turn(1)]), SessionPersistenceConflictError)
  assert.ok(handle.conflict instanceof SessionPersistenceConflictError)
  assert.equal(handle.buffered.length, 0)

  await assert.rejects(handle.append([turn(2, 2)]), SessionPersistenceConflictError)
  await assert.rejects(handle.flush(), SessionPersistenceConflictError)

  let notified
  handle.enqueueLive(turn(2, 2), error => { notified = error })
  assert.ok(notified instanceof SessionPersistenceConflictError)
  assert.equal(handle.buffered.length, 0)

  let reportedAgain
  handle.enqueueLive(turn(2, 2), error => { reportedAgain = error })
  assert.equal(reportedAgain, undefined)

  await handle.close()
  assert.equal(persistence.tracker.writers.has('session-conflicted'), false)
  const reopened = await backend(store).open('session-conflicted', 'write')
  await reopened.close()
})

test('a live drain conflict drops the uncommitted batch instead of retrying it', async () => {
  const store = sessionStore()
  const persistence = backend(store)
  const handle = await persistence.create(header('session-live-conflict'))
  await handle.flush()

  store.sessions.get('session-live-conflict').events.push({
    EventId: 'dsh-session-live-conflict-0',
    InvocationId: 'other',
    Author: 'other',
  })
  handle.enqueueLive(turn(0), () => {})

  await assert.rejects(persistence.flush(), AggregateError)
  assert.ok(handle.conflict instanceof SessionPersistenceConflictError)
  assert.equal(handle.buffered.length, 0)
  assert.equal(store.sessions.get('session-live-conflict').events.length, 1)

  await handle.close()
  assert.equal(persistence.tracker.writers.has('session-live-conflict'), false)
})

test('releaseWriter closes the write handle and releases the in-process claim', async () => {
  const store = sessionStore()
  const persistence = backend(store)
  const handle = await persistence.create(header('session-release'))
  await handle.append([turn(0)])
  assert.equal(persistence.tracker.writers.has('session-release'), true)

  await persistence.releaseWriter('session-release')
  assert.equal(persistence.tracker.writers.has('session-release'), false)
  await assert.rejects(handle.read(), SessionHandleClosedError)

  const reopened = await persistence.open('session-release', 'write')
  await reopened.close()
})

test('writerCursor reports the durable cursor of the in-process writer', async () => {
  const store = sessionStore()
  const persistence = backend(store)
  assert.equal(persistence.writerCursor('session-cursor'), undefined)

  const handle = await persistence.create(header('session-cursor'))
  assert.equal(persistence.writerCursor('session-cursor'), 0)
  await handle.append([turn(0), turn(1)])
  assert.equal(persistence.writerCursor('session-cursor'), 2)
  await handle.close()
  assert.equal(persistence.writerCursor('session-cursor'), undefined)
})

test('eventCount reports the stored count for the pre-turn freshness check', async () => {
  const store = sessionStore()
  const persistence = backend(store)
  const handle = await persistence.create(header('session-count'))
  await handle.flush()
  assert.equal(await persistence.eventCount('session-count'), 0)

  await handle.append([turn(0), turn(1)])
  assert.equal(await persistence.eventCount('session-count'), 2)
  await handle.close()
})

test('handoffCheck reports fresh, stale, local-ahead, and not-found states', async () => {
  const store = sessionStore()
  const persistence = backend(store)
  const handle = await persistence.create(header('session-handoff-state'))
  await handle.append([turn(0), turn(1)])

  const fresh = await persistence.handoffCheck('session-handoff-state', 2)
  assert.equal(fresh.state, 'fresh')
  assert.equal(fresh.cloudEventCount, 2)
  assert.equal(fresh.localEventCount, 2)
  assert.equal(fresh.turnClosed, true)
  assert.equal((await persistence.handoffCheck('session-handoff-state', 1)).state, 'stale')
  assert.equal((await persistence.handoffCheck('session-handoff-state', 3)).state, 'local-ahead')
  assert.equal((await persistence.handoffCheck('session-missing', 0)).state, 'not-found')
  await handle.close()
})

test('handoffCheck reports an open turn instead of treating it as complete', async () => {
  const store = sessionStore()
  const persistence = backend(store)
  const handle = await persistence.create(header('session-open'))
  await handle.append([turn(0)])

  const check = await persistence.handoffCheck('session-open', 1)
  assert.equal(check.state, 'fresh')
  assert.equal(check.turnClosed, false)
  assert.equal(check.lastEvent.type, 'turn/start')
  await handle.close()
})

test('handoffCheck reads the cloud tail only when the local view is behind', async () => {
  const store = sessionStore()
  const persistence = backend(store)
  const handle = await persistence.create(header('session-one-read'))
  await handle.append([turn(0), turn(1)])

  const freshStart = store.calls.length
  await persistence.handoffCheck('session-one-read', 2)
  const freshReads = store.calls.slice(freshStart).filter(call => call.action === 'DescribeEvents')
  assert.equal(freshReads.length, 1)

  const other = backend(store)
  const otherHandle = await other.open('session-one-read', 'write')
  await otherHandle.append([turn(2, 2), turn(3, 2)])
  await otherHandle.close()

  const staleStart = store.calls.length
  const stale = await persistence.handoffCheck('session-one-read', 2)
  assert.equal(stale.state, 'stale')
  const staleReads = store.calls.slice(staleStart).filter(call => call.action === 'DescribeEvents')
  assert.equal(staleReads.length, 2)
  await handle.close()
})

test('handoffCheck uses the local tail for a local-ahead view', async () => {
  const store = sessionStore()
  const persistence = backend(store)
  const handle = await persistence.create(header('session-local-tail'))
  await handle.append([turn(0), turn(1)])

  const start = store.calls.length
  const check = await persistence.handoffCheck('session-local-tail', 3)
  assert.equal(check.state, 'local-ahead')
  assert.equal(check.turnClosed, true)
  const reads = store.calls.slice(start).filter(call => call.action === 'DescribeEvents')
  assert.equal(reads.length, 1)
  await handle.close()
})

test('a second replica handoff at a turn boundary makes the stale writer stop', async () => {
  const store = sessionStore()
  const replicaA = backend(store)
  const handleA = await replicaA.create(header('session-handoff'))
  await handleA.append([turn(0), turn(1)])
  assert.equal((await replicaA.handoffCheck('session-handoff', 2)).state, 'fresh')

  // Replica B shares the Session API but has its own in-process tracker.
  const replicaB = backend(store)
  const handleB = await replicaB.open('session-handoff', 'write')
  await handleB.append([turn(2, 2), turn(3, 2)])
  await handleB.close()

  const check = await replicaA.handoffCheck('session-handoff', 2)
  assert.equal(check.state, 'stale')
  assert.equal(check.cloudEventCount, 4)
  assert.equal(check.turnClosed, true)

  const staleEvent = {
    type: 'user/message',
    seq: 2,
    time: 3,
    data: {
      id: 'msg-a',
      role: 'user',
      source: { kind: 'user', rpcId: 'rpc-a' },
      content: [{ type: 'text', text: 'from replica A' }],
    },
  }
  await assert.rejects(handleA.append([staleEvent]), SessionPersistenceConflictError)
  assert.ok(handleA.conflict instanceof SessionPersistenceConflictError)
  await handleA.close()
  assert.equal(replicaA.tracker.writers.has('session-handoff'), false)
})

test('the controller rebuilds a stale replica and it continues after resume', async () => {
  const store = sessionStore()
  const replicaA = backend(store)
  const handleA = await replicaA.create(header('session-rebuild'))
  await handleA.append([turn(0), turn(1)])

  const replicaB = backend(store)
  const handleB = await replicaB.open('session-rebuild', 'write')
  await handleB.append([turn(2, 2), turn(3, 2)])
  await handleB.close()

  let resumed
  const host = {
    localEventCount: async () => replicaA.writerCursor('session-rebuild'),
    invalidate: async () => { await replicaA.releaseWriter('session-rebuild') },
    resume: async () => {
      resumed = await replicaA.open('session-rebuild', 'write')
      return resumed
    },
  }
  const controller = createHandoffController({ persistence: replicaA, host })

  const decision = await controller.preflight('session-rebuild')
  assert.equal(decision.action, 'rebuilt')
  assert.equal(resumed.state.cursor, 4)

  await resumed.append([turn(4, 3), turn(5, 3)])
  assert.equal(store.sessions.get('session-rebuild').events.length, 6)
  await resumed.close()
})

test('the controller recovers a conflicted handle and the session continues', async () => {
  const store = sessionStore()
  const replicaA = backend(store)
  const handleA = await replicaA.create(header('session-recover'))
  await handleA.append([turn(0), turn(1)])

  const replicaB = backend(store)
  const handleB = await replicaB.open('session-recover', 'write')
  await handleB.append([turn(2, 2), turn(3, 2)])
  await handleB.close()

  const staleEvent = {
    type: 'user/message',
    seq: 2,
    time: 3,
    data: {
      id: 'msg-b',
      role: 'user',
      source: { kind: 'user', rpcId: 'rpc-b' },
      content: [{ type: 'text', text: 'from replica A' }],
    },
  }
  await assert.rejects(handleA.append([staleEvent]), SessionPersistenceConflictError)
  assert.ok(handleA.conflict instanceof SessionPersistenceConflictError)

  let resumed
  const host = {
    localEventCount: async () => replicaA.writerCursor('session-recover'),
    invalidate: async () => { await replicaA.releaseWriter('session-recover') },
    resume: async () => {
      resumed = await replicaA.open('session-recover', 'write')
      return resumed
    },
  }
  const controller = createHandoffController({ persistence: replicaA, host })

  const result = await controller.recover('session-recover', 'conflict')
  assert.equal(result.action, 'rebuilt')
  assert.equal(resumed.state.cursor, 4)

  await resumed.append([turn(4, 3), turn(5, 3)])
  assert.equal(store.sessions.get('session-recover').events.length, 6)
  await resumed.close()
})

test('seeded Sessions store their inherited prefix length', async () => {
  const store = sessionStore()
  const persistence = backend(store)
  const seeded = header('session-fork', { isSeeded: true, parentSession: 'session-parent' })
  await assert.rejects(persistence.create(seeded), /requires an inherited event count/)
  await assert.rejects(persistence.create(header('session-plain'), { inheritedEventCount: 2 }), /must be 0/)

  const handle = await persistence.create(seeded, { inheritedEventCount: 2 })
  assert.equal(handle.inheritedEventCount, 2)
  await handle.append([turn(0), turn(1)])
  await handle.close()

  assert.equal(JSON.parse(store.sessions.get('session-fork').State.CustomState).dshInheritedEventCount, 2)
  const reopened = await backend(store).open('session-fork', 'read')
  assert.equal(reopened.inheritedEventCount, 2)
  await reopened.close()
})

test('Sessions written by DSH 0.1.x are refused on open and hidden from listing', async () => {
  const store = sessionStore()
  store.sessions.set('session-v0', {
    SessionId: 'session-v0',
    State: { CustomState: JSON.stringify({ dshHeader: { version: 0, id: 'session-v0', createdAt: 1 } }) },
    events: [],
  })
  store.sessions.set('session-other-app', {
    SessionId: 'session-other-app',
    State: { CustomState: JSON.stringify({ owner: 'another-application' }) },
    events: [],
  })
  const persistence = backend(store)

  await assert.rejects(persistence.open('session-v0', 'write'), SessionFormatUnsupportedError)
  assert.equal(await persistence.stat('session-v0'), undefined)
  assert.equal(await persistence.stat('session-other-app'), undefined)
  assert.deepEqual(await persistence.list(), [])
  // A refused write open must not leave its ownership claim behind.
  assert.equal(persistence.tracker.writers.size, 0)
})

test('a non-contiguous stored log is reported as corruption', async () => {
  const store = sessionStore()
  store.sessions.set('session-hole', {
    SessionId: 'session-hole',
    State: { CustomState: JSON.stringify({ dshHeader: header('session-hole') }) },
    events: [{ EventId: 'dsh-session-hole-1', Extensions: JSON.stringify({ dshEvent: turn(1) }) }],
  })
  await assert.rejects(backend(store).open('session-hole', 'read'), SessionPersistenceCorruptionError)
})

test('restoring history ignores Events written by other applications', async () => {
  const store = sessionStore()
  store.sessions.set('session-mixed', {
    SessionId: 'session-mixed',
    State: { CustomState: JSON.stringify({ dshHeader: header('session-mixed') }) },
    events: [
      { EventId: 'other-call', Extensions: '' },
      { EventId: 'dsh-session-mixed-0', Extensions: JSON.stringify({ dshEvent: turn(0) }) },
    ],
  })
  const reader = await backend(store).open('session-mixed', 'read')
  assert.deepEqual((await reader.read()).events, [turn(0)])
  await reader.close()
})

test('headers are read once per Session so listing stays under the API rate limit', async () => {
  const store = sessionStore()
  const persistence = backend(store)
  const handle = await persistence.create(header('session-cached'))
  await handle.flush()
  await handle.close()

  const other = backend(store)
  await other.list()
  await other.list()
  const [snapshot] = await other.list()
  assert.equal(actions(store).filter(action => action === 'DescribeSession').length, 2)
  assert.equal(snapshot.revision, 'agent-runtime:session-cached:0')
})

test('SESSION_AGENT_ID tags new Sessions and scopes listing and opening to them', async () => {
  const store = sessionStore()
  for (const id of ['a', 'b']) {
    const handle = await backend(store, id).create(header(id))
    await handle.append([turn(0)])
    await handle.close()
  }
  const legacy = await backend(store, undefined).create(header('legacy'))
  await legacy.flush()
  await legacy.close()

  assert.deepEqual(store.sessions.get('a').Metadata, [{ Name: 'example.com/dsh-agent-id', Value: 'a' }])
  assert.equal(store.sessions.get('legacy').Metadata, undefined)
  assert.deepEqual((await backend(store, 'a').list()).map(snapshot => snapshot.header.id), ['a'])
  assert.deepEqual((await backend(store, undefined).list()).map(snapshot => snapshot.header.id), ['a', 'b', 'legacy'])
  assert.equal(await backend(store, 'a').stat('b'), undefined)
  for (const id of ['b', 'legacy']) {
    await assert.rejects(backend(store, 'a').open(id, 'read'), /belongs to another SESSION_AGENT_ID/)
  }
})

test('request retries Session API calls rejected by the rate limit', async () => {
  const persistence = Object.create(AgentRuntimeSessionPersistence.prototype)
  persistence.retryDelayMs = () => 0
  let attempts = 0
  persistence.client = {
    request: async () => {
      attempts += 1
      if (attempts < 3) throw apiError('RequestLimitExceeded')
      return { ok: true }
    },
  }
  assert.deepEqual(await persistence.request('DescribeSession', {}), { ok: true })
  assert.equal(attempts, 3)

  persistence.client = { request: async () => { throw apiError('AuthFailure') } }
  await assert.rejects(persistence.request('DescribeSession', {}), /AuthFailure/)
})
