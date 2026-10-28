import assert from 'node:assert/strict'
import { mkdtempSync, readFileSync, readdirSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import test from 'node:test'
import agsPiSession from './index.js'
import { FakeSessionService } from './fake-session-service.js'
import { modelsJson } from './model-config.js'
import { readSession, restoreSession, sessionFileName } from './session-restore.js'
import { SessionSync } from './session-sync.js'

const header = { type: 'session', version: 3, id: 's1', timestamp: '2026-10-27T01:02:03.456Z', cwd: '/workspace' }
const usage = { input: 1, output: 1, cacheRead: 0, cacheWrite: 0, totalTokens: 2, cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } }
const entry = (id, parentId, message) => ({ type: 'message', id, parentId, timestamp: '2026-10-27T01:02:04.000Z', message })
const user = (id, parentId, text) => entry(id, parentId, { role: 'user', content: text, timestamp: 1 })
const assistant = (id, parentId, text) => entry(id, parentId, {
  role: 'assistant', content: [{ type: 'text', text }], api: 'a', provider: 'p', model: 'm', usage, stopReason: 'stop', timestamp: 2,
})
const system = { type: 'message', id: 'sys', parentId: null, timestamp: 't', message: { role: 'system', content: '', sections: {}, timestamp: 0 } }

test('nothing is created until the session holds a conversation', async () => {
  const service = new FakeSessionService()
  const sync = await SessionSync.open(service, 's1')
  await sync.flush(header, [system])
  assert.equal(service.sessions.size, 0)
  await sync.flush(header, [system, user('u1', 'sys', 'hi')])
  assert.equal(service.sessions.get('s1').events.length, 2)
})

test('only entries beyond the synced prefix are sent, in order', async () => {
  const service = new FakeSessionService()
  const sync = await SessionSync.open(service, 's1')
  const entries = [user('u1', null, 'hi')]
  await sync.flush(header, entries)
  entries.push(assistant('a1', 'u1', 'hello'), user('u2', 'a1', 'again'))
  await sync.flush(header, entries)
  await sync.flush(header, entries)
  assert.equal(service.appended, 3)
  assert.deepEqual(service.sessions.get('s1').events.map(event => event.EventId), ['pi-s1-0', 'pi-s1-1', 'pi-s1-2'])
})

test('a failed flush resumes from the last event that landed', async () => {
  const service = new FakeSessionService()
  const sync = await SessionSync.open(service, 's1')
  const entries = [user('u1', null, 'a'), assistant('a1', 'u1', 'b'), user('u2', 'a1', 'c')]
  service.failAppendsAfter = 1
  await assert.rejects(sync.flush(header, entries), /append failed/)
  assert.equal(sync.synced, 1)
  service.failAppendsAfter = Infinity
  await sync.flush(header, entries)
  assert.equal(service.sessions.get('s1').events.length, 3)
})

test('opening an existing session continues after its stored events', async () => {
  const service = new FakeSessionService()
  const first = await SessionSync.open(service, 's1')
  const entries = [user('u1', null, 'a'), assistant('a1', 'u1', 'b')]
  await first.flush(header, entries)
  const second = await SessionSync.open(service, 's1')
  assert.equal(second.synced, 2)
  entries.push(user('u2', 'a1', 'c'))
  await second.flush(header, entries)
  assert.equal(service.sessions.get('s1').events.length, 3)
})

test('a local session shorter than the cloud copy is an error, not an overwrite', async () => {
  const service = new FakeSessionService()
  const first = await SessionSync.open(service, 's1')
  await first.flush(header, [user('u1', null, 'a'), assistant('a1', 'u1', 'b')])
  const second = await SessionSync.open(service, 's1')
  await assert.rejects(second.flush(header, [user('u1', null, 'a')]), /2 entries in the cloud but only 1 locally/)
})

test('a Session this extension did not write is refused', async () => {
  const service = new FakeSessionService()
  service.sessions.set('s1', { state: '{"other":true}', events: [], metadata: [] })
  await assert.rejects(SessionSync.open(service, 's1'), /was not written by this extension/)
})

test('restore rebuilds the exact session file pi reads', async () => {
  const service = new FakeSessionService()
  const entries = [system, user('u1', 'sys', 'remember MARKER-7'), assistant('a1', 'u1', 'ok MARKER-7')]
  await (await SessionSync.open(service, 's1')).flush(header, entries)

  const dir = mkdtempSync(join(tmpdir(), 'pi-restore-'))
  const path = await restoreSession(service, 's1', dir)
  assert.equal(path, join(dir, sessionFileName(header)))
  assert.equal(sessionFileName(header), '2026-10-27T01-02-03-456Z_s1.jsonl')
  const records = readFileSync(path, 'utf8').trim().split('\n').map(line => JSON.parse(line))
  assert.deepEqual(records, [header, ...entries])
  assert.deepEqual(readdirSync(dir), [sessionFileName(header)])
  // A second restore leaves the file alone.
  writeFileSync(path, 'local edits\n')
  assert.equal(await restoreSession(service, 's1', dir), undefined)
  assert.equal(readFileSync(path, 'utf8'), 'local edits\n')
})

