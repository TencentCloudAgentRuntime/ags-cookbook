import assert from 'node:assert/strict'
import test from 'node:test'
import {
  MAX_EVENT_BYTES,
  entryToEvent,
  isTruncatedEvent,
  eventIdFor,
  eventToEntry,
  headerToState,
  seqOfEvent,
  stateToHeader,
} from './session-codec.js'

const usage = { input: 10, output: 5, cacheRead: 0, cacheWrite: 0, totalTokens: 15, cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } }
const base = (type, id, parentId, extra) => ({ type, id, parentId, timestamp: '2026-10-27T00:00:00.000Z', ...extra })

const entries = {
  userString: base('message', 'a1', null, { message: { role: 'user', content: 'hello', timestamp: 1 } }),
  userBlocks: base('message', 'a2', 'a1', {
    message: {
      role: 'user',
      content: [{ type: 'text', text: 'look' }, { type: 'image', data: 'aGVsbG8=', mimeType: 'image/png' }],
      timestamp: 2,
    },
  }),
  assistant: base('message', 'a3', 'a2', {
    message: {
      role: 'assistant',
      content: [
        { type: 'thinking', thinking: 'hmm', thinkingSignature: 'sig-1' },
        { type: 'thinking', thinking: '', thinkingSignature: 'opaque', redacted: true },
        { type: 'text', text: 'Reading.', textSignature: 'sig-2' },
        { type: 'toolCall', id: 'call_1', name: 'read', arguments: { path: 'a.txt' }, thoughtSignature: 'sig-3' },
      ],
      api: 'openai-completions', provider: 'custom', model: 'm', usage, stopReason: 'toolUse', timestamp: 3,
    },
  }),
  toolResult: base('message', 'a4', 'a3', {
    message: {
      role: 'toolResult', toolCallId: 'call_1', toolName: 'read',
      content: [{ type: 'text', text: 'file body\nline 2' }], details: { truncated: false }, isError: false, timestamp: 4,
    },
  }),
  toolError: base('message', 'a5', 'a4', {
    message: { role: 'toolResult', toolCallId: 'call_2', toolName: 'bash', content: [{ type: 'text', text: 'boom' }], isError: true, timestamp: 5 },
  }),
  assistantError: base('message', 'a6', 'a5', {
    message: { role: 'assistant', content: [], api: 'x', provider: 'p', model: 'm', usage, stopReason: 'error', errorMessage: 'rate limited', timestamp: 6 },
  }),
  system: base('message', 'a7', 'a6', {
    message: { role: 'system', content: '', sections: { preamble: 'You are...' }, toolsAdded: [{ name: 'read', description: 'd', parameters: {} }], timestamp: 7 },
  }),
  compaction: base('compaction', 'b1', 'a7', { summary: 'earlier work', firstKeptEntryId: 'a3', tokensBefore: 1000, details: { readFiles: ['a.txt'] } }),
  branchSummary: base('branch_summary', 'b2', 'a1', { fromId: 'a7', summary: 'abandoned path' }),
  customMessageString: base('custom_message', 'b3', 'b1', { customType: 'ext', content: 'injected', display: true }),
  customMessageBlocks: base('custom_message', 'b4', 'b3', { customType: 'ext', content: [{ type: 'text', text: 'blocks' }], display: false, details: { n: 1 } }),
  custom: base('custom', 'b5', 'b4', { customType: 'ext', data: { count: 42 } }),
  modelChange: base('model_change', 'b6', 'b5', { provider: 'custom', modelId: 'm' }),
  thinkingChange: base('thinking_level_change', 'b7', 'b6', { thinkingLevel: 'high' }),
  label: base('label', 'b8', 'b7', { targetId: 'a1', label: 'checkpoint' }),
  sessionInfo: base('session_info', 'b9', 'b8', { name: 'Refactor' }),
  unknownType: base('future_entry', 'c1', 'b9', { payload: { anything: [1, 2, 3] } }),
  unknownRole: base('message', 'c2', 'c1', { message: { role: 'bashExecution', command: 'ls', output: 'x', exitCode: 0, timestamp: 8 } }),
}

// The service stores events and returns them with strings and parts intact.
function throughService(event) {
  return JSON.parse(JSON.stringify(event))
}

for (const [name, entry] of Object.entries(entries)) {
  test(`round trip: ${name}`, () => {
    const event = throughService(entryToEvent('sess-1', 7, entry))
    assert.deepEqual(eventToEntry(event), entry)
    assert.equal(event.EventId, eventIdFor('sess-1', 7))
    assert.equal(seqOfEvent(event), 7)
  })
}

