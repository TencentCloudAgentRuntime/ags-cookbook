export type Role = 'code' | 'review'

export interface RuntimeConfig {
  namespace: string
  workspaceClaim: string
  workerImage: string
  siteImage: string
  modelSecret: string
  imagePullSecret?: string
  serviceType: 'LoadBalancer' | 'ClusterIP'
  codeNode?: string
  reviewNode?: string
  siteNode?: string
}

export interface WorkspaceState {
  generation: number
  reviewedGeneration: number
  reviewStatus: 'NONE' | 'DIRTY' | 'PASS' | 'FAIL'
  lastCodeJob: string
  lastReviewJob: string
  updatedAt: string
}
