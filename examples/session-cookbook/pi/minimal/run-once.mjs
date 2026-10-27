// The smallest way to give pi cloud-backed history: no local session file, no pi
// extension. Load the session's entries, hand them to an in-memory SessionManager,
// run one prompt, and send the entries pi added back to the Session.
//
//   node run-once.mjs "<prompt>"        (PI_SESSION_ID names the session)
import { ModelRuntime, SessionManager, createAgentSession } from '@earendil-works/pi-coding-agent'
import { SessionClient, configFromEnv } from '../extension/session-client.js'
import { readSession } from '../extension/session-restore.js'
import { SessionSync } from '../extension/session-sync.js'

const sessionId = process.env.PI_SESSION_ID
const prompt = process.argv[2]
if (!sessionId || !prompt) throw new Error('usage: PI_SESSION_ID=<id> node run-once.mjs "<prompt>"')

const client = new SessionClient(configFromEnv())
const cwd = process.cwd()

// Load: the cloud entries become the in-memory session. A new id starts an empty one.
const stored = await readSession(client, sessionId)
const sessionManager = SessionManager.inMemory(
  cwd,
  { id: sessionId },
  stored && [stored.header, ...stored.entries],
)

const modelRuntime = await ModelRuntime.create()
const { session } = await createAgentSession({
  sessionManager,
  modelRuntime,
  model: modelRuntime.getModel('custom', process.env.LLM_MODEL),
  noTools: 'builtin',
})

let reply = ''
session.subscribe((event) => {
  if (event.type === 'message_update' && event.assistantMessageEvent.type === 'text_delta') {
    reply += event.assistantMessageEvent.delta
  }
})

try {
  await session.prompt(prompt)
} finally {
  session.dispose()
}

// Save: send what pi appended. SessionSync skips the entries the cloud already holds.
const sync = await SessionSync.open(client, sessionId)
await sync.flush(sessionManager.getHeader(), sessionManager.getEntries())
console.log(reply.trim())
