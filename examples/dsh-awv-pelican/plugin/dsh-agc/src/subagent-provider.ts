import { randomUUID } from 'node:crypto'
import type { ContentBlock } from '@deepseek-ai/dsh-llm'
import type { SessionId } from '@deepseek-ai/dsh-session'
import type {
  ResolvedSubagentStartRequest,
  SubagentCapabilities,
  SubagentProvider,
  SubagentRun,
} from '@deepseek-ai/dsh-subagent'
import { agentJob, taskConfigMap } from './job-builder.js'
import { applyObject, deleteObject, kubectl } from './kubectl.js'
import { stopSite, waitForJob } from './job-watcher.js'
import { acquireLease } from './workspace-lease.js'
import { readState, writeState } from './workspace-state.js'
import type { Role, RuntimeConfig } from './types.js'

const NO_CAPABILITIES: SubagentCapabilities = {
  agentOptions: false,
  outputSchema: false,
  depthLimit: false,
  toolFilter: false,
  persona: false,
}

function promptText(blocks: ContentBlock[]): string {
  return blocks.filter((block): block is Extract<ContentBlock, { type: 'text' }> => block.type === 'text')
    .map(block => block.text).join('\n')
}

function safeName(role: Role): string {
  return `${role}-agent-${Date.now().toString(36)}-${randomUUID().slice(0, 6)}`
}

interface CodeResult {
  status: 'OK'
  summary: string
}

interface ReviewResult {
  status: 'PASS' | 'FAIL'
  summary: string
  blocking_issues: string[]
  evidence: string[]
}

function resultJson(logs: string, prefix: string): unknown {
  const markers = logs.split('\n').filter(line => line.includes(prefix))
  for (const marker of markers.reverse()) {
    const value = marker.slice(marker.indexOf(prefix) + prefix.length).trim()
    try {
      return JSON.parse(value) as unknown
    } catch {
      // 模型可能在说明中引用结果格式；继续查找最后一个有效结果。
    }
  }
  throw new Error(`Agent 未输出有效结果：${prefix}`)
}

function stringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every(item => typeof item === 'string')
}

export function codeResult(logs: string): CodeResult {
  const parsed = resultJson(logs, 'DSH_CODE_RESULT=') as Partial<CodeResult>
  if (parsed.status !== 'OK' || typeof parsed.summary !== 'string') {
    throw new Error('Code Agent 结果字段无效')
  }
  return { status: parsed.status, summary: parsed.summary }
}

export function reviewResult(logs: string): ReviewResult {
  const parsed = resultJson(logs, 'DSH_REVIEW_RESULT=') as Partial<ReviewResult>
  if ((parsed.status !== 'PASS' && parsed.status !== 'FAIL')
    || typeof parsed.summary !== 'string'
    || !stringArray(parsed.blocking_issues)
    || !stringArray(parsed.evidence)) {
    throw new Error('Review Agent 结果字段无效')
  }
  if (parsed.status === 'PASS' && parsed.blocking_issues.length > 0) {
    throw new Error('Review PASS 不能包含 blocking_issues')
  }
  return {
    status: parsed.status,
    summary: parsed.summary,
    blocking_issues: parsed.blocking_issues,
    evidence: parsed.evidence,
  }
}

export class KubernetesSubagentProvider implements SubagentProvider {
  readonly capabilities = NO_CAPABILITIES
  readonly inheritsParentContext = false

  constructor(
    readonly name: string,
    private readonly role: Role,
    private readonly config: RuntimeConfig,
  ) {}

  async start(request: ResolvedSubagentStartRequest): Promise<SubagentRun> {
    const runId = randomUUID() as SessionId
    const jobName = safeName(this.role)
    const release = await acquireLease(this.config.namespace)
    let disposed = false
    try {
      await stopSite(this.config.namespace)
      await applyObject(this.config.namespace, taskConfigMap(jobName, promptText(request.prompt)), request.signal)
      await applyObject(this.config.namespace, agentJob(jobName, this.role, this.config), request.signal)
    } catch (error) {
      await deleteObject(this.config.namespace, 'configmap', `${jobName}-task`)
      await release()
      throw error
    }

    const result = (async () => {
      try {
        const logs = await waitForJob(this.config.namespace, jobName, request.signal)
        const state = await readState(this.config.namespace)
        if (this.role === 'code') {
          const code = codeResult(logs)
          const next = {
            ...state,
            generation: state.generation + 1,
            reviewStatus: 'DIRTY' as const,
            lastCodeJob: jobName,
            updatedAt: new Date().toISOString(),
          }
          await writeState(this.config.namespace, next)
          return {
            output: [{ type: 'text' as const, text: JSON.stringify({ ...code, job: jobName, workspace_generation: next.generation }) }],
            stopReason: 'completed' as const,
          }
        }
        const review = reviewResult(logs)
        await writeState(this.config.namespace, {
          ...state,
          reviewedGeneration: state.generation,
          reviewStatus: review.status,
          lastReviewJob: jobName,
          updatedAt: new Date().toISOString(),
        })
        return {
          output: [{ type: 'text' as const, text: JSON.stringify({ ...review, job: jobName, workspace_generation: state.generation }) }],
          stopReason: 'completed' as const,
        }
      } catch (error) {
        return { output: [], diagnostic: String(error).slice(0, 4096), stopReason: request.signal.aborted ? 'aborted' as const : 'error' as const }
      } finally {
        await deleteObject(this.config.namespace, 'configmap', `${jobName}-task`)
        await release()
      }
    })()

    return {
      id: runId,
      localAgent: undefined,
      result,
      dispose: async () => {
        if (disposed) return
        disposed = true
        if (request.signal.aborted) await kubectl(this.config.namespace, ['delete', 'job', jobName, '--ignore-not-found=true']).catch(() => undefined)
        await result.then(() => undefined, () => undefined)
      },
    }
  }
}
