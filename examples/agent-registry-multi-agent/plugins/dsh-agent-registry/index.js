import { defineTool } from '@deepseek-ai/dsh-tools'
import {
  buildDescribePayload,
  buildListPayload,
  buildRegistryListPayload,
  callRegistryAction,
  normalizeDescribeResult,
  normalizeListResult,
  normalizeRegistryListResult,
  resolveRuntimeConfig,
} from './registry-client.js'

export const name = 'agent-registry-tools'
export const inject = ['agents', 'tools', 'systemPrompt']

export const AUTO_DISCOVERY_SOURCE = 'agent-registry:auto-discovery'

const DEFAULT_AUTO_DISCOVERY_LIMIT = 20
const MAX_DISCOVERY_QUERY_LENGTH = 500
const DISCOVERY_POLICY_SECTION = {
  name: 'agent-registry:discovery-policy',
  order: 90,
  text: 'Agent Registry is an access-controlled catalog of governed capabilities across any domain. At the start '
    + 'of each new user goal, an automatic discovery context may provide candidates. A candidate is a clear match when '
    + 'its description names an action, expertise, external operation, review, or verification needed or naturally '
    + 'implied by the requested deliverable. Before performing that action yourself, resolve and invoke the best clear '
    + 'match. Candidate descriptions own their applicability contract: when a description declares the capability an '
    + 'entry point, prerequisite, or required gate for this kind of goal, treat it as a clear match unless the user scope '
    + 'explicitly excludes it. Do not skip such a capability merely because the user input already looks detailed. Task '
    + 'simplicity, your ability to do the work, and direct local tool availability are never reasons to skip '
    + 'a clear match. Select only one best candidate for each distinct capability and do not invoke duplicates. After '
    + 'each result or newly produced artifact, re-evaluate the remaining candidates and invoke every non-redundant clear '
    + 'match needed to close the goal. Capabilities that produce different evidence or decisions are non-redundant: do '
    + 'not collapse independent critique, executable verification, and final readiness into self-review. When an invoked '
    + 'capability returns a structured nextRecommendedCapability, use that exact value as a new capability query and '
    + 'resolve and invoke its best clear match when it supports the user goal; stop on null, a real blocker, or an '
    + 'irrelevant recommendation. This handoff rule applies across domains and never expands the user scope. Never assume '
    + 'a fixed role or workflow; '
    + 'if no candidate description directly matches the goal, continue without delegation and do not fabricate it.',
}

function renderJson(value) {
  return [{ type: 'text', text: JSON.stringify(value, null, 2) }]
}

function optionalString(value) {
  return typeof value === 'string' && value.trim() !== '' ? value.trim() : undefined
}

function optionalBoolean(value, fallback) {
  return typeof value === 'boolean' ? value : fallback
}

function positiveInteger(value, fallback) {
  return Number.isInteger(value) && value > 0 ? value : fallback
}

function messageText(message) {
  if (!Array.isArray(message?.content)) return ''
  return message.content
    .filter(block => block?.type === 'text' && typeof block.text === 'string')
    .map(block => block.text)
    .join('\n')
}

function discoveryGoal(messages) {
  return messages
    .filter(message => message?.source?.kind === 'user')
    .map(messageText)
    .filter(Boolean)
    .join('\n')
    .trim()
    .slice(0, MAX_DISCOVERY_QUERY_LENGTH)
}

function compactRecord(record) {
  return {
    registryId: record.RegistryId ?? record.registryId,
    recordId: record.RecordId ?? record.recordId,
    name: record.Name ?? record.name,
    description: record.Description ?? record.description,
    descriptorType: record.DescriptorType ?? record.descriptorType,
    lifecycleStatus: record.LifecycleStatus ?? record.lifecycleStatus,
    resolvedVersionId: record.ResolvedVersionId ?? record.resolvedVersionId,
    resolvedRevision: record.ResolvedRevision ?? record.resolvedRevision,
  }
}

function cleanObject(value) {
  return Object.fromEntries(Object.entries(value).filter(([, item]) => item !== undefined))
}

