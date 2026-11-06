import assert from 'node:assert/strict'
import test from 'node:test'
import { DEFAULT_SHUTDOWN_ABORT_MS, DEFAULT_SHUTDOWN_GRACE_MS, StatelessPiHost, SessionBusyError } from './host.js'
import { FakeSessionService } from '../extension/fake-session-service.js'
import { SessionSync } from '../extension/session-sync.js'

function generation(sessionId, stored, run = async () => {}, { header: fixedHeader } = {}) {
  const entries = structuredClone(stored?.entries ?? [])
  const header = stored?.header ?? fixedHeader ?? { type: 'session', version: 3, id: sessionId, timestamp: '2026-11-05T00:00:00Z', cwd: '/workspace' }
  const manager = { getHeader: () => header, getEntries: () => entries,
    appendCustomEntry: (customType, data) => entries.push({ type: 'custom', id: crypto.randomUUID(), parentId: entries.at(-1)?.id ?? null, timestamp: new Date().toISOString(), customType, data }) }
  let aborted = false
  return { manager, session: { prompt: run, abort: () => { aborted = true }, dispose() {}, get aborted() { return aborted } }, reply: () => 'ACK' }
}

test('a cold replica rejects unfinished work without a model call or cloud mutation', async () => {
  const client = new FakeSessionService()
  const first = generation('test')
  first.manager.appendCustomEntry('ags-turn-boundary', { state: 'open' })
  await (await SessionSync.open(client, 'test')).flush(first.manager.getHeader(), first.manager.getEntries(), { force: true })
  let called = false
  const host = new StatelessPiHost({ client, createGeneration: async () => { called = true } })
  await assert.rejects(host.prompt('test', 'hello'), { code: 'session/agent-busy' })
  assert.equal(called, false)
  assert.equal(client.appended, 1)
})

test('a persistence failure before the claim prevents any model or tool execution', async () => {
  const client = new FakeSessionService(); client.failAppendsAfter = 0
  let called = false
  const host = new StatelessPiHost({ client, createGeneration: async (id, stored) => generation(id, stored, async () => { called = true }) })
  await assert.rejects(host.prompt('test', 'hello'), /append failed/)
  assert.equal(called, false)
})

test('a failed model call closes the turn it claimed, is not replayed, and the next request proceeds', async () => {
  const client = new FakeSessionService(); let calls = 0
  const host = new StatelessPiHost({ client, createGeneration: async (id, stored) => generation(id, stored, async () => {
    calls++
    if (calls === 1) throw new Error('model unavailable')
  }) })
  await assert.rejects(host.prompt('test', 'hello'), /model unavailable/)
  assert.equal(calls, 1)
  const events = client.sessions.get('test').events.map(event => JSON.stringify(event))
  assert.ok(events.some(text => text.includes('"outcome\\":\\"error\\"')), 'the closed boundary records the error outcome')
  const retry = await host.prompt('test', 'retry')
  assert.equal(retry.reply, 'ACK')
  assert.equal(calls, 2)
})

test('a persistence failure during execution leaves the turn open', async () => {
  const client = new FakeSessionService()
  const host = new StatelessPiHost({ client, createGeneration: async (id, stored) => {
    const gen = generation(id, stored)
    gen.session.subscribe = listener => { gen.emit = listener; return () => {} }
    gen.session.prompt = async () => { client.failAppendsAfter = client.appended; gen.emit({ type: 'message_end' }); await new Promise(r => setTimeout(r, 5)) }
    return gen
  } })
  await assert.rejects(host.prompt('test', 'hello'), /append failed/)
  client.failAppendsAfter = Infinity
  await assert.rejects(host.prompt('test', 'retry'), { code: 'session/agent-busy' })
})

