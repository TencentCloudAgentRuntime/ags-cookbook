import assert from 'node:assert/strict'
import test from 'node:test'
import { collaborationSource } from '../src/source.js'

const entry = event => ({ type: 'event', event })
const event = (seq, type, data) => ({ seq, type, data, time: seq * 1000 })
const call = (seq, callId, recordId) => entry(event(seq, 'tool/call', {
  turn: 1,
  step: seq,
  callId,
  name: 'mcp__a2a__a2a_send_message',
  arguments: JSON.stringify({ record_id: recordId, version_id: `rv-${recordId}` }),
}))
const result = (seq, callId, recordId, taskId) => entry(event(seq, 'tool/result', {
  turn: 1,
  step: seq,
  message: {
    source: { kind: 'tool', callId },
    content: [{
      type: 'tool-result',
      toolCallId: callId,
      isError: false,
      content: [{ type: 'text', text: JSON.stringify({
        target: { recordId, recordName: `${recordId}-agent`, versionId: `rv-${recordId}` },
        taskId,
        state: 'TASK_STATE_COMPLETED',
      }) }],
    }],
  },
}))

test('re-subscribing catches up every event received while the tab was unmounted', () => {
  const developer = [
    call(1, 'developer-send', 'developer'),
    result(2, 'developer-send', 'developer', 'task-developer'),
  ]
  const reviewer = [
    call(3, 'reviewer-send', 'reviewer'),
    result(4, 'reviewer-send', 'reviewer', 'task-reviewer'),
  ]
  let snapshot = {
    revision: 1,
    entries: developer,
    change: { kind: 'replace', entries: developer },
    hasMore: false,
  }
  const eventListeners = new Set()
  const binding = {
    eventSource: {
      getSnapshot: () => snapshot,
      subscribe(listener) {
        eventListeners.add(listener)
        return () => eventListeners.delete(listener)
      },
    },
    session: {
      getSnapshot: () => ({ openState: 'open' }),
      subscribe: () => () => {},
      async loadOlder() {},
    },
  }

  const source = collaborationSource(binding)
  const dispose = source.subscribe(() => {})
  assert.deepEqual(source.getSnapshot().agentNodes.map(node => node.recordId), ['developer'])
  dispose()

  snapshot = {
    revision: 3,
    entries: [...developer, ...reviewer],
    // Only the latest delta is exposed after multiple missed revisions.
    change: { kind: 'append', entries: [reviewer[1]] },
    hasMore: false,
  }

  const disposeAgain = source.subscribe(() => {})
  assert.deepEqual(
    source.getSnapshot().agentNodes.map(node => node.recordId),
    ['developer', 'reviewer'],
  )
  assert.equal(source.getSnapshot().invocations.length, 2)
  disposeAgain()
})
