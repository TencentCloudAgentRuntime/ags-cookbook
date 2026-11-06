/**
 * Cordis runtime plugin for stateless session handoff.
 *
 * This is the piece that actually calls `attachDshHandoff` at runtime. The
 * persistence plugin (`index.js`) only owns storage; it never sees the Agent or
 * the turn boundary, so it cannot rebuild a live generation by itself.
 *
 * Load it after `session-persistence-agent-runtime`:
 *
 *   - id: dsh-stateless-handoff
 *     name: '@tencentcloud/ags-dsh-session-persistence/handoff'
 *
 * The DSH source patch (`dockerfiles/0001-stateless-handoff.patch`) calls the
 * `sessionHandoff` service this plugin registers, after resolving the Agent and
 * before admitting a non-steer prompt.
 */

import { attachDshHandoff } from './dsh-handoff.js'
import { openTurnTimeoutFromEnv } from './constants.js'

export const name = 'dsh-stateless-handoff'

// `sessionController` supplies invalidateGeneration()/resumeGeneration(); the
// other two are the public liveness signals read by attachDshHandoff().
export const inject = ['agents', 'sessionController', 'sessionPersistence', 'sessionProjections']

export function apply(ctx, config = {}) {
  // stderr, so the handoff state transitions are visible in the DSH process log
  // even when the host logger has no info exporter configured.
  const logger = typeof config.logger === 'function'
    ? config.logger
    : (message, fields) => console.error(`[dsh-stateless-handoff] ${message} ${JSON.stringify(fields)}`)

  // An unfinished turn is taken over once it has shown no activity for this long.
  const openTurnTimeoutMs = openTurnTimeoutFromEnv()
  logger('open-turn timeout', { openTurnTimeoutMs })

  const { dispose } = attachDshHandoff(ctx, {
    generation: {
      invalidate: sessionId => ctx.sessionController.invalidateGeneration(sessionId),
      resume: sessionId => ctx.sessionController.resumeGeneration(sessionId),
    },
    logger,
    openTurnTimeoutMs,
  })

  ctx.effect(() => dispose, 'dsh-stateless-handoff: conflict listener')
}
