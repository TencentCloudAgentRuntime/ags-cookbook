import type { Role, RuntimeConfig } from './types.js'

export function taskConfigMap(name: string, prompt: string): unknown {
  return {
    apiVersion: 'v1',
    kind: 'ConfigMap',
    metadata: { name: `${name}-task`, labels: { app: 'dsh-awv', role: 'agent' } },
    data: { 'task.md': prompt },
  }
}

export function agentJob(name: string, role: Role, config: RuntimeConfig): unknown {
  const nodeName = role === 'code' ? config.codeNode : config.reviewNode
  const profile = role === 'code' ? 'code.patch.yml' : 'review.patch.yml'
  return {
    apiVersion: 'batch/v1',
    kind: 'Job',
    metadata: { name, labels: { app: 'dsh-awv', role } },
    spec: {
      backoffLimit: 0,
      activeDeadlineSeconds: 1200,
      ttlSecondsAfterFinished: 1800,
      template: {
        metadata: { labels: { app: 'dsh-awv', role } },
        spec: {
          automountServiceAccountToken: false,
          restartPolicy: 'Never',
          ...(config.imagePullSecret === undefined || config.imagePullSecret === '' ? {} : {
            imagePullSecrets: [{ name: config.imagePullSecret }],
          }),
          ...(nodeName === undefined || nodeName === '' ? {} : {
            nodeSelector: { 'kubernetes.io/hostname': nodeName },
          }),
          securityContext: { runAsUser: 10001, runAsGroup: 10001, fsGroup: 10001, fsGroupChangePolicy: 'OnRootMismatch' },
          containers: [{
            name: 'agent',
            image: config.workerImage,
            imagePullPolicy: 'IfNotPresent',
            workingDir: '/workspace/site',
            command: ['/usr/bin/tini', '--', 'dsh'],
            args: ['--profile', 'headless', '--patch', `/opt/pelican/profiles/${profile}`, '$(DSH_TASK)'],
            envFrom: [{ secretRef: { name: config.modelSecret } }],
            env: [
              { name: 'DSH_TASK', valueFrom: { configMapKeyRef: { name: `${name}-task`, key: 'task.md' } } },
              { name: 'HOME', value: '/tmp/dsh' },
              { name: 'DSH_HOME', value: '/tmp/dsh' },
              { name: 'DSH_PERMISSION_MODE', value: 'danger-full-access' },
            ],
            resources: { requests: { cpu: '1', memory: '2Gi' }, limits: { cpu: '2', memory: '4Gi' } },
            volumeMounts: [
              { name: 'workspace', mountPath: '/workspace/site', readOnly: role === 'review' },
              { name: 'dsh-home', mountPath: '/tmp/dsh' },
              ...(role === 'review' ? [{ name: 'review-output', mountPath: '/tmp/review' }] : []),
            ],
          }],
          volumes: [
            { name: 'workspace', persistentVolumeClaim: { claimName: config.workspaceClaim } },
            { name: 'dsh-home', emptyDir: {} },
            ...(role === 'review' ? [{ name: 'review-output', emptyDir: {} }] : []),
          ],
        },
      },
    },
  }
}