test('restore returns nothing for a session the cloud does not have', async () => {
  const service = new FakeSessionService()
  assert.equal(await restoreSession(service, 'missing', mkdtempSync(join(tmpdir(), 'pi-restore-'))), undefined)
})

test('restore rejects a session with a gap in its sequence', async () => {
  const service = new FakeSessionService()
  await (await SessionSync.open(service, 's1')).flush(header, [user('u1', null, 'a'), assistant('a1', 'u1', 'b'), user('u2', 'a1', 'c')])
  service.sessions.get('s1').events.splice(1, 1)
  await assert.rejects(readSession(service, 's1'), /not contiguous: expected sequence 1, found 2/)
})

function fakePi() {
  const handlers = new Map()
  return { on: (name, handler) => handlers.set(name, handler), handlers }
}

function fakeContext(sessionId, entries) {
  const notices = []
  return {
    notices,
    ui: { notify: (message, level) => notices.push({ message, level }) },
    sessionManager: {
      getSessionId: () => sessionId,
      getHeader: () => ({ ...header, id: sessionId }),
      getEntries: () => entries,
    },
  }
}

test('the extension flushes on pi events and keeps one sync per session id', async () => {
  const service = new FakeSessionService()
  const pi = fakePi()
  agsPiSession(pi, { client: service, log: () => {} })
  for (const event of ['message_end', 'turn_end', 'agent_before_settle', 'session_shutdown', 'session_compact']) {
    assert.ok(pi.handlers.has(event), event)
  }
  const first = [user('u1', null, 'a')]
  await pi.handlers.get('turn_end')({}, fakeContext('s1', first))
  first.push(assistant('a1', 'u1', 'b'))
  await pi.handlers.get('session_shutdown')({}, fakeContext('s1', first))
  await pi.handlers.get('turn_end')({}, fakeContext('s2', [user('u9', null, 'other')]))
  assert.equal(service.sessions.get('s1').events.length, 2)
  assert.equal(service.sessions.get('s2').events.length, 1)
})

test('a failed save is logged, reported to the client, and retried by the next flush', async () => {
  const service = new FakeSessionService()
  const logged = []
  const pi = fakePi()
  agsPiSession(pi, { client: service, log: message => logged.push(message) })
  const entries = [user('u1', null, 'a'), assistant('a1', 'u1', 'b')]
  const context = fakeContext('s1', entries)
  service.failAppendsAfter = 0
  await pi.handlers.get('turn_end')({}, context)
  assert.equal(logged.length, 1)
  assert.match(logged[0], /saving session s1 .* append failed/)
  assert.equal(context.notices[0].level, 'error')
  service.failAppendsAfter = Infinity
  await pi.handlers.get('agent_end')({}, context)
  assert.equal(service.sessions.get('s1').events.length, 2)
})

test('model configuration is built from LLM_* and never contains the key', () => {
  const config = modelsJson({ LLM_BASE_URL: ' https://llm.example/v1 ', LLM_MODEL: 'm-1', LLM_API_KEY: 'secret-key' })
  assert.deepEqual(config.providers.custom, {
    baseUrl: 'https://llm.example/v1', api: 'openai-completions', apiKey: '$LLM_API_KEY', models: [{ id: 'm-1' }],
  })
  assert.ok(!JSON.stringify(config).includes('secret-key'))
  assert.throws(() => modelsJson({ LLM_BASE_URL: 'x', LLM_MODEL: ' ' }), /set LLM_MODEL, LLM_API_KEY/)
})

test('a truncated entry is logged and the rest of the session keeps syncing', async () => {
  const service = new FakeSessionService()
  const logged = []
  const sync = await SessionSync.open(service, 's1', message => logged.push(message))
  const entries = [user('u1', null, 'q'.repeat(500_000)), assistant('a1', 'u1', 'fine')]
  await sync.flush(header, entries)
  assert.equal(service.sessions.get('s1').events.length, 2)
  assert.equal(logged.length, 1)
  assert.match(logged[0], /entry u1 of session s1 exceeds the Session event size limit/)
})

test('a Session tagged for another Agent is refused before anything is written', async () => {
  const service = new FakeSessionService()
  service.agentId = 'agent-b'
  service.sessions.set('s1', {
    state: JSON.stringify({ piHeader: header, piFormat: 1 }),
    events: [],
    metadata: [{ Name: 'example.com/pi-agent-id', Value: 'agent-a' }],
  })
  await assert.rejects(SessionSync.open(service, 's1'), /belongs to a different SESSION_AGENT_ID/)
  assert.equal(service.appended, 0)
})
