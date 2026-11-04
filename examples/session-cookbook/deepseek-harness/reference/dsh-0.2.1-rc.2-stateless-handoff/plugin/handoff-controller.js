/**
 * Turns the persistence plugin's handoff primitives into an explicit state
 * machine for the owner of the live session.
 *
 * The controller is deliberately host-agnostic: it never imports DSH. The
 * integration supplies three operations:
 *
 *   host.localEventCount(sessionId)  durable events this replica has written
 *   host.invalidate(sessionId)       stop input, cancel/await the turn, dispose
 *                                    the agent, and finish teardown
 *   host.resume(sessionId)           reopen through DSH's resume path
 *
 * `host.invalidate` MUST await teardown; `persistence.releaseWriter` is called
 * after it to make sure the in-process write claim is gone before `resume`.
 */

import { SESSION_PERSISTENCE_CONFLICT } from './constants.js'

export class HandoffBusyError extends Error {
  constructor(sessionId, check) {
    super(`session "${sessionId}" cannot start a new turn: ${describe(check)}`)
    this.name = 'HandoffBusyError'
    this.sessionId = sessionId
    this.check = check
  }
}

function describe(check) {
  if (!check.turnClosed) {
    return check.state === 'stale'
      ? 'the stored log is ahead and the last turn is still open'
      : 'the last turn is still open'
  }
  return check.state
}

export function createHandoffController({ persistence, host, logger = () => {} }) {
  if (!persistence || typeof persistence.handoffCheck !== 'function' || typeof persistence.releaseWriter !== 'function') {
    throw new TypeError('persistence must provide handoffCheck() and releaseWriter()')
  }
  if (!host || typeof host.localEventCount !== 'function' || typeof host.invalidate !== 'function' || typeof host.resume !== 'function') {
    throw new TypeError('host must provide localEventCount(), invalidate(), and resume()')
  }

  // Coalesce concurrent rebuilds so two conflicts cannot tear down twice.
  const rebuilding = new Map()

  async function check(sessionId) {
    const localEventCount = await host.localEventCount(sessionId)
    return persistence.handoffCheck(sessionId, localEventCount)
  }

  async function rebuild(sessionId, reason) {
    const running = rebuilding.get(sessionId)
    if (running !== undefined) return running

    const task = (async () => {
      logger('handoff rebuild started', { sessionId, reason })
      // Stop the old generation first; resuming before teardown would race the
      // in-process write claim and the live Session object.
      await host.invalidate(sessionId)
      await persistence.releaseWriter(sessionId)
      const generation = await host.resume(sessionId)
      logger('handoff rebuild finished', { sessionId, reason })
      return generation
    })()
    rebuilding.set(sessionId, task)
    try {
      return await task
    } finally {
      rebuilding.delete(sessionId)
    }
  }

  /**
   * Decide what to do before a new turn.
   *
   * - `run`      the stored log matches and the last turn is closed
   * - `rebuilt`  a stale generation was invalidated and resumed
   * - `create`   the Session does not exist yet
   * - `blocked`  local is ahead (flush failed or was unavailable)
   *
   * Throws HandoffBusyError when the last turn is open. An open turn is not a
   * liveness signal: never close it automatically.
   */
  async function preflight(sessionId) {
    let current = await check(sessionId)

    if (current.state === 'local-ahead' && typeof host.flush === 'function') {
      await host.flush(sessionId)
      current = await check(sessionId)
    }

    if (current.state === 'not-found') return { action: 'create', check: current }
    if (current.state === 'local-ahead') return { action: 'blocked', check: current }
    if (!current.turnClosed) throw new HandoffBusyError(sessionId, current)
    if (current.state === 'stale') {
      const generation = await rebuild(sessionId, 'preflight-stale')
      return { action: 'rebuilt', check: current, generation }
    }
    if (current.state === 'fresh') return { action: 'run', check: current }
    return { action: 'blocked', check: current }
  }

  /**
   * Recover after a persistence conflict. The controller only rebuilds; the
   * caller decides whether the failed turn may be retried.
   */
  async function recover(sessionId, reason = 'conflict') {
    const generation = await rebuild(sessionId, reason)
    return { action: 'rebuilt', check: await check(sessionId), generation }
  }

  return { preflight, recover, rebuild, check }
}

/**
 * Wire the controller to the persistence conflict event. The integration still
 * owns the host; this only routes `session-persistence/conflict` to recover().
 *
 * @returns the Cordis listener disposer.
 */
export function attachConflictRecovery(ctx, controller, { logger = () => {} } = {}) {
  if (!ctx || typeof ctx.on !== 'function') throw new TypeError('ctx.on is required')
  return ctx.on(SESSION_PERSISTENCE_CONFLICT, (session, error) => {
    const sessionId = session?.id
    if (!sessionId) return undefined
    return controller.recover(sessionId, 'conflict').catch(failure => {
      logger('handoff conflict recovery failed', { sessionId, error: String(failure) })
      throw failure
    })
  })
}
