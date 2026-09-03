import z from '@deepseek-ai/schemastery'
import {
  PersistenceCoordinator,
  SessionPersistence,
  SessionPersistenceRevision,
} from '@deepseek-ai/dsh-session-persistence'
import TencentCloudSdk from 'tencentcloud-sdk-nodejs-ags'

const { Client } = TencentCloudSdk.ags.v20250920

function required(value, name) {
  const result = value?.trim()
  if (!result) throw new Error(`${name} is required`)
  return result
}

function parseJson(value, fallback = {}) {
  if (value === undefined || value === null || value === '') return fallback
  return typeof value === 'string' ? JSON.parse(value) : value
}

function headerFromSession(session) {
  const state = parseJson(session?.State?.CustomState)
  if (!state.dshHeader) throw new Error(`Session ${session?.SessionId ?? '<unknown>'} has no DSH header`)
  return state.dshHeader
}

function eventFromSummary(summary) {
  const extensions = parseJson(summary.Extensions)
  if (!extensions.dshEvent) throw new Error(`Event ${summary.EventId} has no DSH event payload`)
  return extensions.dshEvent
}

function objectFromJson(value) {
  try {
    const parsed = typeof value === 'string' ? JSON.parse(value) : value
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed)
      ? parsed
      : { value: parsed }
  } catch {
    return { raw: String(value) }
  }
}

function textFromContent(content) {
  if (!Array.isArray(content)) return ''
  return content.flatMap(part => {
    if (part?.type === 'text' && typeof part.text === 'string') return [part.text]
    if (part?.type === 'tool-result' && Array.isArray(part.content)) {
      return part.content
        .filter(item => item?.type === 'text' && typeof item.text === 'string')
        .map(item => item.text)
    }
    return []
  }).join('\n')
}

function contentParts(content) {
  if (!Array.isArray(content)) return []
  return content.flatMap(part => {
    if (part?.type === 'text' && typeof part.text === 'string') return [{ Text: part.text }]
    if (part?.type === 'reasoning' && typeof part.text === 'string') {
      return [{ Text: part.text, Thought: true }]
    }
    if (part?.type === 'tool-call' && typeof part.name === 'string') {
      return [{
        FunctionCall: JSON.stringify({ Name: part.name, Args: objectFromJson(part.arguments ?? {}) }),
      }]
    }
    if (part?.type === 'tool-result') {
      return [{
            FunctionResponse: JSON.stringify({
              Name: part.toolCallId ?? 'tool',
              Response: {
                content: textFromContent(part.content),
                isError: part.isError === true,
              },
            }),
      }]
    }
    return []
  })
}

function contentProjection(event) {
  if (event.type === 'user/message') {
    const parts = contentParts(event.data?.content)
    return parts.length === 0 ? {} : { Author: 'user', Content: { Role: 'user', Parts: parts } }
  }
  if (event.type === 'assistant/message') {
    const parts = contentParts(event.data?.message?.content)
    return parts.length === 0 ? {} : { Author: 'assistant', Content: { Role: 'assistant', Parts: parts } }
  }
  if (event.type === 'assistant/chunk') {
    const chunk = event.data?.chunk
    if ((chunk?.type === 'text-delta' || chunk?.type === 'reasoning-delta') && typeof chunk.text === 'string') {
      return {
        Author: 'assistant',
        Content: {
          Role: 'assistant',
          Parts: [{ Text: chunk.text, ...(chunk.type === 'reasoning-delta' ? { Thought: true } : {}) }],
        },
      }
    }
  }
  if (event.type === 'tool/call' && typeof event.data?.name === 'string') {
    return {
      Author: 'assistant',
      Content: {
        Role: 'assistant',
        Parts: [{
          FunctionCall: JSON.stringify({
            Name: event.data.name,
            Args: objectFromJson(event.data.arguments ?? {}),
          }),
        }],
      },
    }
  }
  if (event.type === 'tool/result') {
    const result = event.data?.message?.content?.find(part => part?.type === 'tool-result')
    if (result) {
      return {
        Author: 'tool',
        Content: {
          Role: 'tool',
          Parts: [{
            FunctionResponse: JSON.stringify({
              Name: result.toolCallId ?? event.data?.message?.source?.callId ?? 'tool',
              Response: {
                content: textFromContent(result.content),
                isError: result.isError === true,
              },
            }),
          }],
        },
      }
    }
  }
  return {}
}

