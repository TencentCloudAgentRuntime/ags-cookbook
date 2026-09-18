import assert from 'node:assert/strict'
import test from 'node:test'
import { CollaborationProjector, projectEntries } from '../src/projection.js'

const entry = event => ({ type: 'event', event })
const event = (seq, type, data, time = seq * 1000) => ({ seq, type, data, time })
const call = (seq, callId, name, args) => event(seq, 'tool/call', {
  turn: 1, step: seq, callId, name, arguments: JSON.stringify(args),
})
const result = (seq, callId, value, isError = false) => event(seq, 'tool/result', {
  turn: 1,
  step: seq,
  message: {
    source: { kind: 'tool', callId },
    content: [{ type: 'tool-result', toolCallId: callId, isError, content: [{ type: 'text', text: JSON.stringify(value) }] }],
  },
})
const autoDiscovery = (seq, value) => event(seq, 'user/message', {
  content: [{
    type: 'text',
    text: `<agent-registry-discovery>\n${JSON.stringify(value)}\nUse relevant candidates.\n</agent-registry-discovery>`,
  }],
  source: { kind: 'plugin', plugin: 'agent-registry:auto-discovery' },
})

test('projects automatic first-step discovery from Registry plugin context', () => {
  const snapshot = projectEntries([
    entry(event(1, 'turn/start', { turn: 1 })),
    entry(autoDiscovery(2, {
      kind: 'agent-registry-auto-discovery',
      candidates: [
        { registryId: 'reg-demo', recordId: 'rec-analysis', name: 'custom/analysis-agent', descriptorType: 'A2A' },
        { registryId: 'reg-demo', recordId: 'rec-skill', name: 'custom/build-skill', descriptorType: 'AGENT_SKILLS' },
      ],
    })),
  ])

  assert.equal(snapshot.metrics.discovered, 1)
  assert.equal(snapshot.agentNodes[0].label, 'custom/analysis-agent')
  assert.equal(snapshot.agentNodes[0].status, 'discovered')
  const registry = snapshot.coreNodes.find(node => node.id === 'registry')
  assert.equal(registry.calls, 1)
  assert.equal(registry.status, 'completed')
  assert(snapshot.events.some(item => item.action === 'registry-discovered' && item.automatic === true))
})

test('projects automatic discovery failure without inventing agent nodes', () => {
  const snapshot = projectEntries([
    entry(autoDiscovery(1, {
      kind: 'agent-registry-auto-discovery',
      candidates: [],
      error: { code: 'InternalError', requestId: 'request-1', message: 'failed' },
    })),
  ])

  assert.equal(snapshot.metrics.discovered, 0)
  const registry = snapshot.coreNodes.find(node => node.id === 'registry')
  assert.equal(registry.status, 'error')
  assert.equal(registry.failed, 1)
})

test('creates agent nodes from arbitrary A2A Records and excludes non-agent assets', () => {
  const snapshot = projectEntries([
    entry(call(1, 'registry', 'registry_list_records', { search: 'security and delivery' })),
    entry(result(2, 'registry', { records: [
      { RecordId: 'rec-security', Name: 'team-x/security-sentinel', Description: 'Finds risky changes.', DescriptorType: 'A2A' },
      { RecordId: 'rec-release', Name: 'custom-release-captain', Description: 'Ships approved builds.', DescriptorType: 'A2A' },
      { RecordId: 'rec-client', Name: 'demo.local/a2a-client', DescriptorType: 'MCP' },
    ] })),
  ])

  assert.equal(snapshot.metrics.discovered, 2)
  assert.deepEqual(snapshot.agentNodes.map(node => node.label), [
    'team-x/security-sentinel',
    'custom-release-captain',
  ])
  assert.equal(snapshot.agentNodes[0].description, 'Finds risky changes.')
  assert.equal(snapshot.agentNodes[0].status, 'discovered')
  assert(!snapshot.nodes.some(node => node.recordId === 'rec-client'))
})

