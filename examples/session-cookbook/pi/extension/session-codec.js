// Converts between pi session entries and Agent Runtime Session Events.
//
// Content lives once. Message text, reasoning, tool arguments and tool results go to
// Content.Parts, where other systems can read them. Everything a Part cannot express
// (entry id and parent, signatures, usage, model, tool call ids, details) goes to
// Extensions as the same entry with its content removed. Images go to
// InlineData; a region whose DescribeEvents does not return InlineData (observed in
// ap-chongqing, not in ap-shanghai) cannot restore them, and restore says so.
// Entries without conversational content are stored whole in Extensions.

export const CODEC_VERSION = 1
export const EXTENSION_KEY = 'pi'

// The Session service fails reads and writes of a whole Session, deletes included,
// once one of its Events grows past roughly 250 KB (observed: 200 KB works, 300 KB
// breaks the Session). Events are kept under this many bytes of JSON.
export const MAX_EVENT_BYTES = 200_000

const BODY_FIELDS = {
  text: ['text'],
  thinking: ['thinking'],
  image: ['data'],
  toolCall: ['name', 'arguments'],
}

function clone(value) {
  return structuredClone(value)
}

function without(object, fields) {
  const copy = { ...object }
  for (const field of fields) delete copy[field]
  return copy
}

function parseJson(value, fallback) {
  if (value === undefined || value === null || value === '') return fallback
  return typeof value === 'string' ? JSON.parse(value) : value
}

function blockToPart(block) {
  switch (block.type) {
    case 'text':
      return { Text: block.text }
    case 'thinking':
      return { Text: block.thinking, Thought: true }
    case 'image':
      return { InlineData: { MimeType: block.mimeType, Data: block.data } }
    case 'toolCall':
      return { FunctionCall: JSON.stringify({ Name: block.name, Args: block.arguments }) }
    default:
      throw new Error(`unsupported content block type "${block.type}"`)
  }
}

function partToBody(skeleton, part) {
  switch (skeleton.type) {
    case 'text':
      return { ...skeleton, text: part.Text ?? '' }
    case 'thinking':
      return { ...skeleton, thinking: part.Text ?? '' }
    case 'image':
      // Sessions written before images moved to InlineData keep the data in the entry.
      if (typeof part.InlineData?.Data === 'string') return { ...skeleton, data: part.InlineData.Data }
      if (typeof skeleton.data === 'string') return { ...skeleton }
      throw new Error('corrupt pi session event: an image has no InlineData; this region does not return InlineData from DescribeEvents, so a conversation with images cannot be restored here')
    case 'toolCall': {
      const call = parseJson(part.FunctionCall, {})
      return { ...skeleton, name: call.Name, arguments: call.Args ?? {} }
    }
    default:
      throw new Error(`unsupported content block type "${skeleton.type}"`)
  }
}

const KNOWN_BLOCKS = new Set(Object.keys(BODY_FIELDS))

function isBlockArray(content) {
  return Array.isArray(content) && content.every(block => block && KNOWN_BLOCKS.has(block.type))
}

function textOfBlocks(blocks) {
  return blocks.filter(block => block.type === 'text').map(block => block.text).join('\n')
}

function messageErrors(entry) {
  const message = entry.message
  if (message.role === 'assistant' && (message.stopReason === 'error' || message.errorMessage)) {
    return { ErrorCode: 'MODEL_ERROR', ErrorMessage: String(message.errorMessage ?? 'model error') }
  }
  if (message.role === 'toolResult' && message.isError === true) {
    return { ErrorCode: 'TOOL_ERROR', ErrorMessage: textOfBlocks(Array.isArray(message.content) ? message.content : []) }
  }
  return {}
}