test('losing the claim never closes the winner\'s turn', async () => {
  const client = new FakeSessionService()
  // Replica A holds an open turn written by someone else at the position B will claim.
  const a = generation('test'); a.manager.appendCustomEntry('ags-turn-boundary', { state: 'open', requestId: 'a' })
  const sync = await SessionSync.open(client, 'test')
  await sync.flush(a.manager.getHeader(), a.manager.getEntries(), { force: true })
  // B read the history before A claimed, so its claim lands on the same position.
  const stale = { header: a.manager.getHeader(), entries: [] }
  const realList = client.listEvents.bind(client); let first = true
  client.listEvents = async id => { if (first) { first = false; return [] } return realList(id) }
  const host = new StatelessPiHost({ client, createGeneration: async (id) => generation(id, stale, async () => { throw new Error('must not run') }) })
  await assert.rejects(host.prompt('test', 'hello'), error => error.code === 'ResourceInUse.EventIdDuplicate' || error instanceof SessionBusyError)
  assert.equal(client.sessions.get('test').events.length, 1, 'no closed boundary was appended over the winner')
})

test('checkpoints after the claim do not re-read the whole history', async () => {
  const client = new FakeSessionService(); let reads = 0
  const realList = client.listEvents.bind(client)
  client.listEvents = async id => { reads++; return realList(id) }
  const host = new StatelessPiHost({ client, createGeneration: async (id, stored) => {
    const gen = generation(id, stored)
    gen.session.subscribe = listener => { gen.emit = listener; return () => {} }
    gen.session.prompt = async () => { for (let i = 0; i < 5; i++) { gen.manager.appendCustomEntry('note', { i }); gen.emit({ type: 'message_end' }) } }
    return gen
  } })
  await host.prompt('test', 'hello')
  await host.prompt('test', 'again')
  // One read to load history per request, plus none per checkpoint.
  assert.ok(reads <= 4, `expected at most 4 full reads, got ${reads}`)
})

test('simultaneous requests for a new Session leave a clear loser', async () => {
  const client = new FakeSessionService()
  const make = ts => new StatelessPiHost({ client, createGeneration: async (id, stored) =>
    generation(id, stored, async () => {}, { header: { type: 'session', version: 3, id, timestamp: ts, cwd: '/workspace' } }) })
  const results = await Promise.allSettled([make('2026-11-06T00:00:00.000Z').prompt('race', 'hi'), make('2026-11-06T00:00:00.001Z').prompt('race', 'hi')])
  const failed = results.filter(r => r.status === 'rejected')
  assert.equal(results.filter(r => r.status === 'fulfilled').length, 1)
  assert.equal(failed.length, 1)
  assert.match(failed[0].reason.code, /^ResourceInUse\.(SessionIdDuplicate|EventIdDuplicate)$/)
})

test('shutdown refuses new turns, waits for running ones, then aborts the rest', async () => {
  const client = new FakeSessionService(); let finish
  const slow = new StatelessPiHost({ client, createGeneration: async (id, stored) => {
    const gen = generation(id, stored)
    gen.session.prompt = () => new Promise((_, reject) => { finish = reject })
    gen.session.abort = () => finish(new Error('aborted'))
    return gen
  } })
  const running = slow.prompt('slow', 'hello').catch(error => error)
  await new Promise(r => setTimeout(r, 20))
  const left = await slow.shutdown({ graceMs: 20, abortMs: 200 })
  assert.deepEqual(left, [])
  assert.match((await running).message, /aborted/)
  await assert.rejects(slow.prompt('other', 'hello'), { code: 'session/shutting-down' })
  // The aborted turn closed its boundary, so a replica that starts later can use the Session.
  const fresh = new StatelessPiHost({ client, createGeneration: async (id, stored) => generation(id, stored) })
  assert.equal((await fresh.prompt('slow', 'again')).reply, 'ACK')
})

// A replica left an open turn behind at wall-clock `at`.
async function leaveOpenTurn(client, id, requestId = 'dead') {
  const dead = generation(id)
  dead.manager.appendCustomEntry('ags-turn-boundary', { state: 'open', requestId })
  await (await SessionSync.open(client, id)).flush(dead.manager.getHeader(), dead.manager.getEntries(), { force: true })
}

