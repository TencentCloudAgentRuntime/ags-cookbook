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

export const name = 'dsh-stateless-handoff'

// `sessionController` supplies invalidateGeneration()/resumeGeneration(); the
// other two are the public liveness signals read by attachDshHandoff().
export const inject = ['agents', 'sessionController', 'sessionPersistence', 'sessionProjections']

export function apply(ctx, config = {}) {
  const logger = typeof config.logger === 'function'
    ? config.logger
    : (message, fields) => ctx.logger?.info?.(`${message} ${JSON.stringify(fields)}`)

  const { dispose } = attachDshHandoff(ctx, {
    generation: {
      invalidate: sessionId => ctx.sessionController.invalidateGeneration(sessionId),
      resume: sessionId => ctx.sessionController.resumeGeneration(sessionId),
    },
    logger,
  })

  ctx.effect(() => dispose, 'dsh-stateless-handoff: conflict listener')
}
