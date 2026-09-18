const PROJECTED_EVENT_TYPES = new Set([
  'turn/start',
  'turn/end',
  'user/message',
  'tool/call',
  'tool/result',
])

function eventSeq(entry) {
  const seq = Number(entry?.event?.seq)
  return Number.isSafeInteger(seq) ? seq : null
}

/**
 * Keep the projection's relevant event history independent of DSH's moving
 * event window. Long live sessions may evict an earlier tool call before its
 * terminal result arrives; retaining both is required to resolve the result.
 */
export function createProjectionEventLog(initialEntries = []) {
  const entriesBySeq = new Map()

  const merge = entries => {
    let changed = false
    for (const entry of entries ?? []) {
      const seq = eventSeq(entry)
      if (seq === null || !PROJECTED_EVENT_TYPES.has(entry?.event?.type)) continue
      if (!entriesBySeq.has(seq)) changed = true
      entriesBySeq.set(seq, entry)
    }
    return changed
  }

  const entries = () => [...entriesBySeq.entries()]
    .sort(([left], [right]) => left - right)
    .map(([, entry]) => entry)

  merge(initialEntries)
  return { entries, merge }
}
