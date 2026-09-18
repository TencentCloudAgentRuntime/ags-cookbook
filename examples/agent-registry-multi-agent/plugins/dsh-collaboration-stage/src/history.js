const reportLoadFailure = error => {
  console.error('[collaboration-stage] failed to load complete session history:', error)
}

/**
 * Pull every older Session page before projecting a historical collaboration.
 * Live prepends synchronously update eventSource, so callers only need to invoke
 * load once; concurrent invocations share the same in-flight traversal.
 */
export function createCompleteHistoryLoader(binding, onError = reportLoadFailure) {
  let inFlight = null

  const load = () => {
    if (inFlight !== null) return inFlight
    if (binding.session.getSnapshot().openState !== 'open') return Promise.resolve()
    if (!binding.eventSource.getSnapshot().hasMore) return Promise.resolve()

    inFlight = (async () => {
      while (true) {
        const before = binding.eventSource.getSnapshot()
        if (!before.hasMore) return
        await binding.session.loadOlder()
        const after = binding.eventSource.getSnapshot()
        // Another consumer may already be loading this page. Its eventual
        // prepend will call load again through the event-source subscription.
        if (after.revision === before.revision) return
      }
    })().catch(onError).finally(() => {
      inFlight = null
    })
    return inFlight
  }

  return { load }
}
