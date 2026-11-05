import type { Context } from '@deepseek-ai/cordis'
import z from '@deepseek-ai/schemastery'
import { KubernetesSubagentProvider } from './subagent-provider.js'
import { registerSiteTool } from './site-tools.js'
import type { RuntimeConfig } from './types.js'

export const name = 'agc-k8s'
export const inject = ['subagents', 'tools', 'systemPrompt']

export interface Config {
  namespace?: string
  workspaceClaim?: string
  workerImage?: string
  siteImage?: string
  modelSecret?: string
  imagePullSecret?: string
  serviceType?: 'LoadBalancer' | 'ClusterIP'
  codeNode?: string
  reviewNode?: string
  siteNode?: string
}

export const Config: z<Config> = z.object({
  namespace: z.string().default('dsh-awv'),
  workspaceClaim: z.string().default('pelican-workspace'),
  workerImage: z.string().required(),
  siteImage: z.string().default('nginxinc/nginx-unprivileged@sha256:42a7d7f2ee23e9f5a1dcdf3647ba5c585bbd18f79e79cd817e70e8cd61c55779'),
  modelSecret: z.string().default('dsh-model'),
  imagePullSecret: z.string(),
  serviceType: z.union(['LoadBalancer', 'ClusterIP'] as const).default('LoadBalancer'),
  codeNode: z.string(),
  reviewNode: z.string(),
  siteNode: z.string(),
})

const GUIDANCE = `处理网页任务时，由你根据用户需求规划 Sub Agent 任务：
1. 提取用户目标和可验证的验收条件，不要把流程说明原样转发给 Sub Agent。
2. 创建或修改页面时，先生成完整实现任务并调用 code_agent。用户明确要求先检查现有页面时，可以先调用 review_agent。
3. Code 完成后，基于原始需求生成独立评审任务并调用 review_agent。要求它用浏览器实际打开页面，检查桌面端、移动端、动画、交互和控制台错误。
4. Review 返回 FAIL 时，把原始验收条件和完整 blocking_issues 交给 code_agent 修复，然后重新调用 review_agent。
5. 最多调用一次 code_agent 修复。该调用无论成功或报错都计为一次；任一 Agent 报错时立即停止，不得重试或发布。第二次 Review 仍失败时停止，不得发布。
6. 只有 Review 返回 PASS 时才能调用 publish_site。
7. 最终回复列出 Code 状态、Review 结论和页面链接。`

export function apply(ctx: Context, config: Config): void {
  const resolved = config as RuntimeConfig
  ctx.subagents.registerProvider(new KubernetesSubagentProvider('agc-code', 'code', resolved))
  ctx.subagents.registerProvider(new KubernetesSubagentProvider('agc-review', 'review', resolved))
  registerSiteTool(ctx, resolved)
  ctx.systemPrompt.section({ name: 'agc-pelican-workflow', order: 90, text: GUIDANCE })
}
