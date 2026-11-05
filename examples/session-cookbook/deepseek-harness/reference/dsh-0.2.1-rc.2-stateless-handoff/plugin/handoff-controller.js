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
 */

import { SESSION_PERSISTENCE_CONFLICT } from './constants.js'

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
  constructor(sessionId, check, reason = 'open-turn') {
    super(`session "${sessionId}" cannot start a new turn: ${describe(check, reason)}`)
    this.name = 'HandoffBusyError'
    this.sessionId = sessionId
    this.check = check
    this.reason = reason
  }
}

function turnStateOf(check) {
  if (check?.turnState !== undefined) return check.turnState
  // Backward compatibility for hosts that only report the two-state view.
  return check?.turnClosed ? 'closed' : 'open'
}

function describe(check, reason) {
  if (reason === 'local-turn-running') {
    return 'this replica is still driving a turn while the stored log is ahead'
  }
  const turnState = turnStateOf(check)
  if (turnState === 'open') {
    return check.state === 'stale'
      ? 'the stored log is ahead and the last turn is still open'
      : 'an open turn has no driver in this replica'
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
   * or when an open turn has no driver in this replica. An open turn is not a
   * liveness signal and is never closed automatically.
   */
  async function preflight(sessionId) {
    let current = await check(sessionId)

    if (current.state === 'local-ahead' && typeof host.flush === 'function') {
      await host.flush(sessionId)
      current = await check(sessionId)
    }

    if (current.state === 'not-found') return { action: 'create', check: current }
    if (current.state === 'local-ahead') return { action: 'blocked', check: current }

    const turnState = await resolveTurnState(sessionId, current)
    const agentStatus = await resolveAgentStatus(sessionId)

    if (current.state === 'stale') {
      // Never rebuild underneath a turn this replica is still driving. The
      // running turn will surface its own conflict on append.
      if (agentStatus === 'running') {
        throw new HandoffBusyError(sessionId, current, 'local-turn-running')
      }
      // The remote writer's turn is open, or a crashed turn was left open.
      // This replica cannot tell which, and must not close it.
      if (turnState !== 'closed') throw new HandoffBusyError(sessionId, current, 'open-turn')
      const generation = await rebuild(sessionId, 'preflight-stale')
      return { action: 'rebuilt', check: current, generation }
    }

    // fresh: an open turn is only this replica's own turn when the live Agent
    // is actually driving it. Queueing a followup into a running turn is
    // normal; an idle Agent with an open log is crash residue (or a turn that
    // was just resumed) and must not be continued silently.
    if (turnState === 'open' && agentStatus !== 'running') {
      throw new HandoffBusyError(sessionId, current, 'open-turn')
    }
    return { action: 'run', check: current }
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
