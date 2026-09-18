import { createElement as h, useMemo } from 'react'
import { en, NS, zh } from './locales.js'
import { collaborationSource } from './source.js'
import { styles } from './styles.js'
import { participationView } from './view-model.js'

const CORE_GLYPHS = { registry: 'R', coordinator: 'DS', bridge: 'A2A', workspace: 'W' }

const STATUS_BY_ACTION = action => {
  if (action?.includes('failed') || action?.includes('error')) return 'error'
  if (action?.includes('completed') || action === 'turn-end' || action === 'registry-discovered') return 'completed'
  if (action === 'agent-discovered') return 'discovered'
  return 'working'
}

function nodeTitle(t, node) {
  return node.group === 'agent' ? node.label : t(`node.${node.id}`)
}

function formatAction(t, event, nodes) {
  const node = event.nodeId === undefined ? null : nodes.get(event.nodeId)
  const agent = node === undefined || node === null ? '' : nodeTitle(t, node)
  return t(`action.${event.action}`, { agent, count: event.count ?? 0 })
}

function glyphFor(node) {
  if (node.group !== 'agent') return CORE_GLYPHS[node.id]
  const tokens = String(node.label ?? node.recordId ?? 'A')
    .replace(/^demo[-_.]/iu, '')
    .split(/[-_.\s/]+/u)
    .filter(Boolean)
  if (tokens.length > 1) return tokens.slice(0, 2).map(token => token[0]).join('').toUpperCase()
  return [...(tokens[0] ?? 'A')].slice(0, 2).join('').toUpperCase()
}

function hueFor(value) {
  let hash = 0
  for (const character of String(value)) hash = ((hash << 5) - hash + character.codePointAt(0)) | 0
  return Math.abs(hash) % 360
}

function NodeCard({ node, t }) {
  const title = nodeTitle(t, node)
  const latest = node.latest === null ? t('status.idle') : formatAction(t, { ...node.latest, nodeId: node.id }, new Map([[node.id, node]]))
  const details = [
    node.recordId === null ? null : `${t('detail.record')} · ${node.recordId}`,
    node.versionId === null ? null : `${t('detail.version')} · ${node.versionId}`,
    node.taskId === null ? null : `${t('detail.task')} · ${node.taskId}`,
  ].filter(Boolean)
  const style = node.group === 'agent' ? { '--agent-hue': `${hueFor(node.recordId)}deg` } : undefined
  const nodeClass = node.group === 'platform' ? ` dsh-collab-node-${node.id}` : ''
  return h('article', {
    className: `dsh-collab-node dsh-collab-node-${node.group}${nodeClass} ${node.status}`,
    'data-node-id': node.id,
    style,
  },
  h('div', { className: 'dsh-collab-node-glow', 'aria-hidden': true }),
  h('div', { className: 'dsh-collab-node-head' },
    h('span', { className: 'dsh-collab-avatar', 'aria-hidden': true }, glyphFor(node)),
    h('div', { className: 'dsh-collab-node-title' },
      h('strong', { title }, title),
      h('span', { className: 'dsh-collab-status' }, t(`status.${node.status}`)),
    ),
    node.group === 'agent' ? h('span', { className: 'dsh-collab-protocol' }, node.descriptorType ?? 'A2A') : null,
  ),
  node.description === null ? null : h('p', { className: 'dsh-collab-description', title: node.description }, node.description),
  h('p', { className: 'dsh-collab-latest' }, latest),
  h('div', { className: 'dsh-collab-meta' },
    details.length === 0
      ? h('div', null, t('detail.calls', { count: node.calls }))
      : details.map(value => h('div', { key: value, title: value }, value)),
  ))
}

function Metric({ value, label }) {
  return h('div', { className: 'dsh-collab-metric' }, h('strong', null, value), h('span', null, label))
}

