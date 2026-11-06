import assert from 'node:assert/strict'
import test from 'node:test'
import { DEFAULT_OPEN_TURN_TIMEOUT_MS, idleMs, openTurnTimeoutFromEnv } from './constants.js'

test('the open-turn timeout defaults to ten minutes and can be set from the environment', () => {
  assert.equal(DEFAULT_OPEN_TURN_TIMEOUT_MS, 600_000)
  assert.equal(openTurnTimeoutFromEnv({}), 600_000)
  assert.equal(openTurnTimeoutFromEnv({ OPEN_TURN_TIMEOUT_MS: '  ' }), 600_000)
  assert.equal(openTurnTimeoutFromEnv({ OPEN_TURN_TIMEOUT_MS: '90000' }), 90_000)
})

test('an invalid timeout fails at startup instead of silently using the default', () => {
  for (const value of ['abc', '0', '-5', 'Infinity']) {
    assert.throws(() => openTurnTimeoutFromEnv({ OPEN_TURN_TIMEOUT_MS: value }), /OPEN_TURN_TIMEOUT_MS/)
  }
})

test('idleMs reads the event time as epoch milliseconds and is undefined when unknown', () => {
  assert.equal(idleMs({ time: 1_000 }, 4_000), 3_000)
  assert.equal(idleMs({ time: 5_000 }, 4_000), 0, 'a writer clock slightly ahead is not a negative idle time')
  assert.equal(idleMs({}, 4_000), undefined)
  assert.equal(idleMs(undefined, 4_000), undefined)
  assert.equal(idleMs({ time: 'x' }, 4_000), undefined)
})
