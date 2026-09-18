const CORE_NODE_DEFINITIONS = [
  { id: 'registry', group: 'platform' },
  { id: 'coordinator', group: 'platform' },
  { id: 'bridge', group: 'platform' },
  { id: 'workspace', group: 'platform' },
]

function blankNode(definition) {
  return {
    ...definition,
    label: definition.label ?? null,
    description: definition.description ?? null,
    descriptorType: definition.descriptorType ?? null,
    status: definition.status ?? 'idle',
    calls: 0,
    completed: 0,
    failed: 0,
    latest: null,
    recordId: definition.recordId ?? null,
    versionId: definition.versionId ?? null,
    taskId: null,
    updatedAt: definition.updatedAt ?? 0,
  }
}

function json(value) {
  if (typeof value !== 'string' || value.trim() === '') return null
  try {
    return JSON.parse(value)
  } catch {
    return null
  }
}

function textFromResult(event) {
  const blocks = event?.data?.message?.content?.[0]?.content
  if (!Array.isArray(blocks)) return ''
  return blocks
    .filter(block => block?.type === 'text' && typeof block.text === 'string')
    .map(block => block.text)
    .join('\n')
}

function textFromMessage(event) {
  const blocks = event?.data?.content
  if (!Array.isArray(blocks)) return ''
  return blocks
    .filter(block => block?.type === 'text' && typeof block.text === 'string')
    .map(block => block.text)
    .join('\n')
}

function autoDiscoveryPayload(event) {
  if (event?.data?.source?.kind !== 'plugin'
    || event.data.source.plugin !== 'agent-registry:auto-discovery') return null
  const text = textFromMessage(event)
  const match = text.match(/<agent-registry-discovery>\s*([\s\S]*?)\s*(?:\n[^\n]*)*<\/agent-registry-discovery>/u)
  if (match === null) return null
  const firstLine = match[1]?.split('\n')[0] ?? ''
  return json(firstLine)
}

function stringValue(value) {
  return typeof value === 'string' && value !== '' ? value : null
}

function readRecord(value) {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) return null
  const recordId = stringValue(value.recordId) ?? stringValue(value.RecordId)
  const recordName = stringValue(value.recordName)
    ?? stringValue(value.RecordName)
    ?? stringValue(value.name)
    ?? stringValue(value.Name)
  if (recordId === null || recordName === null) return null
  const versionId = stringValue(value.versionId)
    ?? stringValue(value.VersionId)
    ?? stringValue(value.resolvedVersionId)
    ?? stringValue(value.ResolvedVersionId)
  const descriptorType = stringValue(value.descriptorType) ?? stringValue(value.DescriptorType)
  const description = stringValue(value.description) ?? stringValue(value.Description)
  return { recordId, recordName, versionId, descriptorType, description }
}

function collectRecords(value, output = [], seen = new Set()) {
  if (value === null || typeof value !== 'object' || seen.has(value)) return output
  seen.add(value)
  const record = readRecord(value)
  if (record !== null && !output.some(item => item.recordId === record.recordId)) output.push(record)
  for (const child of Array.isArray(value) ? value : Object.values(value)) {
    collectRecords(child, output, seen)
  }
  return output
}

function isA2ARecord(record, existing) {
  const descriptorType = record.descriptorType ?? existing?.descriptorType ?? null
  if (descriptorType !== null) return descriptorType.toUpperCase() === 'A2A'
  if (existing?.nodeId !== undefined) return existing.nodeId !== null
  return /agent/u.test(record.recordName)
}

function stateStatus(state, isError) {
  if (isError) return 'error'
  const normalized = String(state ?? '').toUpperCase()
  if (normalized.includes('FAILED') || normalized.includes('REJECTED') || normalized.includes('CANCEL')) return 'error'
  if (normalized.includes('COMPLETED') || normalized.includes('SUCCEEDED')) return 'completed'
  if (normalized.includes('WORKING') || normalized.includes('SUBMITTED') || normalized.includes('PENDING')) return 'working'
  return 'working'
}