function actionsProjection(event) {
  const stateByType = {
    'permission/preset': ['permissionPreset', event.data?.preset],
    'sandbox/mode': ['sandboxMode', event.data?.mode],
    'approval/policy': ['approvalPolicy', event.data?.policy],
    'session/title': ['sessionTitle', event.data?.title],
  }
  const state = stateByType[event.type]
  return state?.[1] === undefined
    ? undefined
    : { StateDelta: JSON.stringify({ [state[0]]: state[1] }) }
}

function terminalProjection(event) {
  const metadata = {
    source: 'deepseek-harness',
    dshEventType: event.type,
    dshSeq: event.seq,
  }
  if (Number.isInteger(event.data?.turn)) metadata.Turn = event.data.turn
  if (Number.isInteger(event.data?.step)) metadata.Step = event.data.step
  if (event.type === 'assistant/chunk') metadata.Partial = true
  if (event.type === 'turn/end') {
    metadata.TurnComplete = true
    metadata.Interrupted = ['aborted', 'disposed', 'interrupted'].includes(event.data?.reason?.kind)
  }

  const turnError = event.type === 'turn/end' && event.data?.reason?.kind === 'error'
    ? event.data.reason.error
    : undefined
  const chunkFailure = event.type === 'assistant/chunk'
    ? event.data?.chunk?.reason?.failure
    : undefined
  const toolResult = event.type === 'tool/result'
    ? event.data?.message?.content?.find(part => part?.type === 'tool-result' && part.isError === true)
    : undefined
  const failure = turnError ?? chunkFailure
  if (failure) {
    return {
      Metadata: metadata,
      ErrorCode: failure.code ?? 'DSH_ERROR',
      ErrorMessage: failure.message ?? String(failure),
    }
  }
  if (toolResult) {
    return {
      Metadata: metadata,
      ErrorCode: 'TOOL_ERROR',
      ErrorMessage: textFromContent(toolResult.content),
    }
  }
  return { Metadata: metadata }
}

function invocationId(event, sessionId) {
  return event.data?.source?.rpcId
    ?? event.data?.message?.source?.rpcId
    ?? event.data?.callId
    ?? `dsh-${sessionId}`
}

function stableEventId(sessionId, seq) {
  return `dsh-${sessionId}-${seq}`
}

function revisionFromSession(session, eventCount = session.EventCount ?? 0) {
  return SessionPersistenceRevision(
    `agent-runtime:${session.SessionId}:${eventCount}`,
  )
}

function isSessionNotFound(error) {
  return error?.code === 'ResourceNotFound.SessionNotExist'
}

export class AgentRuntimeSessionPersistence extends SessionPersistence {
  static inject = ['sessions']

  static Config = z.object({
    region: z.string().required(),
    endpoint: z.string(),
    spaceId: z.string().required(),
    userId: z.string().required(),
    brainDeploymentId: z.string().required(),
    secretId: z.string().required(),
    secretKey: z.string().required(),
    sessionToken: z.string(),
  })

  supportsRawArtifacts = false
  name = 'session-persistence-agent-runtime'

  constructor(ctx, config) {
    super(ctx)
    this.config = config
    const clientConfig = {
      credential: {
        secretId: required(config.secretId, 'TENCENTCLOUD_SECRET_ID'),
        secretKey: required(config.secretKey, 'TENCENTCLOUD_SECRET_KEY'),
        token: config.sessionToken || undefined,
      },
      region: required(config.region, 'AGR_REGION'),
      profile: {
        httpProfile: config.endpoint ? { endpoint: config.endpoint } : {},
      },
    }
    this.client = new Client(clientConfig)
    this.spaceId = required(config.spaceId, 'SESSION_SPACE_ID')
    this.userId = required(config.userId, 'SESSION_USER_ID')
    this.brainDeploymentId = required(config.brainDeploymentId, 'BRAIN_DEPLOYMENT_ID')
    this.coordinator = new PersistenceCoordinator(this.ctx, this)
  }

  locate() {
    return undefined
  }

  request(action, payload) {
    // Session actions may be newer than the generated SDK surface. AbstractClient's
    // public request path still supplies TC3 signing, retries, and endpoint handling.
    return this.client.request(action, payload)
  }

  sessionRequest(sessionId, extra = {}) {
    return {
      SpaceId: this.spaceId,
      UserId: this.userId,
      SessionId: sessionId,
      ...extra,
    }
  }

  create(meta) {
    return this.coordinator.create(meta)
  }

  append(id, events) {
    return this.coordinator.append(id, events)
  }

  prepare(id, signal) {
    return this.coordinator.prepare(id, signal)
  }

  load(id) {
    return this.coordinator.load(id)
  }

  inspect(id, signal) {
    return this.coordinator.inspect(id, signal)
  }

  readFrom(id, fromSeq, signal) {
    return this.coordinator.readFrom(id, fromSeq, signal)
  }

