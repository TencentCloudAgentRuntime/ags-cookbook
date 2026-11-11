// Keep identical across pi base/reference and DSH base/reference; covered by the copy test.
// Mirror only title changes observed on newly persisted events. Reads never repair history.
function objectValue(raw) {
  try {
    const value = typeof raw === 'string' ? JSON.parse(raw) : raw
    return value !== null && typeof value === 'object' && !Array.isArray(value) ? value : undefined
  } catch { return undefined }
}

export function withSessionTitles(request, titleOfEvent) {
  const titles = new Map()
  const chains = new Map()
  const dispatch = async (action, payload) => {
    const key = JSON.stringify([payload.SpaceId, payload.UserId, payload.SessionId])
    if (action === 'DescribeSession') {
      const response = await request(action, payload)
      const raw = response.Session?.State?.CustomState
      const state = objectValue(raw)
      const saved = state?.sessionTitleSync
      // Only our new writes carry this marker. Reading never backfills a legacy title.
      if (saved?.version === 1 && Number.isSafeInteger(saved.sequence) && saved.sequence >= 0
        && typeof saved.title === 'string'
        && (!titles.has(key) || saved.sequence >= titles.get(key).sequence)) {
        titles.set(key, { sequence: saved.sequence, title: saved.title,
          dirty: (response.Session.Title ?? '') !== saved.title })
      }
      return response
    }
    if (action !== 'AppendEvent') return request(action, payload)
    const run = (chains.get(key) ?? Promise.resolve()).then(async () => {
      const title = titleOfEvent(payload.Event)
      let stored = payload
      if (title !== undefined) {
        const raw = payload.Event.Actions?.StateDelta
        const delta = objectValue(raw)
        if (raw !== undefined && delta === undefined) {
          // A malformed event is a caller bug, not a transient failure: retrying
          // the same payload can never succeed.
          throw Object.assign(new TypeError('Title event StateDelta must be a JSON object'), { code: 'invalid-title-event', retryable: false })
        }
        stored = { ...payload, Event: { ...payload.Event, Actions: { ...payload.Event.Actions,
          StateDelta: JSON.stringify({ ...delta, sessionTitleSync: { version: 1, ...title } }) } } }
      }
      const result = await request(action, stored)
      let current = titles.get(key)
      if (title !== undefined && (current === undefined || title.sequence >= current.sequence)) {
        if (current === undefined || title.sequence > current.sequence || title.title !== current.title) {
          current = { ...title, dirty: true }
          titles.set(key, current)
        }
      }
      // Empty native names must remain empty after the service's user-message fallback.
      if (current !== undefined && (current.dirty || (current.title === '' && payload.Event.Content?.Role === 'user'))) {
        await request('ModifySession', { SpaceId: payload.SpaceId, UserId: payload.UserId,
          SessionId: payload.SessionId, Title: current.title })
        current.dirty = false
      }
      return result
    })
    const settled = run.catch(() => {})
    chains.set(key, settled)
    void settled.then(() => { if (chains.get(key) === settled) chains.delete(key) })
    return run
  }
  // Drop the in-memory title state of a session that is no longer open here.
  const forget = payload => {
    const key = JSON.stringify([payload.SpaceId, payload.UserId, payload.SessionId])
    titles.delete(key)
    chains.delete(key)
  }
  // A content-validating sync may find the event already stored after a failed
  // ModifySession. Retry the pending title even when there are no entries left to append.
  return Object.assign(dispatch, { forget, flush: payload => {
    const key = JSON.stringify([payload.SpaceId, payload.UserId, payload.SessionId])
    const run = (chains.get(key) ?? Promise.resolve()).then(async () => {
      const current = titles.get(key)
      if (!current?.dirty) return
      await request('ModifySession', { SpaceId: payload.SpaceId, UserId: payload.UserId,
        SessionId: payload.SessionId, Title: current.title })
      current.dirty = false
    })
    const settled = run.catch(() => {})
    chains.set(key, settled)
    void settled.then(() => { if (chains.get(key) === settled) chains.delete(key) })
    return run
  } })
}

export function dshEventTitle(event) {
  const ext = objectValue(event.Extensions)
  const native = ext?.dshEvent
  if (native?.type !== 'session/title' || typeof native.data?.title !== 'string'
    || !Number.isSafeInteger(native.seq) || native.seq < 0) return undefined
  return { sequence: native.seq, title: native.data.title }
}

export function piEventTitle(event) {
  const ext = objectValue(event.Extensions)
  const native = ext?.pi?.entry
  if (native?.type !== 'session_info' || typeof native.name !== 'string'
    || !Number.isSafeInteger(ext.pi.seq) || ext.pi.seq < 0) return undefined
  return { sequence: ext.pi.seq, title: native.name }
}
