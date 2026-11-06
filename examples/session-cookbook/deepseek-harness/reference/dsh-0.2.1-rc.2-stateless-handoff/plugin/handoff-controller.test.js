import assert from 'node:assert/strict'
import test from 'node:test'
import { attachConflictRecovery, createHandoffController, HandoffBusyError } from './handoff-controller.js'

function check(state, turnState = 'closed') {
  return {
    state,
    cloudEventCount: 2,
    localEventCount: 2,
    turnState,
    turnClosed: turnState === 'closed',
  }
}

function fakePersistence(checks, { releaseError } = {}) {
  const calls = []
  let index = 0
  return {
    calls,
    async handoffCheck(sessionId, localEventCount) {
      calls.push(['handoffCheck', sessionId, localEventCount])
      return Array.isArray(checks) ? checks[Math.min(index++, checks.length - 1)] : checks
    },
    async releaseWriter(sessionId) {
      calls.push(['releaseWriter', sessionId])
      if (releaseError !== undefined) throw releaseError
    },
  }
}

function fakeHost({ localEventCount = 2, invalidate, resume, flush, liveAgentStatus, liveTurnState } = {}) {
  const calls = []
  const host = {
    calls,
    async localEventCount(sessionId) {
      calls.push(['localEventCount', sessionId])
      return localEventCount
    },
    async invalidate(sessionId) {
      calls.push(['invalidate', sessionId])
      if (invalidate !== undefined) await invalidate(sessionId)
    },
    async resume(sessionId) {
      calls.push(['resume', sessionId])
      return resume !== undefined ? resume(sessionId) : { generation: `${sessionId}-new` }
    },
  }
  if (flush !== undefined) {
    host.flush = async sessionId => {
      calls.push(['flush', sessionId])
      await flush(sessionId)
    }
  }
  if (liveAgentStatus !== undefined) {
    host.liveAgentStatus = async sessionId => {
      calls.push(['liveAgentStatus', sessionId])
      return typeof liveAgentStatus === 'function' ? liveAgentStatus(sessionId) : liveAgentStatus
    }
  }
  if (liveTurnState !== undefined) {
    host.liveTurnState = async sessionId => {
      calls.push(['liveTurnState', sessionId])
      return typeof liveTurnState === 'function' ? liveTurnState(sessionId) : liveTurnState
    }
  }
  return host
}

test('preflight runs when the stored log matches and the turn is closed', async () => {
  const persistence = fakePersistence(check('fresh'))
  const host = fakeHost()
  const controller = createHandoffController({ persistence, host })

  const result = await controller.preflight('session-a')
  assert.equal(result.action, 'run')
  assert.deepEqual(host.calls, [['localEventCount', 'session-a']])
  assert.deepEqual(persistence.calls, [['handoffCheck', 'session-a', 2]])
})

test('preflight runs a fresh open turn while this replica is driving it', async () => {
  const persistence = fakePersistence(check('fresh', 'open'))
  const host = fakeHost({ liveAgentStatus: 'running', liveTurnState: 'open' })
  const controller = createHandoffController({ persistence, host })

  const result = await controller.preflight('session-queue')
  assert.equal(result.action, 'run')
  // No cloud read: our own running turn already holds its claim.
  assert.deepEqual(host.calls.map(call => call[0]), ['liveAgentStatus'])
  assert.equal(persistence.calls.length, 0)
})

test('preflight refuses a fresh open turn when the live Agent is idle', async () => {
  const persistence = fakePersistence(check('fresh', 'open'))
  const host = fakeHost({ liveAgentStatus: 'idle', liveTurnState: 'open' })
  const controller = createHandoffController({ persistence, host })

  await assert.rejects(controller.preflight('session-crash'), HandoffBusyError)
  assert.equal(host.calls.some(call => call[0] === 'invalidate'), false)
})

test('preflight refuses a fresh open turn when the host has no liveness ports', async () => {
  const persistence = fakePersistence(check('fresh', 'open'))
  const host = fakeHost()
  const controller = createHandoffController({ persistence, host })

  await assert.rejects(controller.preflight('session-no-liveness'), HandoffBusyError)
})

