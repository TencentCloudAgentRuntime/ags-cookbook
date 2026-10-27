import { SessionClient, configFromEnv } from './session-client.js'
import { SessionSync } from './session-sync.js'

export const name = 'ags-pi-session'

// pi has no hook that fires per appended entry, so the extension compares the entries
// pi holds with the count already in the cloud at these points and sends the rest.
const FLUSH_EVENTS = [
  'message_end',
  'turn_end',
  'agent_end',
  'agent_before_settle',
  'session_compact',
  'session_tree',
  'session_info_changed',
  'session_shutdown',
]

export default function agsPiSession(pi, options = {}) {
  const client = options.client ?? new SessionClient(configFromEnv())
  const log = options.log ?? (message => process.stderr.write(`[${name}] ${message}\n`))
  // One sync per pi session id. A session switch, fork or new session brings a new id.
  const syncs = new Map()

  function syncFor(sessionId) {
    let sync = syncs.get(sessionId)
    if (sync === undefined) {
      sync = SessionSync.open(client, sessionId, log)
      syncs.set(sessionId, sync)
      // A failed open is retried by the next flush instead of being remembered.
      sync.catch(() => syncs.delete(sessionId))
    }
    return sync
  }

  async function flush(_event, ctx) {
    const manager = ctx.sessionManager
    try {
      const sync = await syncFor(manager.getSessionId())
      await sync.flush(manager.getHeader(), manager.getEntries())
    } catch (error) {
      const message = `saving session ${manager.getSessionId()} to Agent Runtime Session failed: ${error.message}`
      log(message)
      // In RPC mode this reaches the client as an extension UI request.
      ctx.ui?.notify?.(message, 'error')
    }
  }

  for (const event of FLUSH_EVENTS) pi.on(event, flush)
}
