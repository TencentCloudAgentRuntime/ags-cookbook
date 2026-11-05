import { kubectl } from './kubectl.js'

function delay(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(resolve, ms)
    signal?.addEventListener('abort', () => {
      clearTimeout(timer)
      reject(new Error('任务已取消'))
    }, { once: true })
  })
}

export async function stopSite(namespace: string): Promise<void> {
  await kubectl(namespace, ['scale', 'deployment/pelican-site', '--replicas=0']).catch(() => undefined)
  await kubectl(namespace, ['wait', '--for=delete', 'pod', '-l', 'app=pelican-site', '--timeout=180s']).catch(() => undefined)
}

export async function waitForJob(namespace: string, name: string, signal?: AbortSignal): Promise<string> {
  const started = Date.now()
  while (Date.now() - started < 20 * 60 * 1000) {
    const state = await kubectl(namespace, [
      'get', 'job', name,
      '-o', 'jsonpath={.status.succeeded}{"|"}{.status.failed}',
    ], undefined, signal)
    const [succeeded, failed] = state.stdout.split('|')
    if (succeeded === '1') {
      return (await kubectl(namespace, ['logs', `job/${name}`, '--timestamps=true'])).stdout
    }
    if (failed !== '' && failed !== '0') {
      const logs = await kubectl(namespace, ['logs', `job/${name}`, '--timestamps=true']).catch(() => ({ stdout: '', stderr: '' }))
      throw new Error(`Agent Job ${name} 执行失败：\n${logs.stdout.slice(-6000)}`)
    }
    await delay(3000, signal)
  }
  throw new Error(`Agent Job ${name} 在 20 分钟内未完成`)
}
