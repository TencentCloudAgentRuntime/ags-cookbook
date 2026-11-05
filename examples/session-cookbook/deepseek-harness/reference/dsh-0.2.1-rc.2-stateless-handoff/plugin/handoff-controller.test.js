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
  assert.deepEqual(host.calls.map(call => call[0]), ['localEventCount', 'liveTurnState', 'liveAgentStatus'])
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
  assert.deepEqual(host.calls.map(call => call[0]), ['localEventCount', 'liveAgentStatus', 'invalidate', 'resume'])
  assert.deepEqual(persistence.calls.map(call => call[0]), ['handoffCheck', 'releaseWriter'])
})

test('preflight refuses a stale open turn instead of closing it', async () => {
  const persistence = fakePersistence(check('stale', 'open'))
  const host = fakeHost({ liveAgentStatus: 'idle', liveTurnState: 'closed' })
  const controller = createHandoffController({ persistence, host })

  await assert.rejects(controller.preflight('session-c'), HandoffBusyError)
  assert.deepEqual(host.calls.map(call => call[0]), ['localEventCount', 'liveAgentStatus'])
  assert.equal(persistence.calls.some(call => call[0] === 'releaseWriter'), false)
})

test('preflight never rebuilds underneath a turn this replica is running', async () => {
  const persistence = fakePersistence(check('stale'))
  const host = fakeHost({ liveAgentStatus: 'running' })
  const controller = createHandoffController({ persistence, host })

  await assert.rejects(controller.preflight('session-running'), error => {
    assert.equal(error.reason, 'local-turn-running')
    return true
  })
  assert.equal(host.calls.some(call => call[0] === 'invalidate'), false)
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
  assert.deepEqual(persistence.calls.map(call => call[0]), ['releaseWriter', 'handoffCheck'])
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