const lastBoundaryStates = (client, id) => client.sessions.get(id).events
  .map(event => JSON.stringify(event))
  .filter(text => text.includes('ags-turn-boundary'))
  .map(text => /\\?"state\\?":\\?"(open|closed)/.exec(text)?.[1] + (text.includes('abandoned') ? '(abandoned)' : text.includes('completed') ? '(completed)' : ''))

test('a turn active within the timeout is refused with a retry hint and left untouched', async () => {
  const client = new FakeSessionService()
  await leaveOpenTurn(client, 'test')
  const host = new StatelessPiHost({ client, openTurnTimeoutMs: 60_000, now: () => Date.now() + 20_000,
    createGeneration: async () => { throw new Error('must not start') } })
  const busy = await host.prompt('test', 'hello').catch(error => error)
  assert.equal(busy.code, 'session/agent-busy')
  assert.ok(busy.retryAfterMs > 30_000 && busy.retryAfterMs <= 40_000, `retryAfterMs was ${busy.retryAfterMs}`)
  assert.equal(client.appended, 1, 'nothing was appended')
})

test('a turn quiet for the whole timeout is treated as crashed, closed, and the request proceeds', async () => {
  const client = new FakeSessionService()
  await leaveOpenTurn(client, 'test')
  let model = 0
  const host = new StatelessPiHost({ client, openTurnTimeoutMs: 60_000, now: () => Date.now() + 120_000,
    createGeneration: async (id, stored) => generation(id, stored, async () => { model++ }) })
  assert.equal((await host.prompt('test', 'hello')).reply, 'ACK')
  assert.equal(model, 1)
  assert.deepEqual(lastBoundaryStates(client, 'test'), ['open', 'closed(abandoned)', 'open', 'closed(completed)'])
})

test('without a configured timeout an open turn is never taken over', async () => {
  const client = new FakeSessionService()
  await leaveOpenTurn(client, 'test')
  const host = new StatelessPiHost({ client, now: () => Date.now() + 86_400_000, createGeneration: async () => { throw new Error('must not start') } })
  await assert.rejects(host.prompt('test', 'hello'), { code: 'session/agent-busy' })
})

test('an open turn with no readable timestamp is never taken over', async () => {
  const client = new FakeSessionService()
  await leaveOpenTurn(client, 'test')
  const events = client.sessions.get('test').events
  const last = events.at(-1); const ext = JSON.parse(last.Extensions)
  ext.pi.entry.timestamp = 'not a date'; last.Extensions = JSON.stringify(ext)
  const host = new StatelessPiHost({ client, openTurnTimeoutMs: 1, now: () => Date.now() + 86_400_000,
    createGeneration: async () => { throw new Error('must not start') } })
  await assert.rejects(host.prompt('test', 'hello'), { code: 'session/agent-busy' })
})

test('if the old executor was alive, the takeover fences it out and its turn fails without closing the new one', async () => {
  const client = new FakeSessionService()
  let release
  const gate = new Promise(resolve => { release = resolve })
  // A: slow turn. It claims, then stalls long enough to look dead.
  const slow = new StatelessPiHost({ client, createGeneration: async (id, stored) => {
    const gen = generation(id, stored)
    gen.session.subscribe = listener => { gen.emit = listener; return () => {} }
    gen.session.prompt = async () => { await gate; gen.manager.appendCustomEntry('note', { late: true }); gen.emit({ type: 'message_end' }); await new Promise(r => setTimeout(r, 10)) }
    return gen
  } })
  const aTurn = slow.prompt('test', 'slow').catch(error => error)
  await new Promise(r => setTimeout(r, 20))
  // B decides A has been quiet long enough and takes over.
  const taker = new StatelessPiHost({ client, openTurnTimeoutMs: 60_000, now: () => Date.now() + 120_000,
    createGeneration: async (id, stored) => generation(id, stored) })
  assert.equal((await taker.prompt('test', 'take over')).reply, 'ACK')
  // A wakes up and writes: it lands on a position B already filled.
  release()
  const failure = await aTurn
  assert.equal(failure.code, 'ResourceInUse.EventIdDuplicate')
  const states = lastBoundaryStates(client, 'test')
  assert.equal(states.at(-1), 'closed(completed)', 'A did not close or overwrite B\'s turn')
  assert.ok(states.includes('closed(abandoned)'))
})

test('the default shutdown budget fits inside the Kubernetes default termination grace period', () => {
  const KUBERNETES_DEFAULT_GRACE_MS = 30_000
  assert.ok(DEFAULT_SHUTDOWN_GRACE_MS + DEFAULT_SHUTDOWN_ABORT_MS < KUBERNETES_DEFAULT_GRACE_MS,
    'grace + abort must leave a margin below the orchestrator grace period')
})
