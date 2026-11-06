/**
 * Minimal DSH wiring for the handoff controller.
 *
 * The persistence plugin and the controller are version-independent. The only
 * version-specific operations are the `generation` port and the liveness ports,
 * implemented with the DSH 0.2.1-rc.2 agent/session-controller APIs:
 *
 *   generation.invalidate(sessionId)  stop input, cancel/await the turn, dispose
 *                                     the agent, and finish teardown
 *   generation.resume(sessionId)      reopen through ctx.agents.resume()
 *   generation.flush(sessionId)?      optional; flush before a local-ahead check
 *
 * `attachDshHandoff` additionally reads two public DSH signals:
 *
 *   ctx.agents.get(id)?.status                       'idle' | 'running'
 *   ctx.sessionProjections.stateOf(session,'turnBoundary')
 *
 * They are the only way to distinguish a turn this replica is still driving
 * from an open turn left by a crash or another replica. Without them the
 * controller stays conservative and refuses an open turn.
 */

import { attachConflictRecovery, createHandoffController, HandoffBusyError } from './handoff-controller.js'
import { DEFAULT_OPEN_TURN_TIMEOUT_MS } from './constants.js'

export function createDshHandoff({ persistence, generation, liveAgentStatus, liveTurnState, logger, openTurnTimeoutMs }) {
  if (!generation || typeof generation.invalidate !== 'function' || typeof generation.resume !== 'function') {
    throw new TypeError('generation must provide invalidate() and resume()')
  }

  const host = {
    localEventCount: async sessionId => {
      await persistence.flushWriter?.(sessionId)
      return persistence.writerCursor(sessionId)
    },
    invalidate: sessionId => generation.invalidate(sessionId),
    resume: sessionId => generation.resume(sessionId),
  }
  if (typeof generation.flush === 'function') {
    host.flush = sessionId => generation.flush(sessionId)
  }
  if (typeof liveAgentStatus === 'function') host.liveAgentStatus = liveAgentStatus
  if (typeof liveTurnState === 'function') host.liveTurnState = liveTurnState
  return createHandoffController({ persistence, host, logger, openTurnTimeoutMs })
}

/**
 * Cordis helper: create the controller from `ctx.sessionPersistence`, derive
 * the liveness ports from `ctx.agents` / `ctx.sessionProjections`, and route
 * `session-persistence/conflict` into recover(). The caller still has to call
 * `controller.preflight(sessionId)` before each turn; the plugin cannot see the
 * turn boundary — the DSH source patch calls it after the Agent is resolved.
 *
 * @returns {{ controller: ReturnType<typeof createHandoffController>, dispose: () => void }}
 */
export function attachDshHandoff(ctx, { generation, logger = () => {}, openTurnTimeoutMs = DEFAULT_OPEN_TURN_TIMEOUT_MS } = {}) {
  if (!ctx || typeof ctx.on !== 'function') throw new TypeError('ctx.on is required')
  const persistence = ctx.sessionPersistence
  if (!persistence) throw new TypeError('ctx.sessionPersistence is required')
  // The persistence layer applies the same timeout when a Session is opened for
  // writing, before DSH's own crash repair can run. The previous value is
  // restored when this plugin unloads.
  const previousTimeout = persistence.openTurnTimeoutMs
  persistence.openTurnTimeoutMs = openTurnTimeoutMs

  const liveAgentStatus = sessionId => ctx.get?.('agents')?.get?.(sessionId)?.status
  const liveTurnState = sessionId => {
    const agent = ctx.get?.('agents')?.get?.(sessionId)
    if (agent === undefined) return undefined
    const boundary = ctx.get?.('sessionProjections')?.stateOf?.(agent.session, 'turnBoundary')
    if (boundary === undefined) return undefined
    if (boundary.openTurnStartSeq !== null) return 'open'
    return boundary.lastTurn === 0 ? 'none' : 'closed'
  }

  const controller = createDshHandoff({ persistence, generation, liveAgentStatus, liveTurnState, logger, openTurnTimeoutMs })
  // The DSH source patch calls this before admitting a non-steer prompt, after
  // resolving the Agent. `rebuilt` tells the caller to resolve again because
  // the Agent it held was disposed.
  //
  // Cordis requires `ctx.provide()` for a new service: `ctx.set()` throws when
  // the name was never provided by this fiber. The returned disposer is owned
  // by the plugin fiber, so unloading the integration plugin removes it.
  const handoff = {
    beforePrompt: async sessionId => {
      const decision = await controller.preflight(sessionId)
      // The common case (`run`) is not worth a log line per prompt.
      if (decision.action !== 'run') {
        logger('handoff preflight', {
          sessionId,
          action: decision.action,
          state: decision.check?.state,
          turnState: decision.check?.turnState,
        })
      }
      if (decision.action === 'blocked') throw new HandoffBusyError(sessionId, decision.check, 'local-ahead')
      return decision
    },
  }
  if (typeof ctx.provide === 'function') {
    ctx.provide('sessionHandoff', handoff)
  } else if (typeof ctx.set === 'function') {
    // Minimal hosts and unit tests that do not implement Cordis provide().
    ctx.set('sessionHandoff', handoff)
  }
  logger('handoff service registered', {})
  const stopRecovery = attachConflictRecovery(ctx, controller, { logger })
  const dispose = () => {
    stopRecovery()
    persistence.openTurnTimeoutMs = previousTimeout
  }
  return { controller, dispose }
}
