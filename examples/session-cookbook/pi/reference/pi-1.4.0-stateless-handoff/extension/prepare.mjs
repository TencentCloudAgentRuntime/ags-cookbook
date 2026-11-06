// Only configures the model. Session history is loaded into memory per HTTP request.
import { mkdirSync, writeFileSync } from 'node:fs'
import { homedir } from 'node:os'
import { join } from 'node:path'
import { modelsJson } from './model-config.js'

if (process.env.PI_SKIP_MODEL_CONFIG !== 'true') {
  const agentDir = process.env.PI_CODING_AGENT_DIR ?? join(homedir(), '.pi', 'agent')
  mkdirSync(agentDir, { recursive: true })
  writeFileSync(join(agentDir, 'models.json'), `${JSON.stringify(modelsJson(process.env), null, 2)}\n`)
}
