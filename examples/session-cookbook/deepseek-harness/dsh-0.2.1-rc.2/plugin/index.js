import z from '@deepseek-ai/schemastery'
import { SESSION_FORMAT_VERSION, SessionLogOffset } from '@deepseek-ai/dsh-session'
import {
  SessionAlreadyExistsError,
  SessionAlreadyOwnedError,
  SessionHandleClosedError,
  SessionPersistence,
  SessionPersistenceCorruptionError,
  SessionPersistenceNotFoundError,
  SessionPersistenceRevision,
  SessionReadOnlyError,
  assertContiguous,
  assertStoredId,
  assertVersion,
  materializeAppendBatch,
  materializeCreateHeader,
  validateStoredEvents,
} from '@deepseek-ai/dsh-session-persistence'
import TencentCloudSdk from 'tencentcloud-sdk-nodejs-ags'

const { Client } = TencentCloudSdk.ags.v20250920

export const name = 'session-persistence-agent-runtime'

function required(value, name) {
  const result = value?.trim()
  if (!result) throw new Error(`${name} is required`)
  return result
}

function parseJson(value, fallback = {}) {
  if (value === undefined || value === null || value === '') return fallback
  return typeof value === 'string' ? JSON.parse(value) : value
}

// The DSH header and its inherited-prefix length live in the Session's CustomState.
function storedRecordFromSession(session) {
  const state = parseJson(session?.State?.CustomState)
  if (!state.dshHeader) throw new Error(`Session ${session?.SessionId ?? '<unknown>'} has no DSH header`)
  return {
    meta: state.dshHeader,
    inheritedEventCount: SessionLogOffset(state.dshInheritedEventCount ?? 0),
  }
}

// Listing skips Sessions this build cannot open: other applications' Sessions, and
// Sessions written by an older DSH format (0.1.x writes version 0 headers).
function currentRecordFromSession(session) {
  let record
  try {
    record = storedRecordFromSession(session)
  } catch {
    return undefined
  }
  return record.meta.version === SESSION_FORMAT_VERSION ? record : undefined
}