test('content is stored once: Extensions never repeat text that Parts carry', () => {
  const secret = 'UNIQUE-BODY-TEXT'
  const withBody = [
    base('message', 'x1', null, { message: { role: 'user', content: secret, timestamp: 1 } }),
    base('message', 'x2', 'x1', { message: { role: 'user', content: [{ type: 'text', text: secret }], timestamp: 1 } }),
    base('message', 'x3', 'x2', {
      message: { role: 'assistant', content: [{ type: 'thinking', thinking: secret }, { type: 'toolCall', id: 'c', name: 'bash', arguments: { cmd: secret } }], api: 'a', provider: 'p', model: 'm', usage, stopReason: 'toolUse', timestamp: 1 },
    }),
    base('message', 'x4', 'x3', { message: { role: 'toolResult', toolCallId: 'c', toolName: 'bash', content: [{ type: 'text', text: secret }], isError: false, timestamp: 1 } }),
    base('compaction', 'x5', 'x4', { summary: secret, firstKeptEntryId: 'x1', tokensBefore: 1 }),
    base('custom_message', 'x6', 'x5', { customType: 'e', content: secret, display: true }),
  ]
  for (const entry of withBody) {
    const event = entryToEvent('s', 0, entry)
    assert.ok(!event.Extensions.includes(secret), `${entry.id} repeats its body in Extensions`)
    assert.ok(JSON.stringify(event.Content).includes(secret), `${entry.id} lost its body from Parts`)
  }
})

test('image data is stored once, in InlineData', () => {
  const event = entryToEvent('s', 0, entries.userBlocks)
  assert.deepEqual(event.Content.Parts, [{ Text: 'look' }, { InlineData: { MimeType: 'image/png', Data: 'aGVsbG8=' } }])
  assert.ok(!event.Extensions.includes('aGVsbG8='))
})

test('a session saved with images inside Extensions still restores', () => {
  const event = throughService(entryToEvent('s', 0, entries.userBlocks))
  const stored = JSON.parse(event.Extensions)
  stored.pi.entry.message.content[1].data = 'aGVsbG8='
  event.Extensions = JSON.stringify(stored)
  event.Content.Parts[1] = { Text: '[image: image/png]' }
  assert.deepEqual(eventToEntry(event), entries.userBlocks)
})

test('restore fails clearly when the service does not return InlineData', () => {
  const event = throughService(entryToEvent('s', 0, entries.userBlocks))
  event.Content.Parts[1] = {}
  assert.throws(() => eventToEntry(event), /does not return InlineData/)
})

test('entries without conversational content have no Content', () => {
  for (const name of ['system', 'custom', 'modelChange', 'unknownType', 'unknownRole']) {
    assert.equal(entryToEvent('s', 0, entries[name]).Content, undefined, name)
  }
})

test('projection fields: authors, roles, parts and errors', () => {
  const assistant = entryToEvent('s', 1, entries.assistant)
  assert.equal(assistant.Author, 'assistant')
  assert.deepEqual(assistant.Content.Parts.map(part => Object.keys(part)[0]), ['Text', 'Text', 'Text', 'FunctionCall'])
  assert.equal(assistant.Content.Parts[0].Thought, true)
  assert.equal(JSON.parse(assistant.Metadata).TurnComplete, false)
  assert.deepEqual(JSON.parse(assistant.Content.Parts[3].FunctionCall), { Name: 'read', Args: { path: 'a.txt' } })

  const result = entryToEvent('s', 2, entries.toolResult)
  assert.equal(result.Author, 'tool')
  assert.equal(result.Content.Role, 'tool')
  assert.equal(result.ErrorCode, undefined)

  const toolError = entryToEvent('s', 3, entries.toolError)
  assert.equal(toolError.ErrorCode, 'TOOL_ERROR')
  assert.equal(toolError.ErrorMessage, 'boom')

  const modelError = entryToEvent('s', 4, entries.assistantError)
  assert.equal(modelError.ErrorCode, 'MODEL_ERROR')
  assert.equal(modelError.ErrorMessage, 'rate limited')
})

test('a Part the service returns without Text restores as an empty string', () => {
  const entry = base('message', 'e1', null, { message: { role: 'user', content: [{ type: 'text', text: '' }], timestamp: 1 } })
  const event = throughService(entryToEvent('s', 0, entry))
  event.Content.Parts = [{}]
  assert.deepEqual(eventToEntry(event), entry)
})

