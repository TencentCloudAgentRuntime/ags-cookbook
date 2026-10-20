// Writes the model section of DSH's settings.yaml from LLM_* environment variables
// before DSH starts. The API key is never written: DSH reads LLM_API_KEY at runtime.
import { createRequire } from 'node:module'
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { dirname, join } from 'node:path'
import { pathToFileURL } from 'node:url'

export const PROVIDER = 'custom'
const REQUIRED = ['LLM_BASE_URL', 'LLM_MODEL', 'LLM_API_KEY']

export function missingVariables(env) {
  return REQUIRED.filter(name => !env[name]?.trim())
}

// [path, value] pairs to set in settings.yaml; every other setting is left as is.
export function modelSettings(env) {
  const baseURL = env.LLM_BASE_URL.trim()
  const model = env.LLM_MODEL.trim()
  return [
    [['llm-pi-ai', 'providers', PROVIDER], {
      displayName: 'Configured Model Service',
      apiKeyEnv: 'LLM_API_KEY',
      api: 'openai-completions',
      baseURL,
      models: [{ id: model }],
    }],
    [['agent-default-model'], { provider: PROVIDER, model }],
  ]
}

async function main() {
  const missing = missingVariables(process.env)
  if (missing.length > 0) {
    console.error(`configure-model: set ${missing.join(', ')}; see .env.example`)
    process.exit(1)
  }
  // Parse with the same YAML library DSH uses to read its settings.
  const dshModules = process.env.DSH_MODULES || '/usr/local/lib/node_modules/@deepseek-ai'
  const YAML = createRequire(join(dshModules, 'dsh-settings-file', 'package.json'))('yaml')
  const file = join(process.env.DSH_HOME || '/root/.dsh', 'settings.yaml')
  const text = await readFile(file, 'utf8').catch(error => {
    if (error.code === 'ENOENT') return ''
    throw error
  })
  const doc = YAML.parseDocument(text)
  if (doc.errors.length > 0) {
    throw new Error(`configure-model: ${file} is not valid YAML: ${doc.errors[0].message}`)
  }
  if (doc.contents === null) doc.contents = doc.createNode({})
  for (const [path, value] of modelSettings(process.env)) doc.setIn(path, doc.createNode(value))
  await mkdir(dirname(file), { recursive: true })
  await writeFile(file, String(doc))
  console.log(`configure-model: ${PROVIDER}/${process.env.LLM_MODEL.trim()} via ${process.env.LLM_BASE_URL.trim()}`)
}

if (import.meta.url === pathToFileURL(process.argv[1]).href) await main()
