import { randomUUID } from 'node:crypto'
import { readSession } from '../extension/session-restore.js'
import { SessionSync } from '../extension/session-sync.js'

const BOUNDARY = 'ags-turn-boundary'

/**
 * Default shutdown budget: running turns get GRACE to finish, then the rest are
 * aborted and get ABORT to close their boundary. Their sum must stay below the
 * orchestrator's termination grace period, otherwise the process is killed
 * before it can close off; Kubernetes defaults to 30 seconds, so the sum is 25
 * to leave a margin.
 */
export const DEFAULT_SHUTDOWN_GRACE_MS = 20_000
export const DEFAULT_SHUTDOWN_ABORT_MS = 5_000

/** The Session cannot take a new turn right now. Callers may retry later. */
export class SessionBusyError extends Error {
  code = 'session/agent-busy'
  /** If the turn really crashed, a retry after this many milliseconds is expected to succeed. */
  retryAfterMs = undefined
}

/** This replica is shutting down and accepts no new turns. */
export class ShuttingDownError extends Error {
  code = 'session/shutting-down'
}

// An EventId collision means another writer owns that position. The turn it holds
// is not ours to close.
function isConflict(error) {
  return error?.code === 'ResourceInUse.EventIdDuplicate'
}

function lastBoundary(entries) {
  return entries.findLast(entry => entry.type === 'custom' && entry.customType === BOUNDARY)
}

// Milliseconds since the last entry, or undefined when it cannot be told. Entry
// timestamps are ISO strings written by whichever replica ran the turn, so this
// assumes the replicas' clocks agree to well within the timeout.
function idleMs(entries, now) {
  const time = Date.parse(entries.at(-1)?.timestamp)
  return Number.isFinite(time) ? Math.max(0, now - time) : undefined
}

// Sessions written before the boundary protocol have no marker. A last message
// that is not a finished assistant reply means the turn never completed.
function hasUnfinishedTurn(entries) {
  const boundary = lastBoundary(entries)
  if (boundary !== undefined) return boundary.data?.state === 'open'
  const last = entries.findLast(entry => entry.type === 'message')?.message
  return last !== undefined && (last.role !== 'assistant' || last.stopReason === 'toolUse')
}

/**
 * Handles one prompt per request. Each request opens a fresh in-memory
 * generation from the cloud history; the Session API is the only durable state,
 * so no local session file or replica affinity is needed.
 *
 * Turn protocol: persist an `open` boundary first (the claim), run the prompt,
 * then persist a `closed` boundary. If the turn fails after this replica claimed
 * it and persistence still works, the boundary is closed with `outcome: 'error'`
 * so one model error does not lock the Session. The failed turn is never
 * replayed. If persistence itself fails, or the claim was lost to another
 * writer, the boundary is left as found.
 *
 * A turn left open by a replica that died is closed automatically. The log
 * cannot tell a dead executor from a slow one, so activity decides: a turn that
 * wrote an entry within `openTurnTimeoutMs` is refused (it may still be running),
 * one that has been quiet for longer is treated as crashed and closed with
 * `outcome: 'abandoned'`. If the old executor was alive after all, its next
 * write lands on the position the closer now holds and fails with an EventId
 * conflict, so it can no longer write to the log. Tools it already started are
 * not stopped. Without `openTurnTimeoutMs`, nothing is ever taken over.
 */
export class StatelessPiHost {
  /** sessionId -> { settled, abort } for turns running in this process. */
  active = new Map()
  shuttingDown = false

  constructor({ client, createGeneration, openTurnTimeoutMs, now = Date.now }) {
    this.client = client
    this.createGeneration = createGeneration
    this.openTurnTimeoutMs = openTurnTimeoutMs
    this.now = now
  }