// Returns { author, role, parts, skeleton, body } for entries with conversational content, or undefined.
function project(entry) {
  if (entry.type === 'message') {
    const message = entry.message
    if (message.role === 'user' || message.role === 'assistant') {
      if (typeof message.content === 'string' && message.role === 'user') {
        return {
          author: 'user', role: 'user', body: 'string',
          parts: [{ Text: message.content }],
          skeleton: { ...entry, message: without(message, ['content']) },
        }
      }
      if (isBlockArray(message.content)) {
        return {
          author: message.role, role: message.role, body: 'blocks',
          parts: message.content.map(blockToPart),
          skeleton: {
            ...entry,
            message: { ...message, content: message.content.map(block => without(block, BODY_FIELDS[block.type])) },
          },
        }
      }
    }
    if (message.role === 'toolResult' && isBlockArray(message.content)) {
      return {
        author: 'tool', role: 'tool', body: 'toolResult',
        parts: [{
          FunctionResponse: JSON.stringify({ Name: message.toolName, Response: { content: message.content } }),
        }],
        skeleton: { ...entry, message: without(message, ['content']) },
      }
    }
    return undefined
  }
  if (entry.type === 'custom_message') {
    if (typeof entry.content === 'string') {
      return {
        author: 'pi', role: 'user', body: 'string',
        parts: [{ Text: entry.content }],
        skeleton: without(entry, ['content']),
      }
    }
    if (isBlockArray(entry.content)) {
      return {
        author: 'pi', role: 'user', body: 'blocks',
        parts: entry.content.map(blockToPart),
        skeleton: { ...entry, content: entry.content.map(block => without(block, BODY_FIELDS[block.type])) },
      }
    }
    return undefined
  }
  if ((entry.type === 'compaction' || entry.type === 'branch_summary') && typeof entry.summary === 'string') {
    return {
      author: 'pi', role: 'user', body: 'summary',
      parts: [{ Text: entry.summary }],
      skeleton: without(entry, ['summary']),
    }
  }
  return undefined
}

export function eventIdFor(sessionId, seq) {
  return `pi-${sessionId}-${seq}`
}

export function headerToState(header) {
  return JSON.stringify({ piHeader: header, piFormat: CODEC_VERSION })
}

export function stateToHeader(state) {
  const parsed = parseJson(state, {})
  if (!parsed.piHeader) return undefined
  if (parsed.piFormat !== CODEC_VERSION) {
    throw new Error(`unsupported pi session format ${String(parsed.piFormat)}; this build reads format ${CODEC_VERSION}`)
  }
  return parsed.piHeader
}

function buildEvent(sessionId, seq, entry, truncated) {
  const projected = project(entry)
  const metadata = { source: 'pi', piEntryType: entry.type, piSeq: seq, ...(truncated ? { piTruncated: true } : {}) }
  if (entry.type === 'message' && entry.message.role === 'assistant') {
    metadata.TurnComplete = entry.message.stopReason !== 'toolUse'
  }
  const flags = truncated ? { truncated: true } : {}
  const extension = projected === undefined
    ? { v: CODEC_VERSION, seq, ...flags, entry: clone(entry) }
    : { v: CODEC_VERSION, seq, ...flags, body: projected.body, entry: clone(projected.skeleton) }
  return {
    EventId: eventIdFor(sessionId, seq),
    InvocationId: `pi-${sessionId}`,
    Author: projected?.author ?? 'pi',
    ...(projected ? { Content: { Role: projected.role, Parts: projected.parts } } : {}),
    Metadata: JSON.stringify(metadata),
    ...(entry.type === 'message' ? messageErrors(entry) : {}),
    Extensions: JSON.stringify({ [EXTENSION_KEY]: extension }),
  }
}

function eventBytes(event) {
  return Buffer.byteLength(JSON.stringify(event))
}

