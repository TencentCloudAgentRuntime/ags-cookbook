import assert from 'node:assert/strict'
import { readdirSync, readFileSync } from 'node:fs'
import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { parseAllDocuments } from 'yaml'

const root = fileURLToPath(new URL('../', import.meta.url))
const chart = `${root}/deploy/helm/dsh-awv`
function validate(text, name, customTags = []) {
  for (const document of parseAllDocuments(text, { customTags })) {
    assert.equal(document.errors.length, 0, `${name}: ${document.errors.map(e => e.message).join('; ')}`)
    assert.equal(document.warnings.length, 0, `${name}: ${document.warnings.map(e => e.message).join('; ')}`)
  }
}
function walk(directory) {
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    const path = `${directory}/${entry.name}`
    if (entry.isDirectory()) {
      if (!['node_modules', 'lib', '.local', '_output'].includes(entry.name) && path !== `${chart}/templates`) walk(path)
    } else if (/\.ya?ml$/.test(entry.name)) {
      // Harness expressions remain strings during syntax validation; never execute them.
      validate(readFileSync(path, 'utf8'), path, [{ tag: 'tag:yaml.org,2002:js', resolve: value => value }])
    }
  }
}
walk(root)
execFileSync('helm', ['lint', chart], { stdio: 'inherit' })
validate(execFileSync('helm', ['template', 'dsh-awv', chart], { encoding: 'utf8' }), 'rendered Helm manifests')
console.log('YAML syntax and rendered Helm manifests passed.')
