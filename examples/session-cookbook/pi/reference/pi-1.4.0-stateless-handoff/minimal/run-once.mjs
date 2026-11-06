// One-shot adapter using the same claim, cold-load and persistence rules as the HTTP host.
import { ModelRuntime, SessionManager, createAgentSession } from '@earendil-works/pi-coding-agent'
import { SessionClient, configFromEnv } from '../extension/session-client.js'
import { StatelessPiHost } from '../stateless/host.js'

const sessionId = process.env.PI_SESSION_ID
const prompt = process.argv[2]
if (!sessionId || !prompt) throw new Error('usage: PI_SESSION_ID=<id> node run-once.mjs "<prompt>"')
const modelRuntime = await ModelRuntime.create()
const host = new StatelessPiHost({
  client: new SessionClient(configFromEnv()),
  createGeneration: async (id, stored) => {
    const manager = SessionManager.inMemory(process.cwd(), { id }, stored && [stored.header, ...stored.entries])
    const { session } = await createAgentSession({ sessionManager: manager, modelRuntime,
      model: modelRuntime.getModel('custom', process.env.LLM_MODEL), noTools: 'builtin' })
    let reply = ''
    session.subscribe(event => {
      if (event.type === 'message_update' && event.assistantMessageEvent.type === 'text_delta') reply += event.assistantMessageEvent.delta
    })
    return { manager, session, reply: () => reply.trim() }
  },
})
console.log((await host.prompt(sessionId, prompt)).reply)