function eventFromSummary(summary) {
  const extensions = parseJson(summary.Extensions)
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
  return content
    .filter(part => part?.type === 'text' && typeof part.text === 'string')
    .map(part => part.text)
    .join('\n')
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
  if (event.type === 'tool/result' && event.data?.message) {
    const message = event.data.message
    return {
      Author: 'tool',
      Content: {
        Role: 'tool',
        Parts: [{
          FunctionResponse: JSON.stringify({
            Name: message.toolCallId ?? message.source?.callId ?? 'tool',
            Response: {
              content: textFromContent(message.content),
              isError: message.isError === true,
            },
          }),
        }],
      },
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
  // An attempt is a model stream that did not become the step's assistant message.
  if (event.type === 'assistant/attempt') metadata.Partial = true
  if (event.type === 'turn/end') {
    metadata.TurnComplete = true
    metadata.Interrupted = ['aborted', 'interrupted'].includes(event.data?.reason?.kind)
  }

  if (event.type === 'turn/end' && event.data?.reason?.kind === 'error') {
    const failure = event.data.reason.error
    return {
      Metadata: metadata,
      ErrorCode: failure?.code ?? 'DSH_ERROR',
      ErrorMessage: failure?.message ?? String(failure),
    }
  }
  if (event.type === 'tool/result' && event.data?.error) {
    const failure = event.data.error
    return {
      Metadata: metadata,
      ErrorCode: failure.code,
      ErrorMessage: failure.reason ?? failure.name,
    }
  }
  if (event.type === 'tool/result' && event.data?.message?.isError === true) {
    return {
      Metadata: metadata,
      ErrorCode: 'TOOL_ERROR',
      ErrorMessage: textFromContent(event.data.message.content),
    }
  }
  return { Metadata: metadata }
}

function invocationId(event, sessionId) {
  return event.data?.source?.rpcId
    ?? event.data?.message?.source?.rpcId
    ?? event.data?.callId
    ?? event.data?.message?.source?.callId
    ?? `dsh-${sessionId}`
}

function stableEventId(sessionId, seq) {
  return `dsh-${sessionId}-${seq}`
}

function revisionFromEventCount(sessionId, eventCount) {
  return SessionPersistenceRevision(`agent-runtime:${sessionId}:${eventCount}`)
}

function isSessionNotFound(error) {
  return error?.code === 'ResourceNotFound.SessionNotExist'
}

function isSessionIdDuplicate(error) {
  return error?.code === 'ResourceInUse.SessionIdDuplicate'
}

// Fork lineage: a seeded header carries its inherited prefix length; an unseeded header carries 0.
function inheritedCount(header, value) {
  if (header.isSeeded && value === undefined) throw new Error('seeded session header requires an inherited event count')
  const count = SessionLogOffset(value ?? 0)
  if (!header.isSeeded && count !== 0) throw new Error('unseeded session header inherited event count must be 0')
  return count
}

function deepFreeze(value) {
  if (value && typeof value === 'object' && !Object.isFrozen(value)) {
    Object.freeze(value)
    for (const child of Object.values(value)) deepFreeze(child)
  }
  return value
}

export const AGENT_METADATA_KEY = 'example.com/dsh-agent-id'

const MAX_RATE_LIMIT_RETRIES = 5

// Matches the official JSONL backend: the first routed live event opens a fixed batching window.
const LIVE_BATCH_WINDOW_MS = 200

function isRateLimited(error) {
  return String(error?.code ?? '').startsWith('RequestLimitExceeded')
}

/**
 * One open channel onto a stored Session. Mutations serialize on a per-handle
 * promise chain. A write handle is the Session's only writer in this process,
 * so it keeps the log it has opened and appended in memory and serves its own
 * reads from it; a read handle reads the Session API.
 */
export class AgentRuntimeSessionHandle {
  chain = Promise.resolve()
  closing
  observedLength = 0
  /** Routed live events awaiting their batching deadline. */
  buffered = []
  batchTimer
  /** Set when a drain failed; the automatic timer stays quiet until the next drain. */
  drainPaused = false
  draining

  constructor(backend, header, access, state) {
    this.backend = backend
    this.id = header.id
    this.header = header
    this.access = access
    // { cursor, materialized, inheritedEventCount, events } — events only on a write handle.
    this.state = state
  }

  get inheritedEventCount() {
    return this.state.inheritedEventCount
  }

  async read(offset = 0, length = Number.MAX_SAFE_INTEGER, options) {
    this.assertOpen('read')
    if (!Number.isSafeInteger(offset) || offset < 0) throw new TypeError(`read offset must be a non-negative safe integer, got ${String(offset)}`)
    if (!Number.isSafeInteger(length) || length < 0) throw new TypeError(`read length must be a non-negative safe integer, got ${String(length)}`)
    options?.signal?.throwIfAborted()
    const events = this.access === 'write'
      ? this.state.events
      : await this.backend.readCurrentLog(this.id, options?.signal)
    if (events.length < this.observedLength) {
      throw new Error(`session "${this.id}": stored log shrank below a previously observed prefix (${events.length} < ${this.observedLength})`)
    }
    this.observedLength = events.length
    return { eventState: 'shared-frozen', events: events.slice(offset, offset + length) }
  }

  async append(events, options) {
    this.assertOpen('append')
    const batch = materializeAppendBatch(events)
    return this.run('append', async () => {
      options?.signal?.throwIfAborted()
      await this.persistContiguous(batch)
    })
  }

  // AppendEvent persists on resolution, so flush only has to materialize an empty Session.
  flush(options) {
    return this.run('flush', async () => {
      options?.signal?.throwIfAborted()
      if (this.access !== 'write') throw new SessionReadOnlyError(this.id, 'flush')
      await this.materialize()
    })
  }

  close() {
    return this.closing ??= (async () => {
      let drainFailure
      for (;;) {
        try {
          await this.drainLive()
        } catch (error) {
          drainFailure = error
          break
        }
        await this.chain
        if (this.buffered.length === 0) break
      }
      await this.chain
      this.backend.tracker.release(this, this.state.materialized)
      if (drainFailure !== undefined) throw drainFailure
    })()
  }

  [Symbol.asyncDispose]() {
    return this.close()
  }

  enqueueLive(event, reportBackgroundFailure) {
    this.buffered.push(structuredClone(event))
    if (this.batchTimer !== undefined || this.drainPaused) return
    this.batchTimer = setTimeout(() => {
      this.batchTimer = undefined
      this.drainLive().catch(reportBackgroundFailure)
    }, LIVE_BATCH_WINDOW_MS)
  }

  drainLive() {
    return this.draining ??= this.drainBuffered().finally(() => {
      this.draining = undefined
    })
  }

  async drainBuffered() {
    if (this.batchTimer !== undefined) {
      clearTimeout(this.batchTimer)
      this.batchTimer = undefined
    }
    this.drainPaused = false
    while (this.buffered.length > 0) {
      await this.enqueueChain(async () => {
        const batch = this.buffered.splice(0)
        try {
          await this.persistContiguous(materializeAppendBatch(batch))
        } catch (error) {
          // Keep the batch in order; session/flush or close retries it and rejects loudly.
          this.buffered = batch.concat(this.buffered)
          this.drainPaused = true
          throw error
        }
      })
    }
  }

  // The cursor advances only after the whole batch is stored. A retried batch resends
  // events that already landed; AppendEvent accepts an identical EventId retry.
  async persistContiguous(batch) {
    if (this.access !== 'write') throw new SessionReadOnlyError(this.id, 'append')
    if (batch.length === 0) return
    assertContiguous(this.id, batch, this.state.cursor)
    await this.materialize()
    await this.backend.appendEvents(this.id, batch)
    for (const event of batch) this.state.events.push(deepFreeze(event))
    this.state.cursor += batch.length
  }

  async materialize() {
    if (this.state.materialized) return
    await this.backend.createStoredSession(this.header, this.state.inheritedEventCount)
    this.state.materialized = true
    this.backend.tracker.materialized(this.id)
  }

  enqueueChain(op) {
    const next = this.chain.then(op)
    this.chain = next.catch(() => {})
    return next
  }

  async run(operation, op) {
    this.assertOpen(operation)
    return this.enqueueChain(async () => {
      this.assertOpen(operation)
      return op()
    })
  }

  assertOpen(operation) {
    if (this.closing !== undefined) throw new SessionHandleClosedError(this.id, operation)
  }
}

/**
 * In-process bookkeeping: the single active writer per Session id (doubling as
 * the live event router), the open-handle set teardown closes, and the
 * created-but-unmaterialized Sessions this process can already observe.
 */
export class AgentRuntimeBackendTracker {
  openHandles = new Set()
  /** `null` marks a claim whose handle is still being constructed. */
  writers = new Map()
  pending = new Map()
  counter = 0

  constructor(name) {
    this.name = name
  }

  registerCreated(header, inheritedEventCount) {
    if (this.writers.has(header.id)) throw new SessionAlreadyExistsError(header.id)
    this.writers.set(header.id, null)
    this.pending.set(header.id, {
      header,
      inheritedEventCount,
      revision: SessionPersistenceRevision(`memory:${this.name}:${++this.counter}`),
    })
  }

  claimWrite(id) {
    if (this.writers.has(id)) throw new SessionAlreadyOwnedError(id)
    this.writers.set(id, null)
  }

  releaseClaim(id) {
    this.writers.delete(id)
  }

  pendingOf(id) {
    return this.pending.get(id)
  }

  pendingEntries() {
    return this.pending.entries()
  }

  materialized(id) {
    this.pending.delete(id)
  }

  /** The active write handle for a Session, when this process holds one. */
  writerOf(id) {
    return this.writers.get(id) ?? undefined
  }

  adopt(handle) {
    this.openHandles.add(handle)
    if (handle.access === 'write') this.writers.set(handle.id, handle)
    return handle
  }

  // A creator that never materialized leaves nothing behind: the Session never existed.
  release(handle, materialized) {
    this.openHandles.delete(handle)
    if (handle.access !== 'write') return
    this.writers.delete(handle.id)
    if (!materialized) this.pending.delete(handle.id)
  }

  async flushAll() {
    const errors = []
    for (const writer of [...this.writers.values()]) {
      if (writer === null) continue
      try {
        await writer.drainLive()
        await writer.flush()
      } catch (error) {
        if (error instanceof SessionHandleClosedError) continue
        errors.push(error)
      }
    }
    if (errors.length > 0) throw new AggregateError(errors, `${this.name} flush failed`)
  }

  install(ctx) {
    const { writers, openHandles, name } = this
    return ctx.effect(function* () {
      yield async () => {
        const errors = []
        for (const handle of [...openHandles]) {
          try {
            await handle.close()
          } catch (error) {
            errors.push(error)
          }
        }
        if (errors.length > 0) throw new AggregateError(errors, `${name} dispose failed`)
      }
      yield ctx.on('session/event', (session, event) => {
        writers.get(session.id)?.enqueueLive(event, error => {
          ctx.logger.warn(`session-persistence: background write for session "${session.id}" failed (buffered events retained): ${String(error)}`)
        })
      })
      yield ctx.on('session/flush', session => {
        const writer = writers.get(session.id)
        if (writer === null || writer === undefined) return undefined
        return (async () => {
          await writer.drainLive()
          await writer.flush()
        })()
      })
      yield ctx.on('session/disposed', session => {
        const writer = writers.get(session.id)
        if (writer === null || writer === undefined) return
        writer.close().catch(error => {
          ctx.logger.warn(`session-persistence: final drain for session "${session.id}" failed: ${String(error)}`)
        })
      })
    }, `${name} live routing and open handles`)
  }
}

export class AgentRuntimeSessionPersistence extends SessionPersistence {
  name = name

  constructor(ctx, config, tracker) {
    super(ctx)
    this.config = config
    this.tracker = tracker
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
    this.agentId = config.agentId?.trim() || undefined
  }

  async request(action, payload) {
    // Session actions may be newer than the generated SDK surface. AbstractClient's
    // public request path still supplies TC3 signing, retries, and endpoint handling.
    // Rate-limited calls were not executed, so retrying them is safe; AppendEvent is
    // also idempotent through its stable EventId.
    for (let attempt = 0; ; attempt += 1) {
      try {
        return await this.client.request(action, payload)
      } catch (error) {
        if (!isRateLimited(error) || attempt >= MAX_RATE_LIMIT_RETRIES) throw error
        await new Promise(resolve => setTimeout(resolve, this.retryDelayMs(attempt)))
      }
    }
  }

  retryDelayMs(attempt) {
    return 200 * 2 ** attempt + Math.random() * 100
  }

  // Headers are immutable, so each process reads a Session's header at most once.
  recordCache() {
    this.records ??= new Map()
    return this.records
  }

  sessionRequest(sessionId, extra = {}) {
    return {
      SpaceId: this.spaceId,
      UserId: this.userId,
      SessionId: sessionId,
      ...extra,
    }
  }

  // With SESSION_AGENT_ID set, Sessions are tagged with it on creation and listed by it.
  agentFilters() {
    return this.agentId ? { Filters: [{ Name: `metadata:${AGENT_METADATA_KEY}`, Values: [this.agentId] }] } : {}
  }

  ownsSession(session) {
    return !this.agentId || session.Metadata?.some(item => item.Name === AGENT_METADATA_KEY && item.Value === this.agentId)
  }

  async create(header, options) {
    options?.signal?.throwIfAborted()
    const snapshot = materializeCreateHeader(header)
    const inheritedEventCount = inheritedCount(snapshot, options?.inheritedEventCount)
    if (this.tracker.pendingOf(snapshot.id) !== undefined || await this.sessionExists(snapshot.id)) {
      throw new SessionAlreadyExistsError(snapshot.id)
    }
    options?.signal?.throwIfAborted()
    // The Session is visible to this process now; CreateSession runs on the first append or flush.
    this.tracker.registerCreated(snapshot, inheritedEventCount)
    return this.tracker.adopt(new AgentRuntimeSessionHandle(this, snapshot, 'write', {
      cursor: 0,
      materialized: false,
      inheritedEventCount,
      events: [],
    }))
  }

  async open(id, access, options) {
    options?.signal?.throwIfAborted()
    if (access === 'read') {
      const pending = this.tracker.pendingOf(id)
      if (pending !== undefined) {
        return this.tracker.adopt(new AgentRuntimeSessionHandle(this, pending.header, 'read', {
          materialized: false,
          inheritedEventCount: pending.inheritedEventCount,
        }))
      }
      const stored = await this.requireStored(id, options?.signal)
      return this.tracker.adopt(new AgentRuntimeSessionHandle(this, stored.meta, 'read', {
        materialized: true,
        inheritedEventCount: stored.inheritedEventCount,
      }))
    }
    this.tracker.claimWrite(id)
    try {
      const stored = await this.requireStored(id, options?.signal)
      options?.signal?.throwIfAborted()
      return this.tracker.adopt(new AgentRuntimeSessionHandle(this, stored.meta, 'write', {
        cursor: stored.events.length,
        materialized: true,
        inheritedEventCount: stored.inheritedEventCount,
        events: stored.events,
      }))
    } catch (error) {
      this.tracker.releaseClaim(id)
      throw error
    }
  }

  flush() {
    return this.tracker.flushAll()
  }

  async stat(id, options) {
    options?.signal?.throwIfAborted()
    const pending = this.tracker.pendingOf(id)
    if (pending !== undefined) return { header: pending.header, revision: pending.revision }
    let session
    try {
      session = await this.describeSession(id)
    } catch (error) {
      if (isSessionNotFound(error)) return undefined
      throw error
    }
    if (!this.ownsSession(session)) return undefined
    const record = currentRecordFromSession(session)
    if (!record) return undefined
    this.recordCache().set(id, record)
    return { header: record.meta, revision: await this.revision(id, options?.signal) }
  }

  async list(options) {
    const signal = options?.signal
    const snapshots = []
    const listed = new Set()
    for (let offset = 0; ; offset += 100) {
      signal?.throwIfAborted()
      const response = await this.request('DescribeSessions', {
        SpaceId: this.spaceId,
        UserIds: [this.userId],
        ...this.agentFilters(),
        Offset: offset,
        Limit: 100,
      })
      const page = response.Sessions ?? []
      for (const session of page) {
        if (!this.ownsSession(session)) continue
        const record = await this.listedRecord(session)
        if (!record) continue
        listed.add(session.SessionId)
        snapshots.push({ header: record.meta, revision: await this.revision(session.SessionId, signal) })
      }
      if (offset + page.length >= Number(response.TotalCount ?? 0) || page.length === 0) break
    }
    for (const [id, entry] of this.tracker.pendingEntries()) {
      if (!listed.has(id)) snapshots.push({ header: entry.header, revision: entry.revision })
    }
    signal?.throwIfAborted()
    return snapshots
  }

  async listedRecord(summary) {
    const cache = this.recordCache()
    if (cache.has(summary.SessionId)) return cache.get(summary.SessionId)
    // DescribeSessions rows carry no State, so the DSH header has to come from DescribeSession.
    const session = summary.State === undefined ? await this.describeSession(summary.SessionId) : summary
    const record = currentRecordFromSession(session)
    cache.set(summary.SessionId, record)
    return record
  }

  async revision(id, signal) {
    signal?.throwIfAborted()
    const response = await this.request('DescribeEvents', this.sessionRequest(id, {
      Offset: 0,
      Limit: 1,
    }))
    return revisionFromEventCount(id, Number(response.TotalCount ?? 0))
  }

  async sessionExists(id) {
    try {
      await this.describeSession(id)
      return true
    } catch (error) {
      if (isSessionNotFound(error)) return false
      throw error
    }
  }

  // The current log for a read handle: an in-process writer's log is fresher than the API.
  async readCurrentLog(id, signal) {
    const writer = this.tracker.writerOf(id)
    if (writer !== undefined) return writer.state.events
    if (this.tracker.pendingOf(id) !== undefined) return []
    return (await this.requireStored(id, signal)).events
  }

  async requireStored(id, signal) {
    const stored = await this.loadStored(id, signal)
    if (stored === undefined) throw new SessionPersistenceNotFoundError(id)
    return stored
  }

  async loadStored(id, signal) {
    signal?.throwIfAborted()
    let session
    let events
    try {
      [session, events] = await Promise.all([
        this.describeSession(id),
        this.describeEvents(id, signal),
      ])
    } catch (error) {
      if (isSessionNotFound(error)) return undefined
      throw error
    }
    if (!this.ownsSession(session)) throw new Error(`Session ${id} belongs to another SESSION_AGENT_ID`)
    const { meta, inheritedEventCount } = storedRecordFromSession(session)
    assertStoredId(id, meta)
    assertVersion(meta)
    for (let index = 0; index < events.length; index += 1) {
      if (events[index].seq !== index) {
        throw new SessionPersistenceCorruptionError(
          `Session ${id} has a non-contiguous DSH event log at seq ${index}`,
          { cause: new Error(`expected seq ${index}, got ${events[index].seq}`) },
        )
      }
    }
    // Validation freezes message payloads only; handles share these events, so freeze them whole.
    return { meta, inheritedEventCount, events: validateStoredEvents(meta, events).map(deepFreeze) }
  }

  async createStoredSession(header, inheritedEventCount) {
    const state = {
      dshHeader: header,
      ...(inheritedEventCount === 0 ? {} : { dshInheritedEventCount: inheritedEventCount }),
    }
    try {
      await this.request('CreateSession', this.sessionRequest(header.id, {
        State: { CustomState: JSON.stringify(state) },
        ...(this.agentId ? { Metadata: [{ Name: AGENT_METADATA_KEY, Value: this.agentId }] } : {}),
      }))
    } catch (error) {
      if (!isSessionIdDuplicate(error)) throw error
      // A retried CreateSession whose first attempt landed stores the same header.
      const existing = storedRecordFromSession(await this.describeSession(header.id))
      if (JSON.stringify(existing.meta) !== JSON.stringify(header)) throw new SessionAlreadyExistsError(header.id)
    }
    this.recordCache().set(header.id, { meta: header, inheritedEventCount })
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

  async describeSession(id, recentEvents = 0) {
    const response = await this.request('DescribeSession', this.sessionRequest(id, {
      NumRecentEvents: recentEvents,
    }))
    if (!response.Session) throw new Error(`Session ${id} was not returned`)
    return response.Session
  }

  async describeEvents(id, signal) {
    const events = []
    let offset = 0
    for (;;) {
      signal?.throwIfAborted()
      const response = await this.request('DescribeEvents', this.sessionRequest(id, {
        Offset: offset,
        Limit: 100,
      }))
      const page = response.Events ?? []
      events.push(...page.map(eventFromSummary).filter(Boolean))
      offset += page.length
      if (offset >= Number(response.TotalCount ?? offset) || page.length === 0) break
    }
    events.sort((left, right) => left.seq - right.seq)
    return events
  }
}

export const Config = z.object({
  region: z.string().required(),
  endpoint: z.string(),
  spaceId: z.string().required(),
  userId: z.string().required(),
  agentId: z.string(),
  secretId: z.string().required(),
  secretKey: z.string().required(),
  sessionToken: z.string(),
})

/**
 * Mount the Session-API persistence service with live routing, keeping handles
 * open through the consumer unloads triggered by removing this provider.
 */
export async function apply(ctx, config) {
  let service
  ctx.effect(function* () {
    const tracker = new AgentRuntimeBackendTracker(name)
    yield tracker.install(ctx)
    service = ctx.plugin({
      name: `${name}-service`,
      apply(serviceCtx) {
        new AgentRuntimeSessionPersistence(serviceCtx, config, tracker)
      },
    })
    yield service.dispose
  }, `${name} resources`)
  await service.await()
}
