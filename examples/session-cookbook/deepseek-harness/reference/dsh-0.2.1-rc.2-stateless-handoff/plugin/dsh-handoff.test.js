import assert from 'node:assert/strict'
import test from 'node:test'
import { attachDshHandoff, createDshHandoff } from './dsh-handoff.js'
import { HandoffBusyError } from './handoff-controller.js'
import { apply as applyIntegration } from './dsh-handoff-plugin.js'

function check(state, turnState = 'closed') {
  return {
    state,
    cloudEventCount: 2,
    localEventCount: 2,
    turnState,
    turnClosed: turnState === 'closed',
  }
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

function fakeCtx(persistence, { agents, sessionProjections } = {}) {
  const services = new Map()
  const handlers = new Map()
  if (agents !== undefined) services.set('agents', agents)
  if (sessionProjections !== undefined) services.set('sessionProjections', sessionProjections)
  return {
    handlers,
    sessionPersistence: persistence,
    on(name, handler) {
      handlers.set(name, handler)
      return () => handlers.delete(name)
    },
    provide(name, value) {
      services.set(name, value)
      return () => services.delete(name)
    },
    set(name, value) {
      services.set(name, value)
    },
    get(name) {
      return services.get(name)
    },
  }
}

function liveAgent(status) {
  const agent = { id: 'session-live', session: { id: 'session-live' }, status }
  return { get: sessionId => (sessionId === 'session-live' ? agent : undefined) }
}

function projection(boundary) {
  return { stateOf: () => boundary }
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

test('createDshHandoff accepts the optional liveness ports', async () => {
  const persistence = fakePersistence(check('fresh', 'open'))
  const generation = fakeGeneration()
  const controller = createDshHandoff({
    persistence,
    generation,
    liveAgentStatus: () => 'running',
    liveTurnState: () => 'open',
  })

  const result = await controller.preflight('session-live')
  assert.equal(result.action, 'run')
})

test('attachDshHandoff derives liveness from agents and session projections', async () => {
  const ctx = fakeCtx(fakePersistence(check('fresh', 'open')), {
    agents: liveAgent('running'),
    sessionProjections: projection({ openTurnStartSeq: 1, lastTurn: 1 }),
  })
  const generation = fakeGeneration()
  attachDshHandoff(ctx, { generation })

  const decision = await ctx.get('sessionHandoff').beforePrompt('session-live')
  assert.equal(decision.action, 'run')
})

test('attachDshHandoff refuses a resumed open turn when the live Agent is idle', async () => {
  const ctx = fakeCtx(fakePersistence(check('fresh', 'open')), {
    agents: liveAgent('idle'),
    sessionProjections: projection({ openTurnStartSeq: 1, lastTurn: 1 }),
  })
  const generation = fakeGeneration()
  attachDshHandoff(ctx, { generation })

  await assert.rejects(
    ctx.get('sessionHandoff').beforePrompt('session-live'),
    HandoffBusyError,
  )
})

test('attachDshHandoff treats a never-started Session as none, not open', async () => {
  const ctx = fakeCtx(fakePersistence(check('fresh', 'none')), {
    agents: liveAgent('idle'),
    sessionProjections: projection({ openTurnStartSeq: null, lastTurn: 0 }),
  })
  const generation = fakeGeneration()
  attachDshHandoff(ctx, { generation })

  const decision = await ctx.get('sessionHandoff').beforePrompt('session-live')
  assert.equal(decision.action, 'run')
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

test('the integration plugin registers the handoff service and conflict recovery', async () => {
  const persistence = fakePersistence(check('fresh'))
  const calls = []
  const disposers = []
  const ctx = {
    sessionPersistence: persistence,
    sessionController: {
      async invalidateGeneration(sessionId) {
        calls.push(['invalidateGeneration', sessionId])
      },
      async resumeGeneration(sessionId) {
        calls.push(['resumeGeneration', sessionId])
        return { id: sessionId }
      },
    },
    agents: { get: () => undefined },
    sessionProjections: { stateOf: () => undefined },
    on(name, handler) {
      this.handlers ??= new Map()
      this.handlers.set(name, handler)
      return () => this.handlers.delete(name)
    },
    provide(name, value) {
      this.services ??= new Map()
      this.services.set(name, value)
      return () => this.services.delete(name)
    },
    set(name, value) {
      this.services ??= new Map()
      this.services.set(name, value)
    },
    get(name) {
      return this.services?.get(name)
    },
    effect(create, label) {
      disposers.push([label, create()])
      return () => {}
    },
    logger: { info() {} },
  }

  applyIntegration(ctx, {})
  assert.equal(typeof ctx.get('sessionHandoff').beforePrompt, 'function')
  assert.equal(ctx.handlers.has('session-persistence/conflict'), true)
  assert.equal(disposers.length, 1)

  await ctx.handlers.get('session-persistence/conflict')({ id: 'session-plugin' }, new Error('conflict'))
  assert.deepEqual(calls, [
    ['invalidateGeneration', 'session-plugin'],
    ['resumeGeneration', 'session-plugin'],
  ])
})


test('the open-turn timeout is applied while the plugin is attached and restored on dispose', () => {
  const persistence = fakePersistence(check('fresh'))
  persistence.openTurnTimeoutMs = undefined
  const ctx = fakeCtx(persistence)
  const { dispose } = attachDshHandoff(ctx, { generation: fakeGeneration() })
  assert.equal(persistence.openTurnTimeoutMs, 10 * 60 * 1000)
  dispose()
  assert.equal(persistence.openTurnTimeoutMs, undefined)
})

test('the open-turn timeout can be configured', () => {
  const persistence = fakePersistence(check('fresh'))
  attachDshHandoff(fakeCtx(persistence), { generation: fakeGeneration(), openTurnTimeoutMs: 90_000 })
  assert.equal(persistence.openTurnTimeoutMs, 90_000)
})

test('a blocked local-ahead state is reported as such, not as an open turn', async () => {
  const ctx = fakeCtx(fakePersistence(check('local-ahead')))
  attachDshHandoff(ctx, { generation: fakeGeneration() })
  await assert.rejects(ctx.get('sessionHandoff').beforePrompt('s'), error => error.reason === 'local-ahead')
})