function descriptorPriority(record) {
  const type = String(record.DescriptorType ?? record.descriptorType ?? '').toUpperCase()
  return ['A2A', 'MCP', 'AGENT_SKILLS', 'AGUI', 'CUSTOM'].indexOf(type) + 1 || 6
}

function selectDiscoveryCandidates(records, limit) {
  const registries = new Map()
  for (const record of records) {
    const registryId = String(record.RegistryId ?? record.registryId ?? 'unknown')
    if (!registries.has(registryId)) registries.set(registryId, [])
    registries.get(registryId).push(record)
  }

  const selected = []
  for (let priority = 1; priority <= 6 && selected.length < limit; priority += 1) {
    const queues = [...registries.values()].map(recordsInRegistry =>
      recordsInRegistry.filter(record => descriptorPriority(record) === priority))
    let progress = true
    while (progress && selected.length < limit) {
      progress = false
      for (const queue of queues) {
        const candidate = queue.shift()
        if (candidate === undefined) continue
        progress = true
        selected.push(candidate)
        if (selected.length === limit) break
      }
    }
  }
  return selected
}

function autoDiscoveryMessage(goal, result, maxCandidates) {
  const selected = selectDiscoveryCandidates(result.records, maxCandidates)
  const payload = {
    kind: 'agent-registry-auto-discovery',
    goal,
    scope: result.scope ?? 'CONFIGURED_REGISTRY',
    totalCount: result.totalCount,
    candidateSelection: 'A2A_FIRST_CROSS_REGISTRY',
    candidates: selected.map(record => cleanObject(compactRecord(record))),
    partialFailures: result.partialFailures ?? [],
  }
  const text = [
    '<agent-registry-discovery>',
    JSON.stringify(payload),
    'Before beginning substantive work, compare these governed capability candidates with the user goal. A candidate ',
    'is a clear match when its description names an action, expertise, external operation, review, or verification ',
    'needed or naturally implied by the requested deliverable. If one or more candidates clearly match, first select ',
    'one best candidate per distinct capability, ',
    'call registry_describe_record with registry_id set to its registryId and record_id set to its recordId, and invoke ',
    'the resolved capability before performing that action yourself. Candidate descriptions own their applicability ',
    'contract: if one declares itself an entry point, prerequisite, or required gate for this kind of goal, treat it ',
    'as a clear match unless the user scope explicitly excludes it; detailed user input is not a reason to skip it. ',
    'Task simplicity, your own ability, and direct ',
    'tool availability are not reasons to skip a clear match. Re-evaluate remaining candidates after every result or ',
    'new artifact and invoke each non-redundant clear match needed to close the goal. Capabilities that produce different ',
    'evidence or decisions are non-redundant; do not collapse independent critique, executable verification, and final ',
    'readiness into self-review. If an invoked result contains a structured nextRecommendedCapability, use its exact ',
    'value as a new capability query and invoke the best clear match when it supports the user goal. Stop following ',
    'handoffs on null, a real blocker, or an irrelevant recommendation; never expand the user scope. If no candidate description ',
    'directly matches the goal, continue directly without invoking one. ',
    'Never claim a candidate was invoked unless an invocation tool actually completed.',
    '</agent-registry-discovery>',
  ].join('\n')
  return {
    content: [{ type: 'text', text }],
    source: { kind: 'plugin', plugin: AUTO_DISCOVERY_SOURCE },
  }
}

function autoDiscoveryFailureMessage(goal, error) {
  const payload = {
    kind: 'agent-registry-auto-discovery',
    goal,
    candidates: [],
    error: {
      code: error?.code,
      requestId: error?.requestId,
      message: error instanceof Error ? error.message : String(error),
    },
  }
  return {
    content: [{
      type: 'text',
      text: `<agent-registry-discovery>\n${JSON.stringify(payload)}\nRegistry discovery failed. Continue the user task with directly available capabilities; do not retry unless Registry access is essential.\n</agent-registry-discovery>`,
    }],
    source: { kind: 'plugin', plugin: AUTO_DISCOVERY_SOURCE },
  }
}

function selectedRegistryId(runtime, args) {
  const registryId = optionalString(args.registry_id) ?? optionalString(runtime.registryId)
  if (registryId === undefined) {
    throw new Error('registry_id is required when AGENT_REGISTRY_ID is not configured')
  }
  return registryId
}

