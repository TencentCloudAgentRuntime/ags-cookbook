import { entryToEvent, eventToEntry, headerToState, isTruncatedEvent, stateToHeader } from './session-codec.js'

// Starting pi alone creates no cloud Session. A conversation or an explicit
// native session_info rename is persistence activity and materializes the Session.
function hasConversation(entries) {
  return entries.some(entry => entry.type === 'message' && (entry.message.role === 'user' || entry.message.role === 'assistant'))
}

/**
 * Copies one pi session to a cloud Session. pi entries are append-only, so the
 * synced prefix is a count. Each flush sends the entries beyond it, in order, one
 * AppendEvent each. A failed flush leaves the count where the last event landed and
 * the next flush resumes from there; EventIds are stable, so a retry is harmless.
 */
export class SessionSync {
  chain = Promise.resolve()

  constructor(client, sessionId, state, log = () => {}) {
    this.client = client
    this.sessionId = sessionId
    this.log = log
    this.synced = state.synced
    this.created = state.created
  }

  /** Reads how much of the Session is already in the cloud. */
  static async open(client, sessionId, log) {
    const session = await client.describeSession(sessionId)
    if (session === undefined) return new SessionSync(client, sessionId, { synced: 0, created: false }, log)
    if (!client.ownsSession(session)) {
      throw new Error(`Session ${sessionId} belongs to a different SESSION_AGENT_ID; refusing to write to it`)
    }
    if (stateToHeader(session.State?.CustomState) === undefined) {
      throw new Error(`Session ${sessionId} exists but was not written by this extension`)
    }
    return new SessionSync(client, sessionId, { synced: await client.countEvents(sessionId), created: true }, log)
  }

  /** Continues from history the caller has just read and validated, without another read. */
  static fromStored(client, sessionId, stored, log) {
    return new SessionSync(client, sessionId, { synced: stored.entries.length, created: true }, log)
  }

  /**
   * @param options.force  send even when the entries hold no conversation yet.
   * @param options.verify compare the cloud history with `entries` before appending
   *   (default true). Pass false once the caller holds the turn claim: any other
   *   writer then fails with EventIdDuplicate at the next position anyway.
   */
  flush(header, entries, options = {}) {
    const run = this.chain.then(() => this.send(header, entries, options))
    this.chain = run.catch(() => {})
    return run
  }

  async send(header, entries, options = {}) {
    if (!options.force && !hasConversation(entries) && !entries.some(entry => entry.type === 'session_info') && !this.created) return
    if (entries.length < this.synced) {
      // The cloud is ahead of this copy, so another writer got there first. Same
      // class of failure as a lost append, and callers handle it the same way.
      throw Object.assign(
        new Error(`Session ${this.sessionId} holds ${this.synced} entries in the cloud but only ${entries.length} locally; reload cloud history before continuing`),
        { code: 'ResourceInUse.EventIdDuplicate' })
    }
    if (this.created && options.verify !== false) {
      const remote = await this.client.listEvents(this.sessionId)
      for (let index = 0; index < remote.length; index += 1) {
        const expected = entries[index] === undefined ? undefined : eventToEntry(entryToEvent(this.sessionId, index, entries[index]))
        if (expected === undefined || stable(expected) !== stable(eventToEntry(remote[index]))) {
          const error = new Error(`Session ${this.sessionId} history changed at entry ${index}; reload cloud history before continuing`)
          error.code = 'ResourceInUse.EventIdDuplicate'
          throw error
        }
      }
      this.synced = remote.length
    }
    if (entries.length === this.synced) {
      await this.client.flushTitle?.(this.sessionId)
      return
    }
    if (!this.created) {
      await this.client.createSession(this.sessionId, headerToState(header))
      this.created = true
    }
    while (this.synced < entries.length) {
      const event = entryToEvent(this.sessionId, this.synced, entries[this.synced])
      if (isTruncatedEvent(event)) {
        this.log(`entry ${entries[this.synced].id} of session ${this.sessionId} exceeds the Session event size limit; its largest content was cut down before saving`)
      }
      await this.client.appendEvent(this.sessionId, event)
      this.synced += 1
    }
  }
}

function stable(value) {
  if (Array.isArray(value)) return '[' + value.map(stable).join(',') + ']'
  if (value && typeof value === 'object') return '{' + Object.keys(value).sort().map(key => JSON.stringify(key) + ':' + stable(value[key])).join(',') + '}'
  return JSON.stringify(value)
}
