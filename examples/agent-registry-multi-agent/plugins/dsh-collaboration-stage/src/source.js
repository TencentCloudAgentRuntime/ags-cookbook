import { createProjectionEventLog } from './event-log.js'
import { createCompleteHistoryLoader } from './history.js'
import { CollaborationProjector } from './projection.js'

export function collaborationSource(binding) {
  const projector = new CollaborationProjector()
  const history = createCompleteHistoryLoader(binding)
  let eventWindow = binding.eventSource.getSnapshot()
  const eventLog = createProjectionEventLog(eventWindow.entries)
  projector.replace(eventLog.entries())
  let snapshot = projector.snapshot
  const listeners = new Set()
  let disposeEvents = null
  let disposeSession = null

  const refresh = (catchUp = false) => {
    const next = binding.eventSource.getSnapshot()
    if (next.revision !== eventWindow.revision) {
      // A tab can be unmounted while the Session keeps receiving events. On
      // re-subscribe, `change` only describes the latest mutation, so merging
      // that delta would lose every event received while nobody was listening.
      const entries = catchUp || next.change.kind !== 'append'
        ? next.entries
        : next.change.entries
      const changed = eventLog.merge(entries)
      eventWindow = next
      void history.load()
      if (!changed) return
      projector.replace(eventLog.entries())
      snapshot = projector.snapshot
      for (const listener of [...listeners]) listener()
    }
  }

  const refreshSession = () => {
    if (binding.session.getSnapshot().openState === 'open') void history.load()
  }

  return {
    getSnapshot: () => snapshot,
    subscribe: listener => {
      listeners.add(listener)
      if (disposeEvents === null) disposeEvents = binding.eventSource.subscribe(refresh)
      if (disposeSession === null) disposeSession = binding.session.subscribe(refreshSession)
      // Reconcile the complete current window immediately. No new event may
      // arrive after a finished Session, so waiting for the next subscription
      // callback would leave historical playback stale.
      refresh(true)
      void history.load()
      return () => {
        listeners.delete(listener)
        if (listeners.size === 0 && disposeEvents !== null) {
          disposeEvents()
          disposeEvents = null
        }
        if (listeners.size === 0 && disposeSession !== null) {
          disposeSession()
          disposeSession = null
        }
      }
    },
  }
}
