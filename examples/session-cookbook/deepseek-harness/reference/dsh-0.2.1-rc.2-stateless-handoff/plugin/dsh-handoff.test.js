import assert from 'node:assert/strict'
import test from 'node:test'
import { attachDshHandoff, createDshHandoff } from './dsh-handoff.js'
import { HandoffBusyError } from './handoff-controller.js'

function check(state, turnClosed = true) {
  return { state, cloudEventCount: 2, localEventCount: 2, turnClosed }
}

function fakePersistence(checks) {
  const calls = []
  let index = 0
  return {
    calls,
    writerCursor(sessionId) {
      calls.push(['writerCursor', sessionId])
      return 2
    },
    async handoffCheck(sessionId, localEventCount) {
      calls.push(['handoffCheck', sessionId, localEventCount])
      return Array.isArray(checks) ? checks[Math.min(index++, checks.length - 1)] : checks
    },
    async releaseWriter(sessionId) {
      calls.push(['releaseWriter', sessionId])
    },
  }
}

function fakeGeneration({ flush } = {}) {
  const calls = []
  const generation = {
    calls,
    async invalidate(sessionId) {
      calls.push(['invalidate', sessionId])
    },
    async resume(sessionId) {
      calls.push(['resume', sessionId])
      return { sessionId }
    },
  }
  if (flush !== undefined) {
    generation.flush = async sessionId => {
      calls.push(['flush', sessionId])
      await flush(sessionId)
    }
  }
  return generation
}

function fakeCtx(persistence) {
  const services = new Map()
  const handlers = new Map()
  return {
    handlers,
    sessionPersistence: persistence,
    on(name, handler) {
      handlers.set(name, handler)
      return () => handlers.delete(name)
    },
    set(name, value) {
      services.set(name, value)
    },
    get(name) {
      return services.get(name)
    },
  }
}

test('createDshHandoff rebuilds a stale generation through the port', async () => {
  const persistence = fakePersistence(check('stale'))
  const generation = fakeGeneration()
  const controller = createDshHandoff({ persistence, generation })

  const result = await controller.preflight('session-a')
  assert.equal(result.action, 'rebuilt')
  assert.deepEqual(generation.calls.map(call => call[0]), ['invalidate', 'resume'])
  assert.deepEqual(persistence.calls.map(call => call[0]), ['writerCursor', 'handoffCheck', 'releaseWriter'])
})

test('createDshHandoff forwards the optional flush operation', async () => {
  const persistence = fakePersistence([check('local-ahead'), check('fresh')])
  const generation = fakeGeneration({ flush: async () => {} })
  const controller = createDshHandoff({ persistence, generation })

  const result = await controller.preflight('session-b')
  assert.equal(result.action, 'run')
  assert.equal(generation.calls.some(call => call[0] === 'flush'), true)
})

test('attachDshHandoff wires the conflict event to recovery', async () => {
  const ctx = fakeCtx(fakePersistence(check('fresh')))
  const generation = fakeGeneration()
  const { controller, dispose } = attachDshHandoff(ctx, { generation })
  assert.equal(typeof controller.preflight, 'function')

  const listener = ctx.handlers.get('session-persistence/conflict')
  await listener({ id: 'session-c' }, new Error('conflict'))
  assert.deepEqual(generation.calls.map(call => call[0]), ['invalidate', 'resume'])

  dispose()
  assert.equal(ctx.handlers.has('session-persistence/conflict'), false)
})

test('attachDshHandoff installs the pre-prompt hook', async () => {
  const ctx = fakeCtx(fakePersistence(check('stale')))
  const generation = fakeGeneration()
  attachDshHandoff(ctx, { generation })

  const handoff = ctx.get('sessionHandoff')
  assert.equal(typeof handoff.beforePrompt, 'function')
  const decision = await handoff.beforePrompt('session-d')
  assert.equal(decision.action, 'rebuilt')
  assert.deepEqual(generation.calls.map(call => call[0]), ['invalidate', 'resume'])
})

test('the pre-prompt hook reports a blocked handoff as busy', async () => {
  const ctx = fakeCtx(fakePersistence(check('local-ahead')))
  const generation = fakeGeneration()
  attachDshHandoff(ctx, { generation })

  await assert.rejects(
    ctx.get('sessionHandoff').beforePrompt('session-e'),
    HandoffBusyError,
  )
  assert.equal(generation.calls.length, 0)
})

test('createDshHandoff rejects an incomplete generation port', () => {
  assert.throws(
    () => createDshHandoff({ persistence: fakePersistence(check('fresh')), generation: {} }),
    /invalidate/,
  )
})

test('attachDshHandoff requires ctx.sessionPersistence', () => {
  assert.throws(
    () => attachDshHandoff({ on() {} }, { generation: fakeGeneration() }),
    /sessionPersistence/,
  )
})
