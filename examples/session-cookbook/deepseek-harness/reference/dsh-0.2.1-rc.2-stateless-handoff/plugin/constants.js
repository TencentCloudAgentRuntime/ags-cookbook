/** Cordis event emitted when a write handle detects an EventId conflict. */
export const SESSION_PERSISTENCE_CONFLICT = 'session-persistence/conflict'

/**
 * How long an unfinished turn may show no new event before it is treated as
 * abandoned (its executor crashed) and closed so the conversation can continue.
 *
 * It must be longer than the longest quiet stretch of a healthy turn, such as a
 * slow model call or a long-running tool. Too short a value takes over turns that
 * are still running; too long a value leaves a crashed conversation unusable for
 * that long. Set `OPEN_TURN_TIMEOUT_MS` to change it.
 */
export const DEFAULT_OPEN_TURN_TIMEOUT_MS = 10 * 60 * 1000

/**
 * Read the open-turn timeout from the environment.
 * @throws when the value is set but is not a positive number, so a typo fails at startup.
 */
export function openTurnTimeoutFromEnv(env = process.env) {
  const raw = env.OPEN_TURN_TIMEOUT_MS
  if (raw === undefined || raw.trim() === '') return DEFAULT_OPEN_TURN_TIMEOUT_MS
  const value = Number(raw)
  if (!Number.isFinite(value) || value <= 0) {
    throw new Error(`OPEN_TURN_TIMEOUT_MS must be a positive number of milliseconds, got "${raw}"`)
  }
  return value
}

/**
 * Milliseconds since the last event of an unfinished turn, or undefined when it
 * cannot be told. `time` is the writer's Unix epoch milliseconds, so this assumes
 * the replicas' clocks agree to well within the timeout.
 */
export function idleMs(lastEvent, now = Date.now()) {
  const time = lastEvent?.time
  return Number.isFinite(time) ? Math.max(0, now - time) : undefined
}