async function listAllActiveRegistries(runtime, signal) {
  const pageSize = 100
  const registries = []
  const requestIds = []
  let offset = 0
  let totalCount = Number.POSITIVE_INFINITY

  while (offset < totalCount) {
    const response = await callRegistryAction(runtime, 'DescribeRegistryList', buildRegistryListPayload({
      status: 'ACTIVE',
      offset,
      limit: pageSize,
    }), { signal })
    const page = normalizeRegistryListResult(response)
    requestIds.push(page.requestId)
    registries.push(...page.registries)
    totalCount = page.totalCount
    if (page.registries.length === 0) break
    offset += page.registries.length
  }

  if (registries.length === 0 && optionalString(runtime.registryId) !== undefined) {
    return {
      registries: [{ RegistryId: runtime.registryId, Name: 'configured-default' }],
      requestIds,
      usedConfiguredDefault: true,
    }
  }
  return { registries, requestIds, usedConfiguredDefault: false }
}

async function searchOneRegistry(runtime, registryId, args, signal) {
  const payload = buildListPayload(registryId, args)
  const response = await callRegistryAction(runtime, 'DescribeRegistryRecordList', payload, { signal })
  const result = normalizeListResult(registryId, response)
  return {
    ...result,
    records: result.records.map(record => ({
      ...record,
      RegistryId: record.RegistryId ?? registryId,
    })),
  }
}

async function searchAcrossRegistries(runtime, registries, args, signal) {
  const results = []
  const failures = []
  for (const registry of registries) {
    const registryId = optionalString(registry.RegistryId)
    if (registryId === undefined) continue
    try {
      results.push(await searchOneRegistry(runtime, registryId, args, signal))
    } catch (error) {
      failures.push({
        registryId,
        code: error?.code,
        requestId: error?.requestId,
        message: error instanceof Error ? error.message : String(error),
      })
    }
  }
  if (results.length === 0 && failures.length > 0) {
    const detail = failures
      .map(failure => `${failure.registryId}: ${failure.message}`)
      .join('; ')
    const error = new Error(`Agent Registry record search failed in all ${failures.length} registries: ${detail}`)
    error.failures = failures
    throw error
  }
  return { results, failures }
}

function combineRecordResults(registryDiscovery, searchResult) {
  return {
    scope: 'ALL_ACCESSIBLE_REGISTRIES',
    registryCount: registryDiscovery.registries.length,
    registryRequestIds: registryDiscovery.requestIds,
    usedConfiguredDefault: registryDiscovery.usedConfiguredDefault,
    records: searchResult.results.flatMap(result => result.records),
    totalCount: searchResult.results.reduce((sum, result) => sum + result.totalCount, 0),
    perRegistry: searchResult.results.map(result => ({
      registryId: result.registryId,
      requestId: result.requestId,
      returnedCount: result.records.length,
      totalCount: result.totalCount,
    })),
    partialFailures: searchResult.failures,
  }
}

async function discoverRecords(runtime, args, signal) {
  const search = typeof args.search === 'string' ? args.search.trim() : ''
  const offset = args.offset ?? 0
  const explicitRegistryId = optionalString(args.registry_id)
  if (explicitRegistryId !== undefined) {
    const result = await searchOneRegistry(runtime, explicitRegistryId, args, signal)
    if (result.records.length > 0 || search === '' || offset !== 0) return result
    const fallbackArgs = { ...args }
    delete fallbackArgs.search
    const fallback = await searchOneRegistry(runtime, explicitRegistryId, fallbackArgs, signal)
    return {
      ...fallback,
      searchFallback: {
        reason: 'NO_TEXT_MATCHES',
        originalSearch: search,
        originalRequestIds: [result.requestId],
      },
    }
  }

  const registryDiscovery = await listAllActiveRegistries(runtime, signal)
  const initial = await searchAcrossRegistries(runtime, registryDiscovery.registries, args, signal)
  const combined = combineRecordResults(registryDiscovery, initial)
  if (combined.records.length > 0 || search === '' || offset !== 0) return combined

  const fallbackArgs = { ...args }
  delete fallbackArgs.search
  const fallback = await searchAcrossRegistries(runtime, registryDiscovery.registries, fallbackArgs, signal)
  return {
    ...combineRecordResults(registryDiscovery, fallback),
    searchFallback: {
      reason: 'NO_TEXT_MATCHES',
      originalSearch: search,
      originalRequestIds: initial.results.map(result => result.requestId),
    },
  }
}