test('preflight runs a fresh Session with no turn yet', async () => {
  const persistence = fakePersistence(check('fresh', 'none'))
  const host = fakeHost({ liveAgentStatus: 'idle', liveTurnState: 'none' })
  const controller = createHandoffController({ persistence, host })

  const result = await controller.preflight('session-new')
  assert.equal(result.action, 'run')
})

test('preflight rebuilds a stale generation whose turn is closed', async () => {
  const persistence = fakePersistence(check('stale'))
  const host = fakeHost({ liveAgentStatus: 'idle', liveTurnState: 'open' })
  const controller = createHandoffController({ persistence, host })

  const result = await controller.preflight('session-b')
  assert.equal(result.action, 'rebuilt')
  assert.deepEqual(result.generation, { generation: 'session-b-new' })
  assert.deepEqual(host.calls.map(call => call[0]), ['liveAgentStatus', 'localEventCount', 'invalidate', 'resume'])
  assert.deepEqual(persistence.calls.map(call => call[0]), ['handoffCheck', 'releaseWriter'])
})

test('preflight refuses a stale open turn instead of closing it', async () => {
  const persistence = fakePersistence(check('stale', 'open'))
  const host = fakeHost({ liveAgentStatus: 'idle', liveTurnState: 'closed' })
  const controller = createHandoffController({ persistence, host })

  await assert.rejects(controller.preflight('session-c'), HandoffBusyError)
  assert.deepEqual(host.calls.map(call => call[0]), ['liveAgentStatus', 'localEventCount'])
  assert.equal(persistence.calls.some(call => call[0] === 'releaseWriter'), false)
})

test('a turn this replica is running is never rebuilt, even when the cloud log is ahead', async () => {
  const persistence = fakePersistence(check('stale'))
  const host = fakeHost({ liveAgentStatus: 'running' })
  const controller = createHandoffController({ persistence, host })

  const result = await controller.preflight('session-running')
  assert.equal(result.action, 'run')
  assert.equal(host.calls.some(call => call[0] === 'invalidate'), false)
  assert.equal(persistence.calls.length, 0, 'no cloud read while our own turn is running')
})

test('preflight flushes a local-ahead log and rechecks', async () => {
  const persistence = fakePersistence([check('local-ahead'), check('fresh')])
  const host = fakeHost({ flush: async () => {} })
  const controller = createHandoffController({ persistence, host })

  const result = await controller.preflight('session-e')
  assert.equal(result.action, 'run')
  assert.deepEqual(host.calls.map(call => call[0]), ['localEventCount', 'flush', 'localEventCount'])
  assert.equal(persistence.calls.filter(call => call[0] === 'handoffCheck').length, 2)
})

test('preflight blocks local-ahead when the host cannot flush', async () => {
  const persistence = fakePersistence(check('local-ahead'))
  const host = fakeHost()
  const controller = createHandoffController({ persistence, host })

  const result = await controller.preflight('session-f')
  assert.equal(result.action, 'blocked')
  assert.equal(host.calls.some(call => call[0] === 'flush'), false)
})

test('preflight reports create for a missing Session', async () => {
  const persistence = fakePersistence(check('not-found', 'none'))
  const host = fakeHost()
  const controller = createHandoffController({ persistence, host })

  const result = await controller.preflight('session-g')
  assert.equal(result.action, 'create')
  assert.equal(host.calls.some(call => call[0] === 'invalidate'), false)
})

test('recover rebuilds after a conflict and reports the new state', async () => {
  const persistence = fakePersistence(check('fresh'))
  const host = fakeHost()
  const controller = createHandoffController({ persistence, host })

  const result = await controller.recover('session-h', 'conflict')
  assert.equal(result.action, 'rebuilt')
  assert.equal(result.check.state, 'fresh')
  assert.deepEqual(host.calls.map(call => call[0]), ['invalidate', 'resume', 'localEventCount'])
  assert.deepEqual(persistence.calls.map(call => call[0]), ['releaseWriter', 'handoffCheck', 'handoffCheck'])
})

