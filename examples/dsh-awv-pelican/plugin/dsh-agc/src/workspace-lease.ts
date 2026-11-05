import { randomUUID } from 'node:crypto'
import { applyObject, deleteObject, kubectl } from './kubectl.js'

const NAME = 'pelican-workspace-lock'

function microTime(): string {
  return new Date().toISOString().replace(/(\.\d{3})Z$/, '$1000Z')
}

export async function acquireLease(namespace: string): Promise<() => Promise<void>> {
  const holder = randomUUID()
  const lease = {
    apiVersion: 'coordination.k8s.io/v1',
    kind: 'Lease',
    metadata: { name: NAME, labels: { app: 'dsh-awv' } },
    spec: {
      holderIdentity: holder,
      acquireTime: microTime(),
      leaseDurationSeconds: 1800,
    },
  }
  try {
    await kubectl(namespace, ['create', '-f', '-'], JSON.stringify(lease))
  } catch (error) {
    const message = String(error)
    if (message.includes('AlreadyExists')) {
      throw new Error('工作区正在被其他任务使用；请等待当前 Code、Review 或发布任务结束。')
    }
    throw new Error(`创建工作区 Lease 失败：${message}`)
  }
  return async () => {
    const current = await kubectl(namespace, ['get', 'lease', NAME, '-o', 'jsonpath={.spec.holderIdentity}'])
      .catch(() => undefined)
    if (current?.stdout === holder) await deleteObject(namespace, 'lease', NAME)
  }
}

export async function forceReleaseLease(namespace: string): Promise<void> {
  await deleteObject(namespace, 'lease', NAME)
}