function InvocationCard({ invocation, index, t }) {
  const node = invocation.node
  const rawTitle = node === null ? invocation.recordId : nodeTitle(t, node)
  const title = rawTitle
    .replace(/^demo[-_.](?:rd[-_.])?/iu, '')
    .replace(/[-_.]agent$/iu, ' Agent')
  const needsEvidence = invocation.outcome === 'INSUFFICIENT_EVIDENCE'
  const status = invocation.outcome === 'BLOCKED' || needsEvidence ? 'blocked' : invocation.status
  const outcome = invocation.outcome === null
    ? t(`status.${invocation.status}`)
    : ['READY', 'PASSED', 'BLOCKED', 'INSUFFICIENT_EVIDENCE'].includes(invocation.outcome)
      ? t(`outcome.${invocation.outcome}`)
      : invocation.outcome
  const style = node?.group === 'agent' ? { '--agent-hue': `${hueFor(node.recordId)}deg` } : undefined
  return h('article', {
    className: `dsh-collab-invocation-card ${status}`,
    'data-task-id': invocation.taskId,
    style,
  },
  h('span', { className: 'dsh-collab-invocation-index' }, String(index + 1).padStart(2, '0')),
  h('div', { className: 'dsh-collab-invocation-head' },
    h('span', { className: 'dsh-collab-avatar', 'aria-hidden': true }, glyphFor(node ?? { group: 'agent', label: title, recordId: invocation.recordId })),
    h('div', null,
      h('strong', { title }, title),
      h('span', { className: 'dsh-collab-invocation-outcome' }, outcome),
    ),
    h('span', { className: 'dsh-collab-protocol' }, node?.descriptorType ?? 'A2A'),
  ),
  h('div', { className: 'dsh-collab-invocation-meta' },
    h('span', { title: invocation.versionId ?? '' }, invocation.versionId ?? t('detail.versionUnknown')),
    h('code', { title: invocation.taskId }, invocation.taskId),
  ))
}

function Route({ state, label, vertical = false }) {
  return h('div', { className: `dsh-collab-route ${vertical ? 'vertical' : 'horizontal'} ${state}` },
    h('span', { className: 'dsh-collab-route-track', 'aria-hidden': true }, h('i', null)),
    h('span', { className: 'dsh-collab-route-label' }, label),
  )
}

function invocationState(bridge, agentNodes, taskCount) {
  if (bridge.status === 'error') return 'error'
  if (bridge.status === 'working' || agentNodes.some(node => node.status === 'working')) return 'working'
  if (taskCount > 0) return 'completed'
  return 'idle'
}