test('concurrent recover calls share one rebuild', async () => {
  let openGate
  const gate = new Promise(resolve => { openGate = resolve })
  const persistence = fakePersistence(check('fresh'))
  const host = fakeHost({ invalidate: async () => { await gate } })
  const controller = createHandoffController({ persistence, host })

  const first = controller.recover('session-i')
  const second = controller.recover('session-i')
  openGate()
  const [left, right] = await Promise.all([first, second])

  assert.equal(left.action, 'rebuilt')
  assert.equal(right.action, 'rebuilt')
  assert.equal(host.calls.filter(call => call[0] === 'invalidate').length, 1)
  assert.equal(host.calls.filter(call => call[0] === 'resume').length, 1)
})

test('a failed invalidate leaves the generation untouched', async () => {
  const failure = new Error('invalidate failed')
  const persistence = fakePersistence(check('stale'))
  const host = fakeHost({ invalidate: async () => { throw failure } })
  const controller = createHandoffController({ persistence, host })

  await assert.rejects(controller.recover('session-j'), failure)
  assert.equal(host.calls.some(call => call[0] === 'resume'), false)
  assert.equal(persistence.calls.some(call => call[0] === 'releaseWriter'), false)
})

test('a failed releaseWriter does not resume the generation', async () => {
  const failure = new Error('writer still open')
  const persistence = fakePersistence(check('stale'), { releaseError: failure })
  const host = fakeHost()
  const controller = createHandoffController({ persistence, host })

  await assert.rejects(controller.recover('session-k'), failure)
  assert.equal(host.calls.some(call => call[0] === 'resume'), false)
})

test('preflight waits for an in-flight rebuild before reading the cursor', async () => {
  let openGate
  const gate = new Promise(resolve => { openGate = resolve })
  const persistence = fakePersistence(check('fresh'))
  const host = fakeHost({ invalidate: async () => { await gate } })
  const controller = createHandoffController({ persistence, host })

  const recovering = controller.recover('session-m')
  const preflighting = controller.preflight('session-m')
  openGate()
  await Promise.all([recovering, preflighting])

  // Both checks must run after resume; without serialization, preflight would
  // read localEventCount while invalidate is still tearing the generation down.
  assert.deepEqual(host.calls.map(call => call[0]), [
    'invalidate', 'resume', 'localEventCount', 'localEventCount',
  ])
})

test('attachConflictRecovery routes the conflict event into recover', async () => {
  const handlers = new Map()
  const ctx = {
    on(name, handler) {
      handlers.set(name, handler)
      return () => handlers.delete(name)
    },
  }
  const persistence = fakePersistence(check('fresh'))
  const host = fakeHost()
  const controller = createHandoffController({ persistence, host })
  const dispose = attachConflictRecovery(ctx, controller)

  const listener = handlers.get('session-persistence/conflict')
  assert.equal(typeof listener, 'function')
  const result = await listener({ id: 'session-l' }, new Error('conflict'))
  assert.equal(result.action, 'rebuilt')
  assert.equal(host.calls.filter(call => call[0] === 'invalidate').length, 1)
  assert.equal(host.calls.filter(call => call[0] === 'resume').length, 1)

  dispose()
  assert.equal(handlers.has('session-persistence/conflict'), false)
})

// DSH cold resume rejects open remote turns with its public RemoteError code.
test('remote busy during conflict recovery blocks without failing the event listener', async () => {
  const failure = Object.assign(new Error('winner is still running'), { code: 'session/agent-busy' })
  const persistence = fakePersistence([check('fresh'), check('stale', 'open')])
  const host = fakeHost({ resume: async () => { throw failure } })
  const controller = createHandoffController({ persistence, host })
  let listener
  attachConflictRecovery({ on(_event, callback) { listener = callback } }, controller)
  const result = await listener({ id: 'session-remote-busy' }, new Error('conflict'))
  assert.equal(result.action, 'blocked')
  assert.equal(result.check.turnState, 'open')
  assert.deepEqual(host.calls.map(call => call[0]), ['invalidate', 'resume'])
  assert.deepEqual(persistence.calls.map(call => call[0]), ['releaseWriter', 'handoffCheck', 'handoffCheck'])
})


