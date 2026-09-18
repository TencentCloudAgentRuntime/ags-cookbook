import assert from 'node:assert/strict'
import test from 'node:test'
import { createCompleteHistoryLoader } from '../src/history.js'

function bindingWithPages(pages) {
  let snapshot = pages.shift()
  let calls = 0
  return {
    binding: {
      eventSource: { getSnapshot: () => snapshot },
      session: {
        getSnapshot: () => ({ openState: 'open' }),
        async loadOlder() {
          calls += 1
          snapshot = pages.shift() ?? snapshot
        },
      },
    },
    calls: () => calls,
    snapshot: () => snapshot,
  }
}

test('loads every older page until the Session window is complete', async () => {
  const fixture = bindingWithPages([
    { revision: 1, hasMore: true },
    { revision: 2, hasMore: true },
    { revision: 3, hasMore: false },
  ])
  const loader = createCompleteHistoryLoader(fixture.binding)

  await loader.load()

  assert.equal(fixture.calls(), 2)
  assert.equal(fixture.snapshot().hasMore, false)
})

test('shares one traversal across concurrent load requests', async () => {
  const fixture = bindingWithPages([
    { revision: 1, hasMore: true },
    { revision: 2, hasMore: false },
  ])
  const loader = createCompleteHistoryLoader(fixture.binding)

  await Promise.all([loader.load(), loader.load()])

  assert.equal(fixture.calls(), 1)
})

test('stops cleanly when another consumer owns the older-page request', async () => {
  let calls = 0
  const snapshot = { revision: 1, hasMore: true }
  const binding = {
    eventSource: { getSnapshot: () => snapshot },
    session: {
      getSnapshot: () => ({ openState: 'open' }),
      async loadOlder() { calls += 1 },
    },
  }
  const loader = createCompleteHistoryLoader(binding)

  await loader.load()

  assert.equal(calls, 1)
})

test('waits for the Session to finish opening before requesting older pages', async () => {
  let calls = 0
  const binding = {
    eventSource: { getSnapshot: () => ({ revision: 1, hasMore: true }) },
    session: {
      getSnapshot: () => ({ openState: 'loading' }),
      async loadOlder() { calls += 1 },
    },
  }
  const loader = createCompleteHistoryLoader(binding)

  await loader.load()

  assert.equal(calls, 0)
})
