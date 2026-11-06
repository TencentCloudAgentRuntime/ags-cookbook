import { seqOfEvent, stateToHeader } from './session-codec.js'

// An in-memory stand-in for SessionClient, with the service behaviour the example relies on:
// events keep what they were sent, a repeated EventId with the same content is accepted.
export class FakeSessionService {
  sessions = new Map()
  failAppendsAfter = Infinity
  appended = 0
  agentId = undefined

  async describeSession(id) {
    const session = this.sessions.get(id)
    return session && { SessionId: id, State: { CustomState: session.state }, Metadata: session.metadata }
  }

  async createSession(id, state) {
    if (this.sessions.has(id)) throw new Error('duplicate session')
    this.sessions.set(id, { state, events: [], metadata: [] })
  }

  async appendEvent(id, event) {
    if (this.appended >= this.failAppendsAfter) throw new Error('append failed')
    const session = this.sessions.get(id)
    if (!session) throw new Error('no session')
    const existing = session.events.findIndex(item => item.EventId === event.EventId)
    const stored = JSON.parse(JSON.stringify(event))
    if (existing >= 0) session.events[existing] = stored
    else session.events.push(stored)
    this.appended += 1
  }

  async countEvents(id) {
    return this.sessions.get(id).events.length
  }

  async listEvents(id) {
    return [...this.sessions.get(id).events].sort((left, right) => seqOfEvent(left) - seqOfEvent(right))
  }

  async listSessionIds() {
    return [...this.sessions.keys()].filter(id => stateToHeader(this.sessions.get(id).state) !== undefined)
  }

  ownsSession(session) {
    return this.agentId === undefined || session.Metadata?.some(item => item.Value === this.agentId)
  }
}
