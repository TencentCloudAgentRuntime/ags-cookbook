// Runs before pi starts: writes the model configuration and brings the requested
// cloud sessions back to disk, so that pi finds them like any local session.
import { mkdirSync, writeFileSync } from 'node:fs'
import { homedir } from 'node:os'
import { join } from 'node:path'
import { modelsJson } from './model-config.js'
import { SessionClient, configFromEnv } from './session-client.js'
import { restoreSession } from './session-restore.js'

const env = process.env
const sessionDir = env.PI_SESSION_DIR ?? '/var/pi/sessions'
const agentDir = env.PI_CODING_AGENT_DIR ?? join(homedir(), '.pi', 'agent')

// An empty LLM_* setting fails here, before pi starts, with the variable names.
// A deployment that keeps its own models.json sets PI_SKIP_MODEL_CONFIG=true.
if (env.PI_SKIP_MODEL_CONFIG !== 'true') {
  mkdirSync(agentDir, { recursive: true })
  writeFileSync(join(agentDir, 'models.json'), `${JSON.stringify(modelsJson(env), null, 2)}\n`)
}

const client = new SessionClient(configFromEnv(env))
const sessionIds = new Set()
if (env.PI_SESSION_ID?.trim()) sessionIds.add(env.PI_SESSION_ID.trim())
if (env.PI_RESTORE_ALL === 'true') {
  for (const id of await client.listSessionIds()) sessionIds.add(id)
}

for (const id of sessionIds) {
  const path = await restoreSession(client, id, sessionDir)
  console.error(path ? `prepare: restored session ${id}` : `prepare: session ${id} is new or already on disk`)
}
