import { applyObject, getJson } from './kubectl.js'
import type { WorkspaceState } from './types.js'

const NAME = 'pelican-workspace-state'

const EMPTY: WorkspaceState = {
  generation: 0,
  reviewedGeneration: 0,
  reviewStatus: 'NONE',
  lastCodeJob: '',
  lastReviewJob: '',
  updatedAt: '',
}

interface ConfigMap { data?: Record<string, string> }

export async function readState(namespace: string): Promise<WorkspaceState> {
  const map = await getJson<ConfigMap>(namespace, 'configmap', NAME)
  if (map?.data?.state === undefined) return { ...EMPTY }
  return { ...EMPTY, ...JSON.parse(map.data.state) as WorkspaceState }
}

export async function writeState(namespace: string, state: WorkspaceState): Promise<void> {
  await applyObject(namespace, {
    apiVersion: 'v1',
    kind: 'ConfigMap',
    metadata: { name: NAME, labels: { app: 'dsh-awv' } },
    data: { state: JSON.stringify(state) },
  })
}
