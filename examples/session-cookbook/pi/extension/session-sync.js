import { entryToEvent, headerToState, isTruncatedEvent, stateToHeader } from './session-codec.js'

// pi writes a session file only once it holds a conversation. Cloud Sessions follow
// the same rule, so starting pi never creates an empty Session.
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

  flush(header, entries) {
    const run = this.chain.then(() => this.send(header, entries))
    this.chain = run.catch(() => {})
    return run
  }

  async send(header, entries) {
    if (!hasConversation(entries)) return
    if (entries.length < this.synced) {
      throw new Error(`Session ${this.sessionId} holds ${this.synced} entries in the cloud but only ${entries.length} locally`)
    }
    if (entries.length === this.synced) return
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