  async prompt(sessionId, text) {
    if (this.shuttingDown) throw new ShuttingDownError('This replica is shutting down')
    if (this.active.has(sessionId)) throw new SessionBusyError('A turn is already running in this replica')

    let generation
    let release
    const settled = new Promise(resolve => { release = resolve })
    this.active.set(sessionId, { settled, abort: () => generation?.session.abort?.() })

    let sync
    let unsubscribe
    let writes = Promise.resolve()
    let claimed = false
    let persistenceFailure
    try {
      const stored = await readSession(this.client, sessionId)
      let abandonedIdleMs
      if (stored !== undefined && hasUnfinishedTurn(stored.entries)) {
        const idle = idleMs(stored.entries, this.now())
        if (this.openTurnTimeoutMs === undefined || idle === undefined || idle < this.openTurnTimeoutMs) {
          const busy = new SessionBusyError('The previous turn is unfinished and was active recently; it may still be running. Retry later.')
          if (this.openTurnTimeoutMs !== undefined) busy.retryAfterMs = Math.ceil(this.openTurnTimeoutMs - (idle ?? 0))
          throw busy
        }
        abandonedIdleMs = idle
      }
      generation = await this.createGeneration(sessionId, stored)
      const manager = generation.manager
      // The history was just read and validated; reuse it instead of reading again.
      sync = stored === undefined
        ? await SessionSync.open(this.client, sessionId)
        : SessionSync.fromStored(this.client, sessionId, stored)

      // Close the abandoned turn first. If its executor is still alive, its next
      // write targets this position and fails with an EventId conflict. If another
      // replica closes it at the same moment, this append conflicts and the
      // request ends with a 409 instead of running a turn on top of theirs.
      if (abandonedIdleMs !== undefined) {
        manager.appendCustomEntry(BOUNDARY, { state: 'closed', outcome: 'abandoned', idleMs: abandonedIdleMs })
        await sync.flush(manager.getHeader(), manager.getEntries(), { force: true, verify: false })
      }

      // The claim. A random request id makes two simultaneous claims differ, so the
      // Session API rejects the loser at this position instead of treating it as a
      // retry of the winner.
      manager.appendCustomEntry(BOUNDARY, { state: 'open', requestId: randomUUID() })
      await sync.flush(manager.getHeader(), manager.getEntries(), { force: true })
      claimed = true

      // Within this request we hold the claim, so a later append at the same
      // position fails with EventIdDuplicate. Re-reading the whole history at
      // every checkpoint would add nothing.
      unsubscribe = generation.session.subscribe?.(event => {
        if (!['message_end', 'turn_end', 'tool_execution_end'].includes(event.type)) return
        const snapshot = structuredClone(manager.getEntries())
        writes = writes.then(async () => {
          if (persistenceFailure) return
          await sync.flush(manager.getHeader(), snapshot, { force: true, verify: false })
        }).catch(error => {
          persistenceFailure = error
          void Promise.resolve(generation.session.abort?.()).catch(() => {})
        })
      })
      await generation.session.prompt(text)
      await writes
      if (persistenceFailure) throw persistenceFailure
      const lastAssistant = manager.getEntries().findLast(entry => entry.type === 'message' && entry.message.role === 'assistant')?.message
      if (lastAssistant && ['error', 'aborted'].includes(lastAssistant.stopReason)) {
        throw new Error(lastAssistant.errorMessage || `Model stopped with ${lastAssistant.stopReason}`)
      }
      manager.appendCustomEntry(BOUNDARY, { state: 'closed', outcome: 'completed' })
      await sync.flush(manager.getHeader(), manager.getEntries(), { force: true, verify: false })
      return { reply: generation.reply(), eventCount: sync.synced }
    } catch (error) {
      await writes
      const canClose = claimed && persistenceFailure === undefined && !isConflict(error)
      if (canClose) await this.#closeAfterFailure(generation, sync, error)
      // The failed request is never replayed; the caller decides whether to retry.
      throw error
    } finally {
      unsubscribe?.()
      generation?.session.dispose()
      this.active.delete(sessionId)
      release()
    }
  }

  // Best effort. If this write fails too, the boundary stays open and the turn is
  // taken over automatically once it has been quiet for the open-turn timeout.
  async #closeAfterFailure(generation, sync, cause) {
    try {
      const manager = generation.manager
      manager.appendCustomEntry(BOUNDARY, { state: 'closed', outcome: 'error', message: String(cause?.message ?? cause).slice(0, 500) })
      await sync.flush(manager.getHeader(), manager.getEntries(), { force: true, verify: false })
    } catch {
      // Leave the boundary open.
    }
  }

  /**
   * Stop accepting turns, give running turns `graceMs` to finish, then abort the
   * rest and wait up to `abortMs` for them to close their boundary.
   * @returns session ids that were still running when the wait ended.
   */
  async shutdown({ graceMs = DEFAULT_SHUTDOWN_GRACE_MS, abortMs = DEFAULT_SHUTDOWN_ABORT_MS } = {}) {
    this.shuttingDown = true
    const waitFor = async ms => {
      let timer
      try {
        await Promise.race([
          // settled only resolves, from prompt's finally block, even when the turn fails.
          Promise.all([...this.active.values()].map(turn => turn.settled)),
          // Pending promises alone do not keep Node alive through shutdown.
          new Promise(resolve => { timer = setTimeout(resolve, ms) }),
        ])
      } finally {
        clearTimeout(timer)
      }
    }
    await waitFor(graceMs)
    if (this.active.size > 0) {
      for (const turn of this.active.values()) void Promise.resolve().then(() => turn.abort()).catch(() => {})
      await waitFor(abortMs)
    }
    return [...this.active.keys()]
  }
}
