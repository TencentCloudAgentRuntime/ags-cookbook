import { existsSync, mkdirSync, readdirSync, renameSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { eventToEntry, seqOfEvent, stateToHeader } from './session-codec.js'

/** Local file name pi uses for a session: <timestamp>_<id>.jsonl in the session directory. */
export function sessionFileName(header) {
  return `${header.timestamp.replace(/[:.]/g, '-')}_${header.id}.jsonl`
}

function hasLocalFile(sessionDir, sessionId) {
  return existsSync(sessionDir) && readdirSync(sessionDir).some(name => name.endsWith(`_${sessionId}.jsonl`))
}

/** Reads a cloud Session and returns its pi header and entries, or undefined when it is not a pi session. */
export async function readSession(client, sessionId) {
  const session = await client.describeSession(sessionId)
  if (session === undefined || !client.ownsSession(session)) return undefined
  const header = stateToHeader(session.State?.CustomState)
  if (header === undefined) return undefined
  const events = await client.listEvents(sessionId)
  events.forEach((event, index) => {
    if (seqOfEvent(event) !== index) {
      throw new Error(`Session ${sessionId} is not contiguous: expected sequence ${index}, found ${String(seqOfEvent(event))}`)
    }
  })
  return { header, entries: events.map(eventToEntry) }
}

/**
 * Writes a cloud Session to the directory pi reads sessions from. Returns the file
 * path, or undefined when the Session is not in the cloud or already on disk.
 */
export async function restoreSession(client, sessionId, sessionDir) {
  if (hasLocalFile(sessionDir, sessionId)) return undefined
  const session = await readSession(client, sessionId)
  if (session === undefined) return undefined
  mkdirSync(sessionDir, { recursive: true })
  const path = join(sessionDir, sessionFileName(session.header))
  const lines = [session.header, ...session.entries].map(record => `${JSON.stringify(record)}\n`).join('')
  // pi must never see a half-written file, so write beside it and rename.
  writeFileSync(`${path}.tmp`, lines)
  renameSync(`${path}.tmp`, path)
  return path
}
