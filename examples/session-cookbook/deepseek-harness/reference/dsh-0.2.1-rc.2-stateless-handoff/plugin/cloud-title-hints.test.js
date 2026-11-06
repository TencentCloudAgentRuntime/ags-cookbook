import assert from 'node:assert/strict'
import test from 'node:test'
import { installCloudTitleHints } from './cloud-title-hints.js'

test('cold lists use cloud Title without loading history, keep native values and restore on unload', () => {
  let dispose
  let block
  const original = () => block
  const cache = { cachedSnapshot: original }
  const ctx = { inject(_names, callback) { callback({ sessionProjectionCache: cache,
    effect(setup) { dispose = setup() } }) } }
  const titles = new Map([['test', '云端标题']])
  installCloudTitleHints(ctx, titles)
  assert.deepEqual(cache.cachedSnapshot({ id: 'test' }), { asOfSeq: 0, values: { title: '云端标题' } })
  block = { asOfSeq: 8, values: undefined }
  assert.deepEqual(cache.cachedSnapshot({ id: 'test' }), { asOfSeq: 8, values: { title: '云端标题' } })
  block = { asOfSeq: 8, values: { title: '原生标题', other: 1 } }
  assert.equal(cache.cachedSnapshot({ id: 'test' }), block)
  block = { asOfSeq: 8, values: { title: null, other: 1 } }
  assert.deepEqual(cache.cachedSnapshot({ id: 'test' }), { asOfSeq: 8, values: { title: '云端标题', other: 1 } })
  assert.equal(cache.cachedSnapshot({ id: 'test' }, ['other']), block)
  assert.equal(cache.cachedSnapshot({ id: 'missing' }), block)
  dispose();assert.equal(cache.cachedSnapshot, original)
})