function toolKind(name, args) {
  const normalized = String(name).toLowerCase()
  if (normalized.includes('registry_list') || normalized.includes('search_registry')) return 'registry-search'
  if (normalized.includes('registry_describe') || normalized.includes('describe_record')) return 'registry-describe'
  if (normalized.includes('a2a_send_message')) return 'agent-submit'
  if (normalized.includes('a2a_get_task')) return 'agent-poll'
  if (normalized.includes('a2a_cancel')) return 'agent-cancel'
  if (normalized === 'write' || normalized.includes('write_file') || normalized === 'edit') return 'local-write'
  if (normalized === 'bash' || normalized.includes('exec')) {
    const command = String(args?.command ?? args?.cmd ?? '')
    if (/(?:^|\s)(?:npm|pnpm|yarn|node|go|task)\s+(?:run\s+)?(?:test|check)|node\s+--test|pytest|playwright|vitest/iu.test(command)) return 'local-test'
    if (/(?:serve|http\.server|vite|preview|deploy|publish)/iu.test(command)) return 'local-release'
    return 'local-command'
  }
  if (normalized.includes('browser') || normalized.includes('chrome') || normalized.includes('playwright')) return 'local-test'
  return 'other'
}

function isFailure(event) {
  return event?.data?.message?.content?.[0]?.isError === true || event?.data?.error !== undefined
}

export class CollaborationProjector {
  constructor() {
    this.reset()
  }

  reset() {
    this.nodes = new Map(CORE_NODE_DEFINITIONS.map(definition => [definition.id, blankNode(definition)]))
    this.agentOrder = []
    this.invocationOrder = []
    this.invocations = new Map()
    this.calls = new Map()
    this.records = new Map()
    this.tasks = new Map()
    this.events = []
    this.a2aTasks = 0
    this.activeTurn = null
    this.revision = 0
    this.lastSeq = 0
    this.snapshot = this.buildSnapshot()
  }

  replace(entries) {
    this.reset()
    for (const entry of entries) this.accept(entry.event)
    this.publish()
    return this.snapshot
  }

  append(entries) {
    let changed = false
    for (const entry of entries) changed = this.accept(entry.event) || changed
    if (changed) this.publish()
    return changed
  }

  ensureAgent(record, time) {
    const previousRecord = this.records.get(record.recordId)
    const merged = {
      ...previousRecord,
      ...Object.fromEntries(Object.entries(record).filter(([, value]) => value !== null)),
    }
    if (!isA2ARecord(record, previousRecord)) {
      this.records.set(record.recordId, { ...merged, nodeId: null })
      return { nodeId: null, created: false }
    }
    const nodeId = previousRecord?.nodeId ?? `agent:${record.recordId}`
    this.records.set(record.recordId, { ...merged, nodeId })
    const previousNode = this.nodes.get(nodeId)
    if (previousNode === undefined) {
      this.agentOrder.push(nodeId)
      this.nodes.set(nodeId, blankNode({
        id: nodeId,
        group: 'agent',
        label: merged.recordName,
        description: merged.description,
        descriptorType: merged.descriptorType ?? 'A2A',
        recordId: record.recordId,
        versionId: merged.versionId ?? null,
        status: 'discovered',
        updatedAt: time,
      }))
      return { nodeId, created: true }
    }
    this.updateNode(nodeId, {
      label: merged.recordName,
      description: merged.description ?? previousNode.description,
      descriptorType: merged.descriptorType ?? previousNode.descriptorType,
      versionId: merged.versionId ?? previousNode.versionId,
      updatedAt: time,
    })
    return { nodeId, created: false }
  }