// The fields of an entry that hold bulk content, as { size, shrink } handles.
function shrinkables(entry) {
  const refs = []
  // Cutting a field shorter than its truncation note would grow it.
  const MIN_SHRINKABLE = 256
  const text = (owner, field) => {
    if (typeof owner[field] === 'string' && owner[field].length > MIN_SHRINKABLE) {
      refs.push({ size: owner[field].length, shrink: () => {
        // A field cut more than once keeps the length it had before the first cut.
        const note = /\n\[truncated: original (\d+) characters\]$/.exec(owner[field])
        const body = note ? owner[field].slice(0, note.index) : owner[field]
        const original = note ? Number(note[1]) : body.length
        owner[field] = `${body.slice(0, Math.floor(body.length / 2))}\n[truncated: original ${original} characters]`
      } })
    }
  }
  const blocks = list => {
    if (!Array.isArray(list)) return
    for (const block of list) {
      if (block.type === 'text') text(block, 'text')
      else if (block.type === 'thinking') text(block, 'thinking')
      else if (block.type === 'image' && block.data.length > MIN_SHRINKABLE) {
        refs.push({ size: block.data.length, shrink: () => {
          const note = `[image omitted: ${block.data.length} characters of ${block.mimeType} data]`
          for (const key of Object.keys(block)) delete block[key]
          Object.assign(block, { type: 'text', text: note })
        } })
      } else if (block.type === 'toolCall') {
        const size = JSON.stringify(block.arguments).length
        if (size > MIN_SHRINKABLE) {
          refs.push({ size, shrink: () => { block.arguments = { _truncated: `original arguments were ${size} characters` } } })
        }
      }
    }
  }
  if (entry.type === 'message') {
    text(entry.message, 'content')
    blocks(entry.message.content)
  } else {
    text(entry, 'content')
    text(entry, 'summary')
    blocks(entry.content)
  }
  return refs
}

/**
 * Converts one pi entry to a Session Event. An entry whose Event would exceed
 * maxBytes is stored with its largest text cut down until it fits, and the Event is
 * marked truncated; restoring it returns the cut-down entry.
 */
export function entryToEvent(sessionId, seq, entry, { maxBytes = MAX_EVENT_BYTES } = {}) {
  let event = buildEvent(sessionId, seq, entry, false)
  if (eventBytes(event) <= maxBytes) return event
  const shrunk = clone(entry)
  const refs = shrinkables(shrunk)
  for (;;) {
    const largest = refs.reduce((best, ref) => (ref.size > best.size ? ref : best), { size: 0 })
    if (largest.size === 0) {
      throw new Error(`entry ${entry.id} (${entry.type}) needs ${eventBytes(event)} bytes, over the ${maxBytes}-byte Event limit, and has no content that can be cut down`)
    }
    largest.shrink()
    refs.length = 0
    refs.push(...shrinkables(shrunk))
    event = buildEvent(sessionId, seq, shrunk, true)
    if (eventBytes(event) <= maxBytes) return event
  }
}

export function isTruncatedEvent(event) {
  return parseJson(event.Extensions, {})[EXTENSION_KEY]?.truncated === true
}

function fail(message) {
  throw new Error(`corrupt pi session event: ${message}`)
}

function partsOf(event) {
  return event.Content?.Parts ?? []
}

function mergeBlocks(skeletons, parts, where) {
  if (!Array.isArray(skeletons) || skeletons.length !== parts.length) {
    fail(`${where} has ${parts.length} parts for ${Array.isArray(skeletons) ? skeletons.length : 0} content blocks`)
  }
  return skeletons.map((skeleton, index) => partToBody(skeleton, parts[index]))
}

export function eventToEntry(event) {
  const stored = parseJson(event.Extensions, {})[EXTENSION_KEY]
  if (!stored) fail(`${event.EventId ?? '<unknown>'} has no pi extension data`)
  if (stored.v !== CODEC_VERSION) fail(`${event.EventId} uses codec version ${String(stored.v)}`)
  const entry = clone(stored.entry)
  const parts = partsOf(event)
  switch (stored.body) {
    case undefined:
      return entry
    case 'string': {
      const text = parts[0]?.Text ?? ''
      if (entry.type === 'message') entry.message.content = text
      else entry.content = text
      return entry
    }
    case 'blocks':
      if (entry.type === 'message') entry.message.content = mergeBlocks(entry.message.content, parts, event.EventId)
      else entry.content = mergeBlocks(entry.content, parts, event.EventId)
      return entry
    case 'toolResult': {
      const response = parseJson(parts[0]?.FunctionResponse, undefined)
      if (!response?.Response?.content) fail(`${event.EventId} has no tool result content`)
      entry.message.content = response.Response.content
      return entry
    }
    case 'summary':
      entry.summary = parts[0]?.Text ?? ''
      return entry
    default:
      return fail(`${event.EventId} has unknown body kind "${String(stored.body)}"`)
  }
}

export function seqOfEvent(event) {
  const seq = parseJson(event.Extensions, {})[EXTENSION_KEY]?.seq
  return Number.isInteger(seq) ? seq : undefined
}
