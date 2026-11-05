import { defineTool } from '@deepseek-ai/dsh-tools'
import type { Context } from '@deepseek-ai/cordis'
import { applyObject, getJson } from './kubectl.js'
import { acquireLease } from './workspace-lease.js'
import { readState } from './workspace-state.js'
import type { RuntimeConfig } from './types.js'

interface ServiceStatus {
  status?: { loadBalancer?: { ingress?: Array<{ ip?: string; hostname?: string }> } }
}

function resources(config: RuntimeConfig): unknown[] {
  const node = config.siteNode === undefined || config.siteNode === '' ? {} : {
    nodeSelector: { 'kubernetes.io/hostname': config.siteNode },
  }
  return [
    {
      apiVersion: 'apps/v1', kind: 'Deployment', metadata: { name: 'pelican-site', labels: { app: 'pelican-site' } },
      spec: {
        replicas: 1,
        strategy: { type: 'Recreate' },
        selector: { matchLabels: { app: 'pelican-site' } },
        template: {
          metadata: { labels: { app: 'pelican-site' } },
          spec: {
            ...node,
            automountServiceAccountToken: false,
            ...(config.imagePullSecret === undefined || config.imagePullSecret === '' ? {} : {
              imagePullSecrets: [{ name: config.imagePullSecret }],
            }),
            securityContext: { fsGroup: 10001, fsGroupChangePolicy: 'OnRootMismatch' },
            containers: [{
              name: 'nginx', image: config.siteImage, imagePullPolicy: 'IfNotPresent',
              securityContext: { runAsUser: 10001, runAsGroup: 10001 },
              ports: [{ name: 'http', containerPort: 8080 }],
              readinessProbe: { httpGet: { path: '/', port: 'http' }, initialDelaySeconds: 2, periodSeconds: 2 },
              volumeMounts: [{ name: 'workspace', mountPath: '/usr/share/nginx/html', readOnly: true }],
            }],
            volumes: [{ name: 'workspace', persistentVolumeClaim: { claimName: config.workspaceClaim } }],
          },
        },
      },
    },
    {
      apiVersion: 'v1', kind: 'Service', metadata: { name: 'pelican-site', labels: { app: 'pelican-site' } },
      spec: { type: config.serviceType, selector: { app: 'pelican-site' }, ports: [{ name: 'http', port: 80, targetPort: 'http' }] },
    },
  ]
}

async function waitLink(config: RuntimeConfig): Promise<string> {
  for (let index = 0; index < 120; index += 1) {
    const service = await getJson<ServiceStatus>(config.namespace, 'service', 'pelican-site')
    const ingress = service?.status?.loadBalancer?.ingress?.[0]
    const host = ingress?.ip ?? ingress?.hostname
    if (host !== undefined) return `http://${host}`
    await new Promise(resolve => setTimeout(resolve, 3000))
  }
  return '服务已创建，LoadBalancer 地址仍在分配：kubectl get svc pelican-site -w'
}

export function registerSiteTool(ctx: Context, config: RuntimeConfig): void {
  ctx.tools.register(defineTool({
    name: 'publish_site',
    description: 'Review PASS 后，将 AWV 中的 /workspace/site 发布为网页并返回访问链接。',
    parameters: {},
    output: {
      schema: { type: 'string' },
      render: (_args, value) => [{ type: 'text', text: value }],
    },
    async execute() {
      const release = await acquireLease(config.namespace)
      try {
        const state = await readState(config.namespace)
        if (state.reviewStatus !== 'PASS' || state.generation === 0 || state.reviewedGeneration !== state.generation) {
          throw new Error(`发布被拒绝：review=${state.reviewStatus}, generation=${state.generation}, reviewed=${state.reviewedGeneration}`)
        }
        for (const resource of resources(config)) await applyObject(config.namespace, resource)
        return `发布成功：[打开鹈鹕骑车页面](${await waitLink(config)})`
      } finally {
        await release()
      }
    },
  }))
}
