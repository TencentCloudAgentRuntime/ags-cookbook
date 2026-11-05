import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import dotenv from 'dotenv'

const root = fileURLToPath(new URL('../', import.meta.url))
dotenv.config({ path: `${root}/.env`, quiet: true })
const [command, ...args] = process.argv.slice(2)
if (!command) throw new Error('A command is required')
const result = spawnSync(command, args, { cwd: root, env: process.env, stdio: 'inherit' })
if (result.error) throw result.error
process.exit(result.status ?? 1)