  ensureInvokedAgent(recordId, time) {
    if (recordId === null) return null
    const existing = this.records.get(recordId)
    if (existing?.nodeId !== undefined && existing.nodeId !== null) return existing.nodeId
    return this.ensureAgent({
      recordId,
      recordName: existing?.recordName ?? recordId,
      versionId: existing?.versionId ?? null,
      descriptorType: 'A2A',
      description: existing?.description ?? null,
    }, time).nodeId
  }

  accept(event) {
    if (event === undefined || event === null) return false
    this.lastSeq = Math.max(this.lastSeq, Number(event.seq) || 0)
    if (event.type === 'turn/start') {
      this.activeTurn = event.data?.turn ?? null
      this.updateNode('coordinator', { status: 'working', updatedAt: event.time })
      this.addEvent(event, 'turn-start', 'coordinator')
      return true
    }
    if (event.type === 'turn/end') {
      this.activeTurn = null
      const failed = String(event.data?.reason ?? '').toLowerCase().includes('error')
      this.updateNode('coordinator', { status: failed ? 'error' : 'completed', updatedAt: event.time })
      this.addEvent(event, failed ? 'turn-failed' : 'turn-end', 'coordinator')
      return true
    }
    if (event.type === 'user/message') return this.acceptAutoDiscovery(event)
    if (event.type === 'tool/call') return this.acceptCall(event)
    if (event.type === 'tool/result') return this.acceptResult(event)
    return false
  }

  acceptAutoDiscovery(event) {
    const payload = autoDiscoveryPayload(event)
    if (payload?.kind !== 'agent-registry-auto-discovery') return false
    const failed = payload.error !== undefined
    const records = collectRecords(payload.candidates)
    let discoveredNow = 0
    let matchedAgents = 0
    for (const record of records) {
      const ensured = this.ensureAgent(record, event.time)
      if (ensured.nodeId !== null) matchedAgents += 1
      if (ensured.created) {
        discoveredNow += 1
        this.addEvent(event, 'agent-discovered', ensured.nodeId, { recordId: record.recordId })
      }
    }
    this.bumpNode('registry', {
      status: 'working',
      latest: { action: 'registry-search' },
      updatedAt: event.time,
    })
    this.updateNode('registry', {
      status: failed ? 'error' : 'completed',
      latest: { action: failed ? 'registry-error' : 'registry-discovered', count: matchedAgents },
      failedDelta: failed ? 1 : 0,
      completedDelta: failed ? 0 : 1,
      updatedAt: event.time,
    })
    this.addEvent(event, failed ? 'registry-error' : 'registry-discovered', 'registry', {
      count: matchedAgents,
      automatic: true,
    })
    return true
  }

  acceptCall(event) {
    const data = event.data ?? {}
    const args = json(data.arguments) ?? {}
    const kind = toolKind(data.name, args)
    if (kind === 'other') return false
    const recordId = stringValue(args.record_id) ?? stringValue(args.recordId)
    const taskId = stringValue(args.task_id) ?? stringValue(args.taskId)
    let nodeId = recordId === null ? null : this.records.get(recordId)?.nodeId ?? null
    if (nodeId === null && taskId !== null) nodeId = this.tasks.get(taskId)?.nodeId ?? null
    if (nodeId === null && kind.startsWith('agent-')) nodeId = this.ensureInvokedAgent(recordId, event.time)
    const callId = String(data.callId)
    this.calls.set(callId, { kind, nodeId, args, name: data.name, time: event.time, seq: event.seq })

    if (kind.startsWith('registry-')) {
      this.bumpNode('registry', { status: 'working', latest: { action: kind }, updatedAt: event.time })
      this.addEvent(event, kind, 'registry')
      return true
    }
    if (kind.startsWith('agent-')) {
      const bridgeAction = `bridge-${kind.slice('agent-'.length)}`
      this.bumpNode('bridge', { status: 'working', latest: { action: bridgeAction }, updatedAt: event.time })
      if (nodeId !== null) {
        this.bumpNode(nodeId, {
          status: 'working',
          latest: { action: kind },
          recordId,
          versionId: stringValue(args.version_id) ?? stringValue(args.versionId),
          taskId,
          updatedAt: event.time,
        })
        this.addEvent(event, kind, nodeId, { taskId, recordId })
      }
      return true
    }
    this.bumpNode('workspace', { status: 'working', latest: { action: kind }, updatedAt: event.time })
    this.addEvent(event, kind, 'workspace')
    return true
  }

