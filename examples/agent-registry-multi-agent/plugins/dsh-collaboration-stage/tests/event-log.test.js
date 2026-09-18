import assert from 'node:assert/strict'
import test from 'node:test'
import { createProjectionEventLog } from '../src/event-log.js'
import { projectEntries } from '../src/projection.js'

const entry = event => ({ type: 'event', event })
const event = (seq, type, data) => ({ seq, type, data, time: seq * 1000 })
const call = (seq, callId, name, args) => entry(event(seq, 'tool/call', {
  turn: 1,
  step: seq,
  callId,
  name,
  arguments: JSON.stringify(args),
}))
const result = (seq, callId, value) => entry(event(seq, 'tool/result', {
  turn: 1,
  step: seq,
  message: {
    source: { kind: 'tool', callId },
    content: [{
      type: 'tool-result',
      toolCallId: callId,
      isError: false,
      content: [{ type: 'text', text: JSON.stringify(value) }],
    }],
  },
}))

test('retains an earlier A2A call when the live event window is replaced', () => {
  const log = createProjectionEventLog([
    call(1, 'send', 'mcp__a2a__a2a_send_message', {
      record_id: 'rec-developer',
      version_id: 'rv-developer',
    }),
    result(2, 'send', {
      target: {
        recordId: 'rec-developer',
        recordName: 'workbench-developer-agent',
        versionId: 'rv-developer',
      },
      taskId: 'task-developer',
      state: 'TASK_STATE_WORKING',
    }),
  ])

  assert.equal(log.merge([
    call(3, 'poll', 'mcp__a2a__a2a_get_task', {
      record_id: 'rec-developer',
      version_id: 'rv-developer',
      task_id: 'task-developer',
    }),
    result(4, 'poll', {
      target: {
        recordId: 'rec-developer',
        recordName: 'workbench-developer-agent',
        versionId: 'rv-developer',
      },
      taskId: 'task-developer',
      state: 'TASK_STATE_FAILED',
      failure: 'fetch failed',
    }),
  ]), true)

  const snapshot = projectEntries(log.entries())
  assert.equal(snapshot.agentNodes[0].status, 'error')
  assert.equal(snapshot.invocations[0].status, 'error')
  assert.equal(snapshot.metrics.failed, 1)
})

test('ignores high-volume chunks that cannot affect collaboration state', () => {
  const log = createProjectionEventLog([
    entry(event(1, 'assistant/chunk', { chunk: { type: 'text-delta' } })),
    entry(event(2, 'tool-call-chunks', { index: 0 })),
    entry(event(3, 'turn/start', { turn: 1 })),
  ])

  assert.deepEqual(log.entries().map(item => item.event.seq), [3])
})
