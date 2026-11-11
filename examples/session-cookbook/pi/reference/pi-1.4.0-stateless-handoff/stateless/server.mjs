import { createServer } from 'node:http'
import { ModelRuntime, SessionManager, createAgentSession } from '@earendil-works/pi-coding-agent'
import { SessionClient, configFromEnv } from '../extension/session-client.js'
import { DEFAULT_SHUTDOWN_ABORT_MS, DEFAULT_SHUTDOWN_GRACE_MS, StatelessPiHost } from './host.js'

// An unfinished turn that has been quiet for this long is treated as crashed and
// closed automatically. It must exceed the longest quiet stretch of a healthy
// turn (a slow model call, a long tool). Default 10 minutes.
const DEFAULT_OPEN_TURN_TIMEOUT_MS = 10 * 60 * 1000
function openTurnTimeout(env = process.env) {
  const raw = env.OPEN_TURN_TIMEOUT_MS
  if (raw === undefined || raw.trim() === '') return DEFAULT_OPEN_TURN_TIMEOUT_MS
  const value = Number(raw)
  if (!Number.isFinite(value) || value <= 0) throw new Error(`OPEN_TURN_TIMEOUT_MS must be a positive number of milliseconds, got "${raw}"`)
  return value
}

const client = new SessionClient(configFromEnv())
const modelRuntime = await ModelRuntime.create()
const host = new StatelessPiHost({
  client,
  openTurnTimeoutMs: openTurnTimeout(),
  createGeneration: async (sessionId, stored) => {
    const manager = SessionManager.inMemory(process.cwd(), { id: sessionId }, stored && [stored.header, ...stored.entries])
    const { session } = await createAgentSession({ sessionManager: manager, modelRuntime,
      model: modelRuntime.getModel('custom', process.env.LLM_MODEL) })
    let reply = ''
    session.subscribe(event => {
      if (event.type === 'message_update' && event.assistantMessageEvent.type === 'text_delta') reply += event.assistantMessageEvent.delta
    })
    return { manager, session, reply: () => reply.trim() }
  },
})

// Errors the caller can act on, with the HTTP status that says so. Anything else
// is reported as a generic 500; the details stay in this process's log.
const CLIENT_ERRORS = {
  'session/agent-busy': 409, // an earlier turn is unfinished, or this replica is already running one
  'ResourceInUse.EventIdDuplicate': 409, // another writer got there first; reload and retry
  'ResourceInUse.SessionIdDuplicate': 409, // another writer created the same new Session
  'session/shutting-down': 503, // this replica is stopping; send the request to another one
  'invalid-request': 400,
}

class InvalidRequest extends Error {
  code = 'invalid-request'
}

async function readJson(req) {
  const parts = []
  let size = 0
  for await (const chunk of req) {
    size += chunk.length
    if (size > 1048576) throw new InvalidRequest('Request exceeds 1 MiB')
    parts.push(chunk)
  }
  try {
    return JSON.parse(Buffer.concat(parts))
  } catch {
    throw new InvalidRequest('Request body is not valid JSON')
  }
}

const server = createServer(async (req, res) => {
  res.setHeader('Content-Type', 'application/json')
  if (req.method === 'GET' && req.url === '/health') return res.end('{"ok":true}')
  if (req.method !== 'POST' || req.url !== '/prompt') { res.statusCode = 404; return res.end('{"error":"not-found"}') }
  try {
    const body = await readJson(req)
    if (body === null || typeof body !== 'object' || Array.isArray(body)) {
      throw new InvalidRequest('Request body must be a JSON object')
    }
    const { sessionId, text } = body
    if (typeof sessionId !== 'string' || !/^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}$/.test(sessionId) || typeof text !== 'string' || !text.trim()) {
      throw new InvalidRequest('sessionId or text is missing or malformed')
    }
    res.end(JSON.stringify(await host.prompt(sessionId, text)))
  } catch (error) {
    const status = CLIENT_ERRORS[error.code]
    console.error(JSON.stringify({ code: error.code, message: error.message, requestId: error.requestId }))
    res.statusCode = status ?? 500
    if (status === 409 && error.retryAfterMs) res.setHeader('Retry-After', Math.ceil(error.retryAfterMs / 1000))
    res.end(JSON.stringify(status
      ? { error: error.code, message: error.message }
      : { error: 'internal-error', message: 'Internal error; see the server log' }))
  }
})
server.listen(Number(process.env.PORT ?? 3080), '0.0.0.0', () => console.error('pi stateless host listening'))

// On SIGTERM/SIGINT stop taking requests, let running turns finish, then abort what
// is left so each turn closes its boundary. The orchestrator's termination grace
// period must be longer than SHUTDOWN_GRACE_MS + SHUTDOWN_ABORT_MS.
let stopping = false
async function stop(signal) {
  if (stopping) return
  stopping = true
  console.error(`${signal}: shutting down`)
  server.close()
  const graceMs = Number(process.env.SHUTDOWN_GRACE_MS ?? DEFAULT_SHUTDOWN_GRACE_MS)
  const abortMs = Number(process.env.SHUTDOWN_ABORT_MS ?? DEFAULT_SHUTDOWN_ABORT_MS)
  const unfinished = await host.shutdown({ graceMs, abortMs })
  if (unfinished.length > 0) console.error(`turns still running at exit: ${unfinished.join(', ')}`)
  process.exit(unfinished.length > 0 ? 1 : 0)
}
for (const signal of ['SIGTERM', 'SIGINT']) process.on(signal, () => void stop(signal))
