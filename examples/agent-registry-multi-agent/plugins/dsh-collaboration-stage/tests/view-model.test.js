import assert from 'node:assert/strict'
import test from 'node:test'
import { participationView } from '../src/view-model.js'

test('shows only agents that own a real A2A Task', () => {
  const invoked = { id: 'agent:called', label: 'called' }
  const candidate = { id: 'agent:candidate', label: 'candidate' }
  const result = participationView({
    agentNodes: [candidate, invoked],
    invocations: [{ taskId: 'task-1', node: invoked }],
    events: [
      { id: 'registry', action: 'registry-discovered', nodeId: 'registry', count: 15 },
      { id: 'candidate', action: 'agent-discovered', nodeId: candidate.id },
      { id: 'called', action: 'agent-discovered', nodeId: invoked.id },
      { id: 'task', action: 'agent-submit', nodeId: invoked.id },
    ],
  })

  assert.deepEqual(result.agentNodes, [invoked])
  assert.deepEqual(result.events.map(event => event.id), ['registry', 'called', 'task'])
})