test('projects an arbitrary discovered agent through the A2A lifecycle', () => {
  const entries = [
    entry(event(1, 'turn/start', { turn: 1 })),
    entry(call(2, 'registry', 'registry_list_records', {})),
    entry(result(3, 'registry', { Records: [
      { RecordId: 'rec-ux', Name: 'my-team/playability-agent', DescriptorType: 'A2A', ResolvedVersionId: 'rv-ux' },
    ] })),
    entry(call(4, 'send', 'mcp__a2a__a2a_send_message', { record_id: 'rec-ux', version_id: 'rv-ux', message: 'review the game' })),
    entry(result(5, 'send', { target: { recordId: 'rec-ux', recordName: 'my-team/playability-agent', versionId: 'rv-ux' }, taskId: 'task-1', state: 'TASK_STATE_SUBMITTED' })),
    entry(call(6, 'poll', 'mcp__a2a__a2a_get_task', { record_id: 'rec-ux', version_id: 'rv-ux', task_id: 'task-1' })),
    entry(result(7, 'poll', { target: { recordId: 'rec-ux', recordName: 'my-team/playability-agent', versionId: 'rv-ux' }, taskId: 'task-1', state: 'TASK_STATE_COMPLETED' })),
    entry(event(8, 'turn/end', { turn: 1, reason: 'completed' })),
  ]
  const snapshot = projectEntries(entries)
  const agent = snapshot.agentNodes[0]
  const bridge = snapshot.coreNodes.find(node => node.id === 'bridge')

  assert.equal(snapshot.metrics.discovered, 1)
  assert.equal(snapshot.metrics.a2aTasks, 1)
  assert.equal(snapshot.metrics.completed, 1)
  assert.equal(snapshot.invocations.length, 1)
  assert.equal(snapshot.invocations[0].taskId, 'task-1')
  assert.equal(snapshot.invocations[0].node.id, agent.id)
  assert.equal(agent.status, 'completed')
  assert.equal(agent.recordId, 'rec-ux')
  assert.equal(agent.versionId, 'rv-ux')
  assert.equal(agent.taskId, 'task-1')
  assert.equal(bridge.status, 'completed')
  assert(snapshot.events.some(item => item.action === 'agent-completed' && item.nodeId === agent.id))
})

test('preserves actual task order and repeated review outcomes in the invocation chain', () => {
  const target = (recordId, recordName) => ({ recordId, recordName, versionId: `rv-${recordId}` })
  const snapshot = projectEntries([
    entry(call(1, 'dev-send', 'mcp__a2a__a2a_send_message', { record_id: 'developer', version_id: 'rv-developer' })),
    entry(result(2, 'dev-send', { target: target('developer', 'Developer Agent'), taskId: 'task-dev', state: 'TASK_STATE_COMPLETED', handoff: { outcome: 'READY' } })),
    entry(call(3, 'review-send-1', 'mcp__a2a__a2a_send_message', { record_id: 'reviewer', version_id: 'rv-reviewer' })),
    entry(result(4, 'review-send-1', { target: target('reviewer', 'Reviewer Agent'), taskId: 'task-review-1', state: 'TASK_STATE_COMPLETED', handoff: { outcome: 'BLOCKED' } })),
    entry(call(5, 'review-send-2', 'mcp__a2a__a2a_send_message', { record_id: 'reviewer', version_id: 'rv-reviewer' })),
    entry(result(6, 'review-send-2', { target: target('reviewer', 'Reviewer Agent'), taskId: 'task-review-2', state: 'TASK_STATE_COMPLETED', handoff: { outcome: 'PASSED' } })),
  ])

  assert.equal(snapshot.metrics.a2aTasks, 3)
  assert.deepEqual(snapshot.invocations.map(item => item.taskId), ['task-dev', 'task-review-1', 'task-review-2'])
  assert.deepEqual(snapshot.invocations.map(item => item.outcome), ['READY', 'BLOCKED', 'PASSED'])
  assert.equal(snapshot.invocations[1].node.id, snapshot.invocations[2].node.id)
})

test('creates a fallback node when an invoked Record was not present in discovery results', () => {
  const snapshot = projectEntries([
    entry(call(1, 'send', 'mcp__a2a__a2a_send_message', { record_id: 'rec-private', version_id: 'rv-private' })),
    entry(result(2, 'send', {
      target: { recordId: 'rec-private', recordName: 'private/team-agent', versionId: 'rv-private' },
      taskId: 'task-private',
      state: 'TASK_STATE_WORKING',
    })),
  ])

  assert.equal(snapshot.agentNodes.length, 1)
  assert.equal(snapshot.agentNodes[0].label, 'private/team-agent')
  assert.equal(snapshot.agentNodes[0].status, 'working')
})

test('applies live append without rebuilding previous counters', () => {
  const projector = new CollaborationProjector()
  projector.replace([entry(event(1, 'turn/start', { turn: 1 }))])
  assert.equal(projector.append([entry(call(2, 'test', 'bash', { command: 'npm test' }))]), true)
  assert.equal(projector.append([entry(result(3, 'test', { output: 'ok' }))]), true)
  const workspace = projector.snapshot.coreNodes.find(node => node.id === 'workspace')
  assert.equal(workspace.calls, 1)
  assert.equal(workspace.status, 'completed')
  assert.equal(projector.snapshot.events.filter(item => item.action === 'turn-start').length, 1)
})
