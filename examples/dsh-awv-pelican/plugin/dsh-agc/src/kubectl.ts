import { spawn } from 'node:child_process'

export interface CommandResult {
  stdout: string
  stderr: string
}

export function kubectl(
  namespace: string,
  args: string[],
  input?: string,
  signal?: AbortSignal,
): Promise<CommandResult> {
  return new Promise((resolve, reject) => {
    const child = spawn('kubectl', ['-n', namespace, ...args], {
      stdio: ['pipe', 'pipe', 'pipe'],
      signal,
    })
    let stdout = ''
    let stderr = ''
    child.stdout.setEncoding('utf8').on('data', chunk => { stdout += chunk })
    child.stderr.setEncoding('utf8').on('data', chunk => { stderr += chunk })
    child.on('error', reject)
    child.on('close', (code) => {
      if (code === 0) resolve({ stdout, stderr })
      else reject(new Error(`kubectl ${args.join(' ')} failed (${code}): ${stderr.trim()}`))
    })
    if (input === undefined) child.stdin.end()
    else child.stdin.end(input)
  })
}

export async function applyObject(namespace: string, object: unknown, signal?: AbortSignal): Promise<void> {
  await kubectl(namespace, ['apply', '-f', '-'], JSON.stringify(object), signal)
}

export async function deleteObject(
  namespace: string,
  kind: string,
  name: string,
): Promise<void> {
  await kubectl(namespace, ['delete', kind, name, '--ignore-not-found=true', '--wait=true']).catch(() => undefined)
}

export async function getJson<T>(namespace: string, kind: string, name: string): Promise<T | undefined> {
  const result = await kubectl(namespace, ['get', kind, name, '-o', 'json']).catch(() => undefined)
  return result === undefined ? undefined : JSON.parse(result.stdout) as T
}