  acceptResult(event) {
    const callId = String(event.data?.message?.source?.callId ?? '')
    const call = this.calls.get(callId)
    if (call === undefined) return false
    const failed = isFailure(event)
    const payload = json(textFromResult(event))

    if (call.kind.startsWith('registry-')) {
      const records = collectRecords(payload)
      let discoveredNow = 0
      let matchedAgents = 0
      for (const record of records) {
        const ensured = this.ensureAgent(record, event.time)
        if (ensured.nodeId !== null) matchedAgents += 1
        if (ensured.created) {
          discoveredNow += 1
          this.addEvent(event, 'agent-discovered', ensured.nodeId, { recordId: record.recordId })
        }
      }
      this.updateNode('registry', {
        status: failed ? 'error' : 'completed',
        latest: { action: failed ? 'registry-error' : 'registry-discovered', count: matchedAgents },
        failedDelta: failed ? 1 : 0,
        completedDelta: failed ? 0 : 1,
        updatedAt: event.time,
      })
      this.addEvent(event, failed ? 'registry-error' : 'registry-discovered', 'registry', { count: matchedAgents })
      return true
    }

    if (call.kind.startsWith('agent-')) {
      const target = payload?.target ?? payload?.Target ?? {}
      const recordId = stringValue(target.recordId) ?? stringValue(target.RecordId)
        ?? stringValue(call.args.record_id) ?? stringValue(call.args.recordId)
      const known = recordId === null ? null : this.records.get(recordId)
      const recordName = stringValue(target.recordName) ?? stringValue(target.RecordName) ?? known?.recordName ?? null
      const versionId = stringValue(target.versionId) ?? stringValue(target.VersionId)
        ?? stringValue(call.args.version_id) ?? stringValue(call.args.versionId) ?? known?.versionId ?? null
      const taskId = stringValue(payload?.taskId) ?? stringValue(payload?.TaskId)
        ?? stringValue(call.args.task_id) ?? stringValue(call.args.taskId)
      let nodeId = call.nodeId
      if (recordId !== null && recordName !== null) {
        nodeId = this.ensureAgent({
          recordId,
          recordName,
          versionId,
          descriptorType: 'A2A',
          description: known?.description ?? null,
        }, event.time).nodeId
      }
      if (nodeId === null) {
        this.updateNode('bridge', {
          status: failed ? 'error' : 'completed',
          latest: { action: failed ? 'agent-failed' : call.kind },
          failedDelta: failed ? 1 : 0,
          completedDelta: failed ? 0 : 1,
          updatedAt: event.time,
        })
        return true
      }
      if (taskId !== null) this.tasks.set(taskId, { nodeId, recordId, versionId, state: payload?.state })
      const status = stateStatus(payload?.state, failed)
      if (taskId !== null) {
        if (!this.invocations.has(taskId)) this.invocationOrder.push(taskId)
        const previousInvocation = this.invocations.get(taskId)
        this.invocations.set(taskId, {
          taskId,
          nodeId,
          recordId,
          versionId,
          state: stringValue(payload?.state),
          status,
          outcome: stringValue(payload?.handoff?.outcome) ?? previousInvocation?.outcome ?? null,
          updatedAt: event.time,
        })
      }
      let action = call.kind
      if (status === 'completed') action = 'agent-completed'
      else if (status === 'error') action = 'agent-failed'
      else if (String(payload?.state ?? '').toUpperCase().includes('WORKING')) action = 'agent-working'
      const previous = this.nodes.get(nodeId)
      const stateChanged = previous?.status !== status || previous?.taskId !== taskId
      this.updateNode(nodeId, {
        status,
        recordId,
        versionId,
        taskId,
        latest: { action },
        completedDelta: status === 'completed' && previous?.status !== 'completed' ? 1 : 0,
        failedDelta: status === 'error' && previous?.status !== 'error' ? 1 : 0,
        updatedAt: event.time,
      })
      this.updateNode('bridge', {
        status: failed ? 'error' : 'completed',
        latest: { action: failed ? 'bridge-failed' : 'bridge-completed' },
        failedDelta: failed ? 1 : 0,
        completedDelta: failed ? 0 : 1,
        updatedAt: event.time,
      })
      if (call.kind === 'agent-submit' && taskId !== null) this.a2aTasks += 1
      if (call.kind === 'agent-submit' || stateChanged || status === 'error' || status === 'completed') {
        this.addEvent(event, action, nodeId, { taskId, recordId, state: payload?.state })
      }
      return true
    }

    const status = failed ? 'error' : 'completed'
    this.updateNode('workspace', {
      status,
      latest: { action: failed ? 'local-failed' : `${call.kind}-completed` },
      completedDelta: failed ? 0 : 1,
      failedDelta: failed ? 1 : 0,
      updatedAt: event.time,
    })
    this.addEvent(event, failed ? 'local-failed' : `${call.kind}-completed`, 'workspace')
    return true
  }