export function apply(ctx, config = {}) {
  ctx.effect(() => ctx.systemPrompt.section(DISCOVERY_POLICY_SECTION), 'agent-registry.discovery-policy')

  // Presets own an Agent-scoped prompt. A root section alone is therefore not
  // guaranteed to appear in that Agent's first model request. Install the same
  // domain-neutral policy into every live Agent scope before prompt assembly.
  const installedPolicies = new Map()
  const installPolicy = (agent) => {
    if (installedPolicies.has(agent)) return
    installedPolicies.set(agent, agent.ctx.systemPrompt.section(DISCOVERY_POLICY_SECTION))
  }
  for (const agent of ctx.agents.list()) installPolicy(agent)
  ctx.on('agent/created', ({ agent }) => { installPolicy(agent) })
  ctx.on('agent/disposed', ({ agent }) => {
    installedPolicies.get(agent)?.()
    installedPolicies.delete(agent)
  })
  ctx.effect(() => () => {
    for (const dispose of installedPolicies.values()) dispose()
    installedPolicies.clear()
  }, 'agent-registry.discovery-policy.agent-scopes')

  if (optionalBoolean(config.autoDiscover, true)) {
    ctx.on('agent/pre-step', async ({ messages, step, signal }, next) => {
      const decision = await next()
      if (step !== 1 || decision.kind === 'reject') return decision
      const goal = discoveryGoal(messages)
      if (goal === '') return decision
      const maxCandidates = positiveInteger(config.autoDiscoverLimit, DEFAULT_AUTO_DISCOVERY_LIMIT)
      const runtime = resolveRuntimeConfig(config)
      try {
        const result = await discoverRecords(runtime, {
          search: goal,
          lifecycle_status: 'ACTIVE',
          offset: 0,
          limit: maxCandidates,
        }, signal)
        return {
          ...decision,
          messages: [...decision.messages, autoDiscoveryMessage(goal, result, maxCandidates)],
        }
      } catch (error) {
        return {
          ...decision,
          messages: [...decision.messages, autoDiscoveryFailureMessage(goal, error)],
        }
      }
    })
  }

  ctx.tools.register(defineTool({
    name: 'registry_list_registries',
    description: 'List Agent Registries visible to the current cloud identity. Use this to understand discovery '
      + 'scope, to find a Registry by name or description, or before targeting a specific Registry. The Cloud API '
      + 'applies CAM visibility filtering, so the result contains only Registries this identity may discover.',
    parameters: {
      search: {
        type: 'string',
        description: 'Free-text search across Registry metadata.',
      },
      name: {
        type: 'string',
        description: 'Optional exact or product-supported Registry name filter.',
      },
      status: {
        type: 'string',
        enum: ['ACTIVE', 'ARCHIVED'],
        description: 'Optional Registry status filter. ACTIVE is the normal discovery scope.',
      },
      archived: {
        type: 'string',
        enum: ['true', 'false'],
        description: 'Optional archived-state filter supported by the Cloud API.',
      },
      offset: {
        type: 'integer',
        description: 'Zero-based pagination offset. Defaults to 0.',
      },
      limit: {
        type: 'integer',
        description: 'Page size from 1 to 100. Defaults to 20.',
      },
    },
    output: {
      schema: { type: 'json' },
      render: (_args, value) => renderJson(value),
    },
    async execute(args, exec) {
      const runtime = resolveRuntimeConfig(config)
      const response = await callRegistryAction(runtime, 'DescribeRegistryList', buildRegistryListPayload(args), {
        signal: exec.signal,
      })
      return normalizeRegistryListResult(response)
    },
    presentCall: args => ({
      card: 'generic',
      title: 'Discover accessible Agent Registries',
      kind: 'search',
      rawInput: args,
    }),
  }))

  ctx.tools.register(defineTool({
    name: 'registry_list_records',
    description: 'Search the access-controlled Agent Registry catalog for governed agents, MCP servers, skills, and '
      + 'other capabilities across any business domain. Use this as a low-cost discovery step when specialized '
      + 'knowledge, external actions, independent verification, or capabilities beyond the direct tool set may improve '
      + 'the result. Discovery does not require invocation: continue directly when no candidate adds value. When '
      + 'registry_id is omitted, '
      + 'this tool automatically discovers every ACTIVE Registry visible to the current cloud identity and searches '
      + 'each one; returned records carry their RegistryId. Pass registry_id to restrict discovery to one Registry. '
      + 'Compare candidates by Name, Description, and DescriptorType. If the backend text search returns no '
      + 'matches, this tool automatically retries without the text search so semantic selection can still happen. '
      + 'This list returns metadata only; call '
      + 'registry_describe_record on the selected RecordId before invocation.',
    parameters: {
      registry_id: {
        type: 'string',
        description: 'Optional RegistryId. Omit to search all accessible ACTIVE Registries.',
      },
      search: {
        type: 'string',
        description: 'Free-text capability or business requirement, matched against Registry record metadata.',
      },
      name: {
        type: 'string',
        description: 'Optional exact or product-supported name filter.',
      },
      descriptor_type: {
        type: 'string',
        enum: ['MCP', 'A2A', 'AGUI', 'AGENT_SKILLS', 'CUSTOM'],
        description: 'Optional governed descriptor type. A2A is the usual choice when selecting another agent.',
      },
      lifecycle_status: {
        type: 'string',
        enum: ['ACTIVE', 'DELETED'],
        description: 'Optional lifecycle filter. Use ACTIVE for callable candidates.',
      },
      offset: {
        type: 'integer',
        description: 'Zero-based pagination offset. Defaults to 0.',
      },
      limit: {
        type: 'integer',
        description: 'Page size from 1 to 100. Defaults to 20.',
      },
    },
    output: {
      schema: { type: 'json' },
      render: (_args, value) => renderJson(value),
    },
    async execute(args, exec) {
      const runtime = resolveRuntimeConfig(config)
      return discoverRecords(runtime, args, exec.signal)
    },
    presentCall: args => ({
      card: 'generic',
      title: 'Discover agents in Agent Registry',
      kind: 'search',
      rawInput: args,
    }),
  }))

  ctx.tools.register(defineTool({
    name: 'registry_describe_record',
    description: 'Resolve one Agent Registry record to a governed version and return its Descriptors, source '
      + 'configuration, resolved VersionId, and Revision. Use RegistryId and RecordId returned by '
      + 'registry_list_records. registry_id may be omitted only for records from the configured default Registry. Omit both '
      + 'version_id and label to resolve stable, or provide exactly one explicit selector. Call this before invoking '
      + 'the selected agent; never invent an endpoint or version.',
    parameters: {
      registry_id: {
        type: 'string',
        description: 'RegistryId returned by registry_list_records. Defaults to the configured Registry for compatibility.',
      },
      record_id: {
        type: 'string',
        required: true,
        description: 'RecordId returned by registry_list_records.',
      },
      version_id: {
        type: 'string',
        description: 'Optional immutable VersionId. Mutually exclusive with label.',
      },
      label: {
        type: 'string',
        description: 'Optional label such as stable, latest, or canary. Mutually exclusive with version_id.',
      },
    },
    output: {
      schema: { type: 'json' },
      render: (_args, value) => renderJson(value),
    },
    async execute(args, exec) {
      const runtime = resolveRuntimeConfig(config)
      const registryId = selectedRegistryId(runtime, args)
      const payload = buildDescribePayload(registryId, args)
      const response = await callRegistryAction(runtime, 'DescribeRegistryRecord', payload, {
        signal: exec.signal,
      })
      return normalizeDescribeResult(registryId, response)
    },
    presentCall: args => ({
      card: 'generic',
      title: `Resolve Registry record ${args.record_id}`,
      kind: 'read',
      rawInput: args,
    }),
  }))
}
