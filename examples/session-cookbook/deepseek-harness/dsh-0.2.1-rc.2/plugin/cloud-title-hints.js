// Read-only list hints from cloud Title. Native cached/live projections retain priority.
export function installCloudTitleHints(ctx, titles) {
  ctx.inject(['sessionProjectionCache'], child => {
    const cache = child.sessionProjectionCache
    child.effect(() => {
      const original = cache.cachedSnapshot
      const wrapped = function(header, keys) {
        const block = original.call(this, header, keys)
        if (keys && !keys.includes('title')) return block
        if (block?.values?.title !== undefined && block.values.title !== null) return block
        const title = titles.get(header.id)
        if (typeof title !== 'string' || title.length === 0) return block
        return { asOfSeq: block?.asOfSeq ?? 0, values: { ...block?.values, title } }
      }
      cache.cachedSnapshot = wrapped
      return () => { if (cache.cachedSnapshot === wrapped) cache.cachedSnapshot = original }
    }, 'cloud Session title list hints')
  })
}