test('releaseWriter conflict blocks recovery without resuming or failing the listener', async () => {
 const failure=Object.assign(new Error('conflict during close'),{name:'SessionPersistenceConflictError'})
 const persistence=fakePersistence(check('stale','open'),{releaseError:failure})
 const host=fakeHost();const controller=createHandoffController({persistence,host})
 let listener;attachConflictRecovery({on(_event,callback){listener=callback}},controller)
 const result=await listener({id:'close-conflict'},failure)
 assert.equal(result.action,'blocked')
 assert.equal(host.calls.some(call=>call[0]==='resume'),false)
})


function openCheck(state, ageMs, now = 1_000_000) {
  return { state, cloudEventCount: 3, localEventCount: 3, turnState: 'open', turnClosed: false,
    lastEvent: { type: 'step/start', seq: 2, time: now - ageMs } }
}

test('an open turn that was active within the timeout is refused with a retry hint', async () => {
  const persistence = fakePersistence(openCheck('stale', 20_000))
  const host = fakeHost({ liveAgentStatus: 'idle' })
  const controller = createHandoffController({ persistence, host, openTurnTimeoutMs: 60_000, now: () => 1_000_000 })

  await assert.rejects(controller.preflight('s'), error => {
    assert.equal(error.name, 'HandoffBusyError')
    assert.equal(error.retryAfterMs, 40_000)
    return true
  })
  assert.equal(host.calls.some(call => call[0] === 'invalidate'), false)
})

test('an open turn quiet for the whole timeout is treated as a crash and taken over', async () => {
  const persistence = fakePersistence(openCheck('stale', 90_000))
  const host = fakeHost({ liveAgentStatus: 'idle' })
  const controller = createHandoffController({ persistence, host, openTurnTimeoutMs: 60_000, now: () => 1_000_000 })

  const result = await controller.preflight('s')
  assert.equal(result.action, 'rebuilt')
  assert.deepEqual(host.calls.map(call => call[0]), ['liveAgentStatus', 'localEventCount', 'invalidate', 'resume'])
  assert.deepEqual(persistence.calls.map(call => call[0]), ['handoffCheck', 'releaseWriter'])
})

test('a fresh open turn with an idle local Agent is also taken over once abandoned', async () => {
  const persistence = fakePersistence(openCheck('fresh', 90_000))
  const host = fakeHost({ liveAgentStatus: 'idle', liveTurnState: 'open' })
  const controller = createHandoffController({ persistence, host, openTurnTimeoutMs: 60_000, now: () => 1_000_000 })
  assert.equal((await controller.preflight('s')).action, 'rebuilt')
})

test('without a configured timeout an open turn is never taken over', async () => {
  const persistence = fakePersistence(openCheck('stale', 86_400_000))
  const host = fakeHost({ liveAgentStatus: 'idle' })
  const controller = createHandoffController({ persistence, host, now: () => 1_000_000 })
  await assert.rejects(controller.preflight('s'), { name: 'HandoffBusyError' })
})

test('an open turn whose last event has no usable time is never taken over', async () => {
  const check = openCheck('stale', 0); check.lastEvent = { type: 'step/start', seq: 2 }
  const persistence = fakePersistence(check)
  const host = fakeHost({ liveAgentStatus: 'idle' })
  const controller = createHandoffController({ persistence, host, openTurnTimeoutMs: 1, now: () => 1_000_000 })
  await assert.rejects(controller.preflight('s'), { name: 'HandoffBusyError' })
})


test('a losing executor never resumes an open winner even after its quiet timeout', async () => {
  const persistence = fakePersistence(openCheck('stale', 90_000))
  const host = fakeHost()
  const controller = createHandoffController({ persistence, host, openTurnTimeoutMs: 60_000, now: () => 1_000_000 })
  let listener
  attachConflictRecovery({ on(_event, callback) { listener = callback } }, controller)
  const result = await listener({ id: 'late-writer' }, new Error('late append conflict'))
  assert.equal(result.action, 'blocked')
  assert.equal(result.check.turnState, 'open')
  assert.deepEqual(host.calls.map(call => call[0]), ['invalidate'])
  assert.deepEqual(persistence.calls.map(call => call[0]), ['releaseWriter', 'handoffCheck'])
})
