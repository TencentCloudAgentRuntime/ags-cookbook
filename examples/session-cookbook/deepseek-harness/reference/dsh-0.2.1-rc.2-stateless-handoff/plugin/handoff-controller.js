/**
 * Turns the persistence plugin's handoff primitives into an explicit state
 * machine for the owner of the live session.
 *
 * The controller is deliberately host-agnostic: it never imports DSH. The
 * integration supplies three required operations:
 *
 *   host.localEventCount(sessionId)  durable events this replica has written
 *   host.invalidate(sessionId)       stop input, cancel/await the turn, dispose
 *                                    the agent, and finish teardown
 *   host.resume(sessionId)           reopen through DSH's resume path
 *
 * `host.invalidate` MUST await teardown; `persistence.releaseWriter` is called
 * after it to make sure the in-process write claim is gone before `resume`.
 *
 * Two optional operations let the caller distinguish a turn this replica is
 * actually driving from one that only exists as an open log:
 *
 *   host.liveAgentStatus(sessionId)  'idle' | 'running' | undefined
 *   host.liveTurnState(sessionId)    'none' | 'open' | 'closed' | undefined
 *
 * The log alone is not a liveness signal: a crashed turn and a running turn on
 * another replica look identical. A live Agent's `status` is the liveness
 * signal, and its Session projection is the authoritative turn boundary for
 * the fresh case.
 *
 * When this replica's own Agent is running a turn, preflight returns `run`
 * without reading the cloud. The turn already holds its claim (turn/start is
 * persisted before any work), so another writer cannot be running one, and a
 * read would only race this replica's own in-flight appends.
 */

import { SESSION_PERSISTENCE_CONFLICT, idleMs } from './constants.js'

/**
 * A new turn was refused because the stored log or the live generation is in
 * a state this replica must not act on automatically.
 */
export class HandoffBusyError extends Error {
  /**
   * @param sessionId - Session that refused the turn.
   * @param check - the handoffCheck() value the decision was made from.
   * @param reason - why the turn was refused.
   */
  constructor(sessionId, check, reason = 'open-turn', retryAfterMs = undefined) {
    super(`session "${sessionId}" cannot start a new turn: ${describe(check, reason)}`)
    this.name = 'HandoffBusyError'
    this.code = 'session/handoff-busy'
    this.sessionId = sessionId
    this.check = check
    this.reason = reason
    /** When set, a retry after this many milliseconds is expected to succeed if the turn really crashed. */
    this.retryAfterMs = retryAfterMs
  }
}

function turnStateOf(check) {
  if (check?.turnState !== undefined) return check.turnState
  // Backward compatibility for hosts that only report the two-state view.
  return check?.turnClosed ? 'closed' : 'open'
}

function describe(check, reason) {
  if (reason === 'local-ahead') return 'this replica holds events that are not stored yet'
  const turnState = turnStateOf(check)
  if (turnState === 'open') {
    return check.state === 'stale'
      ? 'the stored log is ahead and the last turn is still open'
      : 'an open turn has no driver in this replica'
  }
  return check.state
}

