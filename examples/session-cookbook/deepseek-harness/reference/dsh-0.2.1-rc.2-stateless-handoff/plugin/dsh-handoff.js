/**
 * Minimal DSH wiring for the handoff controller.
 *
 * The persistence plugin and the controller are version-independent. The only
 * version-specific operation is the `generation` port, which the integration
 * implements with the DSH 0.2.1-rc.2 agent/session-controller APIs:
 *
 *   generation.invalidate(sessionId)  stop input, cancel/await the turn, dispose
 *                                     the agent, and finish teardown
 *   generation.resume(sessionId)      reopen through ctx.agents.resume()
 *   generation.flush(sessionId)?      optional; flush before a local-ahead check
 *
 * Keeping this as a port is deliberate: without the real agent handle, a
 * plugin cannot dispose a live Session, and the session-controller's public
 * release/invalidate surface must be verified on the target version.
 */

import { attachConflictRecovery, createHandoffController, HandoffBusyError } from './handoff-controller.js'

export function createDshHandoff({ persistence, generation, logger }) {
  if (!generation || typeof generation.invalidate !== 'function' || typeof generation.resume !== 'function') {
    throw new TypeError('generation must provide invalidate() and resume()')
  }

  const host = {
    localEventCount: sessionId => persistence.writerCursor(sessionId),
    invalidate: sessionId => generation.invalidate(sessionId),
    resume: sessionId => generation.resume(sessionId),
  }
  if (typeof generation.flush === 'function') {
    host.flush = sessionId => generation.flush(sessionId)
  }
  return createHandoffController({ persistence, host, logger })
}

/**
 * Cordis helper: create the controller from `ctx.sessionPersistence` and route
 * `session-persistence/conflict` into recover(). The caller still has to call
 * `controller.preflight(sessionId)` before each turn; the plugin cannot see the
 * turn boundary.
 *
 * @returns {{ controller: ReturnType<typeof createHandoffController>, dispose: () => void }}
 */
export function attachDshHandoff(ctx, { generation, logger } = {}) {
  if (!ctx || typeof ctx.on !== 'function') throw new TypeError('ctx.on is required')
  const persistence = ctx.sessionPersistence
  if (!persistence) throw new TypeError('ctx.sessionPersistence is required')
  const controller = createDshHandoff({ persistence, generation, logger })
  // The DSH source patch calls this before admitting a non-steer prompt.
  if (typeof ctx.set === 'function') {
    ctx.set('sessionHandoff', {
      beforePrompt: async sessionId => {
        const decision = await controller.preflight(sessionId)
        if (decision.action === 'blocked') throw new HandoffBusyError(sessionId, decision.check)
        return decision
      },
    })
  }
  const dispose = attachConflictRecovery(ctx, controller, { logger })
  return { controller, dispose }
}