  async appendEvents(id, events) {
    for (const event of events) {
      const projection = contentProjection(event)
      const terminal = terminalProjection(event)
      await this.request('AppendEvent', this.sessionRequest(id, {
        Event: {
          EventId: stableEventId(id, event.seq),
          InvocationId: invocationId(event, id),
          Author: projection.Author ?? 'dsh',
          Content: projection.Content,
          Actions: actionsProjection(event),
          Metadata: JSON.stringify(terminal.Metadata),
          ErrorCode: terminal.ErrorCode,
          ErrorMessage: terminal.ErrorMessage,
          Extensions: JSON.stringify({ dshEvent: event }),
        },
      }))
    }
  }

  async appendBatch(meta, events, isMaterialized) {
    if (!isMaterialized) {
      await this.request('CreateSession', this.sessionRequest(meta.id, {
        State: { CustomState: JSON.stringify({ dshHeader: meta }) },
        Metadata: [{
          Name: 'ae.tencentcloud.com/brain-deployment-id',
          Value: this.brainDeploymentId,
        }],
      }))
    }
    await this.appendEvents(meta.id, events)
  }

  async describeSession(id, recentEvents = 0) {
    const response = await this.request('DescribeSession', this.sessionRequest(id, {
      NumRecentEvents: recentEvents,
    }))
    if (!response.Session) throw new Error(`Session ${id} was not returned`)
    return response.Session
  }

  async describeEvents(id, signal) {
    const events = []
    for (let offset = 0; ; offset += 100) {
      signal?.throwIfAborted()
      const response = await this.request('DescribeEvents', this.sessionRequest(id, {
        Offset: offset,
        Limit: 100,
      }))
      const page = response.Events ?? []
      events.push(...page.map(eventFromSummary))
      if (events.length >= Number(response.TotalCount ?? events.length) || page.length === 0) break
    }
    events.sort((left, right) => left.seq - right.seq)
    for (let index = 0; index < events.length; index += 1) {
      if (events[index].seq !== index) {
        throw new Error(`Session ${id} has a non-contiguous DSH event log at seq ${index}`)
      }
    }
    return events
  }

  async loadStored(id, signal) {
    signal?.throwIfAborted()
    try {
      const [session, events] = await Promise.all([
        this.describeSession(id),
        this.describeEvents(id, signal),
      ])
      return {
        meta: headerFromSession(session),
        events,
        revision: revisionFromSession(session, events.length),
      }
    } catch (error) {
      if (isSessionNotFound(error)) return undefined
      throw error
    }
  }

  async readStoredRevision(id, signal) {
    signal?.throwIfAborted()
    try {
      const session = await this.describeSession(id)
      const response = await this.request('DescribeEvents', this.sessionRequest(id, {
        Offset: 0,
        Limit: 1,
      }))
      return revisionFromSession(session, Number(response.TotalCount ?? 0))
    } catch (error) {
      if (isSessionNotFound(error)) return undefined
      throw error
    }
  }

  async commitRepair(meta, tornMarker, closers) {
    if (tornMarker !== undefined) {
      throw new Error(`Session ${meta.id} has an unsupported torn Agent Runtime Event tail`)
    }
    await this.appendEvents(meta.id, closers)
  }

  async list(signal) {
    const headers = []
    for (let offset = 0; ; offset += 100) {
      signal?.throwIfAborted()
      const response = await this.request('DescribeSessions', {
        SpaceId: this.spaceId,
        UserIds: [this.userId],
        Offset: offset,
        Limit: 100,
      })
      const page = response.Sessions ?? []
      for (const session of page) {
        try {
          headers.push(headerFromSession(session))
        } catch {
          // A SessionSpace can contain Sessions created by other applications.
        }
      }
      if (offset + page.length >= Number(response.TotalCount ?? 0) || page.length === 0) break
    }
    return headers
  }

  async listSnapshots(signal) {
    const snapshots = []
    for (let offset = 0; ; offset += 100) {
      signal?.throwIfAborted()
      const response = await this.request('DescribeSessions', {
        SpaceId: this.spaceId,
        UserIds: [this.userId],
        Offset: offset,
        Limit: 100,
      })
      const page = response.Sessions ?? []
      for (const session of page) {
        try {
          snapshots.push({
            header: headerFromSession(session),
            revision: await this.readStoredRevision(session.SessionId, signal),
          })
        } catch {
          // Ignore Sessions not owned by this DSH persistence backend.
        }
      }
      if (offset + page.length >= Number(response.TotalCount ?? 0) || page.length === 0) break
    }
    return snapshots
  }
}

export default AgentRuntimeSessionPersistence