export function createHandoffController({ persistence, host, logger = () => {}, openTurnTimeoutMs, now = Date.now }) {
  if (!persistence || typeof persistence.handoffCheck !== 'function' || typeof persistence.releaseWriter !== 'function') {
    throw new TypeError('persistence must provide handoffCheck() and releaseWriter()')
  }
  if (!host || typeof host.localEventCount !== 'function' || typeof host.invalidate !== 'function' || typeof host.resume !== 'function') {
    throw new TypeError('host must provide localEventCount(), invalidate(), and resume()')
  }
  for (const name of ['liveAgentStatus', 'liveTurnState']) {
    if (host[name] !== undefined && typeof host[name] !== 'function') {
      throw new TypeError(`host.${name} must be a function when provided`)
    }
  }

  // Coalesce concurrent rebuilds so two conflicts cannot tear down twice.
  const rebuilding = new Map()

  async function check(sessionId) {
    // A rebuild disposes and reopens the writer. Reading the cursor while it is
    // in flight could observe a half-torn-down generation, so serialize behind
    // the in-flight rebuild first.
    const running = rebuilding.get(sessionId)
    if (running !== undefined) await running.catch(() => undefined)
    const localEventCount = await host.localEventCount(sessionId)
    return persistence.handoffCheck(sessionId, localEventCount)
  }

  async function rebuild(sessionId, reason, allowOpenTurn = true) {
    const running = rebuilding.get(sessionId)
    if (running !== undefined) return running

    const task = (async () => {
      logger('handoff rebuild started', { sessionId, reason })
      // Stop the old generation first; resuming before teardown would race the
      // in-process write claim and the live Session object.
      await host.invalidate(sessionId)
      await persistence.releaseWriter(sessionId)
      if (!allowOpenTurn) {
        // A losing executor may discard its generation, but conflict recovery
        // must not take the winner's turn back, even after its quiet timeout.
        // Only an explicit new prompt is allowed to initiate timeout takeover.
        const current = await persistence.handoffCheck(sessionId, 0)
        if (turnStateOf(current) === 'open') throw new HandoffBusyError(sessionId, current)
      }
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

  // A stale local view cannot see the remote tail, so the cloud-derived state
  // from handoffCheck() is authoritative. When the log matches, prefer the live
  // Agent's own projection: it is O(1) and distinguishes an empty log from an
  // open turn.
  async function resolveTurnState(sessionId, current) {
    if (current.state !== 'stale' && typeof host.liveTurnState === 'function') {
      const live = await host.liveTurnState(sessionId)
      if (live !== undefined) return live
    }
    return turnStateOf(current)
  }

  async function resolveAgentStatus(sessionId) {
    if (typeof host.liveAgentStatus !== 'function') return undefined
    return host.liveAgentStatus(sessionId)
  }

  /**
   * Decide what to do before a new turn.
   *
   * - `run`      this replica may admit the turn
   * - `rebuilt`  a stale generation was invalidated and resumed
   * - `create`   the Session does not exist yet
   * - `blocked`  local is ahead (flush failed or was unavailable)
   *
   * Throws HandoffBusyError when the stored log is ahead and its turn is open,
   * or when an open turn has no driver here and has not reached the configured
   * quiet timeout. Older open turns are rebuilt through native crash repair.
   */
  async function preflight(sessionId) {
    // Our own turn is running: queueing more input is normal and needs no cloud read.
    if (await resolveAgentStatus(sessionId) === 'running') return { action: 'run' }

    let current = await check(sessionId)

    if (current.state === 'local-ahead' && typeof host.flush === 'function') {
      await host.flush(sessionId)
      current = await check(sessionId)
    }

    if (current.state === 'not-found') return { action: 'create', check: current }
    if (current.state === 'local-ahead') return { action: 'blocked', check: current }

    const turnState = await resolveTurnState(sessionId, current)
    // Here this replica's Agent is idle, so an open turn has no driver in this
    // process. Either another replica is running it or it was left by a crash,
    // and the log cannot tell which. Activity tells: a turn that recently wrote an
    // event may be alive and is refused; one quiet for the whole timeout is
    // treated as a crash and closed by rebuilding, which makes DSH's own crash
    // repair run when the Session is reopened for writing. Without a configured
    // timeout nothing is ever taken over.
    if (turnState === 'open') {
      const idle = idleMs(current.lastEvent, now())
      if (openTurnTimeoutMs === undefined || idle === undefined || idle < openTurnTimeoutMs) {
        const retryAfterMs = openTurnTimeoutMs === undefined ? undefined : Math.ceil(openTurnTimeoutMs - (idle ?? 0))
        throw new HandoffBusyError(sessionId, current, 'open-turn', retryAfterMs)
      }
      logger('handoff taking over an abandoned turn', { sessionId, idleMs: idle })
      const generation = await rebuild(sessionId, 'open-turn-abandoned')
      return { action: 'rebuilt', check: current, generation }
    }

    if (current.state === 'stale') {
      const generation = await rebuild(sessionId, 'preflight-stale')
      return { action: 'rebuilt', check: current, generation }
    }
    return { action: 'run', check: current }
  }

  /**
   * Recover after a persistence conflict. The controller only rebuilds; the
   * caller decides whether the failed turn may be retried.
   */
  async function recover(sessionId, reason = 'conflict') {
    try {
      const generation = await rebuild(sessionId, reason, false)
      return { action: 'rebuilt', check: await check(sessionId), generation }
    } catch (error) {
      // The losing generation is disposed, but the winner may still be running.
      // Resume will reject its open turn. Wait for a later request to cold-load
      // the completed history instead of repairing or replaying it.
      if (error?.name !== 'HandoffBusyError' && error?.code !== 'session/agent-busy'
        && error?.name !== 'SessionPersistenceConflictError'
        && error?.code !== 'session/handoff-busy') throw error
      return { action: 'blocked', check: error.check ?? await persistence.handoffCheck(sessionId, 0) }
    }
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