test('restore rejects corrupt events', () => {
  const event = throughService(entryToEvent('s', 0, entries.assistant))
  assert.throws(() => eventToEntry({ ...event, Content: { Role: 'assistant', Parts: event.Content.Parts.slice(1) } }), /parts for 4 content blocks/)
  assert.throws(() => eventToEntry({ EventId: 'e', Extensions: '{}' }), /no pi extension data/)
  assert.throws(() => eventToEntry({ EventId: 'e', Extensions: JSON.stringify({ pi: { v: 99, entry: {} } }) }), /codec version 99/)
})

test('header state round trip and format check', () => {
  const header = { type: 'session', version: 3, id: 's', timestamp: 't', cwd: '/workspace' }
  assert.deepEqual(stateToHeader(headerToState(header)), header)
  assert.equal(stateToHeader('{}'), undefined)
  assert.equal(stateToHeader(undefined), undefined)
  assert.throws(() => stateToHeader(JSON.stringify({ piHeader: header, piFormat: 2 })), /unsupported pi session format/)
})

const bytes = event => Buffer.byteLength(JSON.stringify(event))

test('an Event over the size limit is cut down to fit and marked truncated', () => {
  const huge = 'y'.repeat(900_000)
  const toolResult = base('message', 'big1', null, {
    message: { role: 'toolResult', toolCallId: 'c', toolName: 'bash', content: [{ type: 'text', text: huge }], isError: false, timestamp: 1 },
  })
  const event = throughService(entryToEvent('s', 0, toolResult))
  assert.ok(bytes(event) <= MAX_EVENT_BYTES)
  assert.equal(isTruncatedEvent(event), true)
  assert.equal(JSON.parse(event.Metadata).piTruncated, true)
  const restored = eventToEntry(event)
  assert.match(restored.message.content[0].text, /\[truncated: original 900000 characters\]$/)
  assert.equal(restored.message.toolCallId, 'c')
  assert.equal(restored.id, 'big1')
})

test('truncation keeps multi-byte text within the byte limit', () => {
  const entry = base('message', 'big2', null, { message: { role: 'user', content: '中'.repeat(300_000), timestamp: 1 } })
  const event = entryToEvent('s', 0, entry)
  assert.ok(bytes(event) <= MAX_EVENT_BYTES)
  assert.equal(eventToEntry(throughService(event)).message.content.endsWith('characters]'), true)
})

test('an oversized image becomes a text note and an oversized tool call loses its arguments', () => {
  const image = base('message', 'big3', null, {
    message: { role: 'user', content: [{ type: 'text', text: 'see' }, { type: 'image', data: 'A'.repeat(500_000), mimeType: 'image/png' }], timestamp: 1 },
  })
  const imageEvent = entryToEvent('s', 0, image)
  assert.ok(bytes(imageEvent) <= MAX_EVENT_BYTES)
  const restoredImage = eventToEntry(throughService(imageEvent))
  assert.deepEqual(restoredImage.message.content[0], { type: 'text', text: 'see' })
  assert.match(restoredImage.message.content[1].text, /^\[image omitted: 500000 characters of image\/png data\]$/)

  const call = base('message', 'big4', null, {
    message: { role: 'assistant', content: [{ type: 'toolCall', id: 'c9', name: 'write', arguments: { content: 'z'.repeat(400_000) } }], api: 'a', provider: 'p', model: 'm', usage, stopReason: 'toolUse', timestamp: 1 },
  })
  const callEvent = entryToEvent('s', 1, call)
  assert.ok(bytes(callEvent) <= MAX_EVENT_BYTES)
  const restoredCall = eventToEntry(throughService(callEvent)).message.content[0]
  assert.equal(restoredCall.id, 'c9')
  assert.equal(restoredCall.name, 'write')
  assert.match(restoredCall.arguments._truncated, /original arguments were \d+ characters/)
})

test('an Event under the limit is untouched and unmarked', () => {
  const event = entryToEvent('s', 0, entries.toolResult)
  assert.equal(isTruncatedEvent(event), false)
  assert.equal(JSON.parse(event.Metadata).piTruncated, undefined)
})

test('an entry with nothing to cut down is rejected rather than stored over the limit', () => {
  const custom = base('custom', 'big5', null, { customType: 'x', data: { blob: 'q'.repeat(300_000) } })
  assert.throws(() => entryToEvent('s', 0, custom), /over the 200000-byte Event limit/)
})