  bumpNode(id, patch) {
    const previous = this.nodes.get(id)
    if (previous === undefined) return
    this.nodes.set(id, { ...previous, ...patch, calls: previous.calls + 1 })
  }

  updateNode(id, patch) {
    const previous = this.nodes.get(id)
    if (previous === undefined) return
    const completedDelta = patch.completedDelta ?? 0
    const failedDelta = patch.failedDelta ?? 0
    const clean = { ...patch }
    delete clean.completedDelta
    delete clean.failedDelta
    this.nodes.set(id, {
      ...previous,
      ...clean,
      completed: previous.completed + completedDelta,
      failed: previous.failed + failedDelta,
    })
  }

  addEvent(event, action, nodeId, detail = {}) {
    this.events.push({
      id: `${event.seq}:${action}:${nodeId}`,
      seq: event.seq,
      time: event.time,
      action,
      nodeId,
      ...detail,
    })
    if (this.events.length > 160) this.events.splice(0, this.events.length - 160)
    const node = this.nodes.get(nodeId)
    if (node !== undefined) this.nodes.set(nodeId, { ...node, latest: { action, ...detail }, updatedAt: event.time })
  }

  publish() {
    this.revision += 1
    this.snapshot = this.buildSnapshot()
  }

  buildSnapshot() {
    const coreNodes = CORE_NODE_DEFINITIONS.map(definition => this.nodes.get(definition.id) ?? blankNode(definition))
    const agentNodes = this.agentOrder.map(id => this.nodes.get(id)).filter(Boolean)
    const invocations = this.invocationOrder.map(taskId => {
      const invocation = this.invocations.get(taskId)
      if (invocation === undefined) return null
      return { ...invocation, node: this.nodes.get(invocation.nodeId) ?? null }
    }).filter(Boolean)
    return {
      revision: this.revision,
      lastSeq: this.lastSeq,
      activeTurn: this.activeTurn,
      nodes: [...coreNodes, ...agentNodes],
      coreNodes,
      agentNodes,
      invocations,
      events: [...this.events].reverse(),
      metrics: {
        discovered: agentNodes.length,
        a2aTasks: this.a2aTasks,
        completed: agentNodes.filter(node => node.status === 'completed').length,
        failed: agentNodes.filter(node => node.status === 'error').length,
      },
    }
  }
}

export function projectEntries(entries) {
  return new CollaborationProjector().replace(entries)
}