function CollaborationView({ useCollaboration, useSession, t }) {
  const snapshot = useCollaboration(value => value)
  const running = useSession(value => value.running)
  const nodes = useMemo(() => new Map(snapshot.nodes.map(node => [node.id, node])), [snapshot.nodes])
  const registry = nodes.get('registry')
  const coordinator = nodes.get('coordinator')
  const bridge = nodes.get('bridge')
  const workspace = nodes.get('workspace')
  const invocations = snapshot.invocations
  const participation = useMemo(() => participationView(snapshot), [snapshot])
  const agentNodes = participation.agentNodes
  const displayEvents = participation.events
  const invokeState = invocationState(bridge, agentNodes, snapshot.metrics.a2aTasks)

  return h('div', { className: 'dsh-collab-root', 'data-conversation-composer-overlay': '' },
    h('div', { className: 'dsh-collab-atmosphere', 'aria-hidden': true }, h('i', null), h('i', null), h('i', null)),
    h('header', { className: 'dsh-collab-header' },
      h('div', { className: 'dsh-collab-heading' },
        h('div', null, h('h2', null, t('title')), h('p', { className: 'dsh-collab-subtitle' }, t('subtitle'))),
        h('span', { className: `dsh-collab-live${running ? '' : ' replay'}` }, running ? t('live') : t('replay')),
      ),
      h('div', { className: 'dsh-collab-metrics' },
        h(Metric, { value: agentNodes.length, label: t('metric.participants') }),
        h(Metric, { value: snapshot.metrics.a2aTasks, label: t('metric.tasks') }),
        h(Metric, { value: snapshot.metrics.completed, label: t('metric.completed') }),
        h(Metric, { value: snapshot.metrics.failed, label: t('metric.failed') }),
      ),
    ),
    h('div', { className: 'dsh-collab-content' },
      h('section', { className: 'dsh-collab-stage', 'aria-label': t('section.flow') },
        h('h3', { className: 'dsh-collab-section-title' }, t('section.flow')),
        h('div', { className: 'dsh-collab-core-map' },
          h('div', { className: 'dsh-collab-core-registry' }, h(NodeCard, { node: registry, t })),
          h('div', { className: 'dsh-collab-core-discovery' }, h(Route, { state: registry.status, label: t('route.discovery') })),
          h('div', { className: 'dsh-collab-core-coordinator' }, h(NodeCard, { node: coordinator, t })),
          h('div', { className: 'dsh-collab-core-local' }, h(Route, { state: workspace.status, label: t('route.local') })),
          h('div', { className: 'dsh-collab-core-workspace' }, h(NodeCard, { node: workspace, t })),
          h('div', { className: 'dsh-collab-core-invocation' }, h(Route, { state: invokeState, label: t('route.invocation'), vertical: true })),
          h('div', { className: 'dsh-collab-core-bridge' }, h(NodeCard, { node: bridge, t })),
        ),
        h('div', { className: `dsh-collab-agent-fanout ${invokeState}` },
          h('div', { className: 'dsh-collab-fanout-spine', 'aria-hidden': true }, h('i', null)),
          h('div', { className: 'dsh-collab-agent-pool-head' },
            h('h3', null, t('section.agentPool')),
            h('span', null, t('agentPool.count', { count: agentNodes.length })),
          ),
          agentNodes.length === 0
            ? h('div', { className: 'dsh-collab-agent-empty' },
              h('span', { 'aria-hidden': true }, '+'),
              h('p', null, t('empty.agents')),
            )
            : h('div', { className: 'dsh-collab-agents' }, agentNodes.map(node => h('div', {
              key: node.id,
              className: `dsh-collab-agent-slot ${node.status}`,
            },
            h('span', { className: 'dsh-collab-agent-link', 'aria-hidden': true }, h('i', null)),
            h(NodeCard, { node, t }),
            ))),
        ),
        invocations.length === 0 ? null : h('section', { className: 'dsh-collab-invocation-chain', 'aria-label': t('section.invocationChain') },
          h('div', { className: 'dsh-collab-chain-head' },
            h('div', null,
              h('h3', null, t('section.invocationChain')),
              h('p', null, t('invocationChain.subtitle')),
            ),
            h('span', null, t('invocationChain.count', { count: invocations.length })),
          ),
          h('div', { className: 'dsh-collab-chain-list' }, invocations.map((invocation, index) => h('div', {
            key: invocation.taskId,
            className: 'dsh-collab-chain-step',
          },
          index === 0 ? null : h('span', { className: 'dsh-collab-chain-arrow', 'aria-hidden': true }, h('i', null)),
          h(InvocationCard, { invocation, index, t }),
          ))),
        ),
      ),
      h('aside', { className: 'dsh-collab-timeline', 'aria-label': t('section.timeline') },
        h('h3', { className: 'dsh-collab-section-title' }, t('section.timeline')),
        displayEvents.length === 0
          ? h('div', { className: 'dsh-collab-empty' }, t('empty'))
          : h('ol', { className: 'dsh-collab-events' }, displayEvents.map((event, index) => {
            const detail = event.taskId ?? event.recordId ?? null
            return h('li', { key: event.id, className: `dsh-collab-event ${STATUS_BY_ACTION(event.action)}${index === 0 ? ' newest' : ''}` },
              h('time', { dateTime: new Date(event.time).toISOString() }, new Date(event.time).toLocaleTimeString([], { hour12: false })),
              h('strong', null, formatAction(t, event, nodes)),
              detail === null ? null : h('code', { title: detail }, detail),
            )
          })),
      ),
    ),
  )
}

export const inject = ['slots', 'uiSession', 'locale']

export function apply(ctx) {
  const sources = new WeakMap()
  const sourceFor = binding => {
    let source = sources.get(binding)
    if (source === undefined) {
      source = collaborationSource(binding)
      sources.set(binding, source)
    }
    return source
  }

  ctx.uiSession.provide({
    hooks: ['collaboration'],
    resolve: binding => ({ hooks: { collaboration: sourceFor(binding) } }),
  })

  ctx.effect(() => {
    const tagId = '@local/dsh-collaboration-stage/styles'
    if (document.querySelector(`style[data-plugin-css="${tagId}"]`) !== null) return () => {}
    const tag = document.createElement('style')
    tag.dataset.pluginCss = tagId
    tag.textContent = styles
    document.head.appendChild(tag)
    return () => { tag.remove() }
  }, 'collaboration-stage: styles')
  ctx.effect(() => ctx.locale.register(NS, { zh, en }), 'collaboration-stage: dictionaries')
  const t = ctx.locale.bind(NS)
  ctx.slots.inject('conversation.view', () => ctx.slots.register({
    name: 'conversation.view',
    id: 'collaboration',
    order: 20,
    locale: NS,
    label: () => t('view.label'),
  }, CollaborationView))
}
