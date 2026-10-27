import assert from 'node:assert/strict'
import test from 'node:test'
import { AGENT_METADATA_KEY, SessionClient, configFromEnv } from './session-client.js'
import { entryToEvent } from './session-codec.js'

const config = { region: 'ap-shanghai', secretId: 'id', secretKey: 'key', spaceId: 'space-1', userId: 'user-1' }

function sdk(handler) {
  const calls = []
  return { calls, request: async (action, payload) => { calls.push({ action, payload }); return handler(action, payload, calls) } }
}

const message = seq => entryToEvent('s1', seq, {
  type: 'message', id: `e${seq}`, parentId: null, timestamp: 't', message: { role: 'user', content: `m${seq}`, timestamp: 1 },
})

test('configuration comes from the environment and names what is missing', () => {
  const env = {
    AGR_REGION: 'ap-shanghai', TENCENTCLOUD_SECRET_ID: 'id', TENCENTCLOUD_SECRET_KEY: 'key',
    SESSION_SPACE_ID: 'space-1', SESSION_USER_ID: 'user-1', SESSION_AGENT_ID: ' agent-a ',
  }
  assert.equal(configFromEnv(env).agentId, 'agent-a')
  assert.equal(configFromEnv(env).endpoint, undefined)
  assert.throws(() => configFromEnv({ ...env, SESSION_SPACE_ID: ' ' }), /SESSION_SPACE_ID is required/)
})

test('listEvents pages through the Session and orders by stored sequence', async () => {
  const all = [3, 0, 4, 1, 2].map(message)
  const client = new SessionClient(config, sdk((action, payload) => {
    assert.equal(action, 'DescribeEvents')
    assert.equal(payload.SpaceId, 'space-1')
    assert.equal(payload.UserId, 'user-1')
    // The service may return fewer rows than Limit; the client must keep paging.
    return { Events: all.slice(payload.Offset, payload.Offset + 2), TotalCount: all.length }
  }))
  const events = await client.listEvents('s1')
  assert.deepEqual(events.map(event => event.EventId), [0, 1, 2, 3, 4].map(seq => `pi-s1-${seq}`))
})

test('rate-limited calls are retried and other errors are not', async () => {
  let attempts = 0
  const limited = Object.assign(new Error('slow down'), { code: 'RequestLimitExceeded.UinLimitExceeded' })
  const client = new SessionClient(config, sdk(() => {
    attempts += 1
    if (attempts < 3) throw limited
    return { TotalCount: 7 }
  }))
  assert.equal(await client.countEvents('s1'), 7)
  assert.equal(attempts, 3)

  const denied = Object.assign(new Error('denied'), { code: 'AuthFailure' })
  const failing = new SessionClient(config, sdk(() => { throw denied }))
  await assert.rejects(failing.countEvents('s1'), /denied/)
})

test('describeSession maps a missing Session to undefined', async () => {
  const missing = Object.assign(new Error('gone'), { code: 'ResourceNotFound.SessionNotExist' })
  assert.equal(await new SessionClient(config, sdk(() => { throw missing })).describeSession('s1'), undefined)
  assert.deepEqual(
    await new SessionClient(config, sdk(() => ({ Session: { SessionId: 's1' } }))).describeSession('s1'),
    { SessionId: 's1' },
  )
})

test('createSession tags the Agent and accepts a retried create with the same state', async () => {
  const duplicate = Object.assign(new Error('dup'), { code: 'ResourceInUse.SessionIdDuplicate' })
  const service = sdk(action => {
    if (action === 'CreateSession') throw duplicate
    return { Session: { State: { CustomState: '{"x":1}' } } }
  })
  const client = new SessionClient({ ...config, agentId: 'agent-a' }, service)
  await client.createSession('s1', '{"x":1}')
  assert.deepEqual(service.calls[0].payload.Metadata, [{ Name: AGENT_METADATA_KEY, Value: 'agent-a' }])
  await assert.rejects(client.createSession('s1', '{"x":2}'), /dup/)
})

test('listSessionIds filters by Agent and ownsSession checks the tag', async () => {
  const service = sdk(() => ({ Sessions: [{ SessionId: 'a' }, { SessionId: 'b' }], TotalCount: 2 }))
  const client = new SessionClient({ ...config, agentId: 'agent-a' }, service)
  assert.deepEqual(await client.listSessionIds(), ['a', 'b'])
  assert.deepEqual(service.calls[0].payload.Filters, [{ Name: `metadata:${AGENT_METADATA_KEY}`, Values: ['agent-a'] }])
  assert.equal(client.ownsSession({ Metadata: [{ Name: AGENT_METADATA_KEY, Value: 'agent-a' }] }), true)
  assert.equal(client.ownsSession({ Metadata: [] }), false)
  assert.equal(new SessionClient(config, service).ownsSession({}), true)
})
