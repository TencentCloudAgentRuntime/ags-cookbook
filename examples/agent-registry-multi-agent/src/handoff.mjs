export const HANDOFF_SCHEMA_VERSION = 'demo.delivery.handoff/v1';

export const CAPABILITY_IDS = Object.freeze({
  requirements: 'analyze-requirement-and-design-solution',
  developer: 'implement-code-change',
  reviewer: 'review-code-change',
  tester: 'plan-and-assess-testing',
  release: 'prepare-release-and-acceptance',
});

const KNOWN_CAPABILITY_IDS = new Set(Object.values(CAPABILITY_IDS));

const NEXT_CAPABILITY_GUIDANCE = Object.freeze({
  requirements: `READY 时使用 "${CAPABILITY_IDS.developer}"；存在关键缺口时使用 null。`,
  developer: `READY 时使用 "${CAPABILITY_IDS.reviewer}"；无法实现时使用 null。`,
  reviewer: `PASSED 时使用 "${CAPABILITY_IDS.tester}"；BLOCKED 时使用 "${CAPABILITY_IDS.developer}"。`,
  tester: `PASSED 时使用 "${CAPABILITY_IDS.release}"；不通过或证据不足时使用 "${CAPABILITY_IDS.developer}"。`,
  release: '始终使用 null；发布或交付结论已经是本次协作的最终能力。',
});

const OUTCOMES = new Set([
  'READY',
  'PASSED',
  'BLOCKED',
  'FAILED',
  'INSUFFICIENT_EVIDENCE',
  'NOT_AUTHORIZED',
]);

function requiredString(value, path) {
  if (typeof value !== 'string' || value.trim() === '') {
    throw new Error(`${path} must be a non-empty string`);
  }
  return value.trim();
}

function optionalString(value, path) {
  if (value === null || value === undefined) return null;
  return requiredString(value, path);
}

function stringList(value, path) {
  if (!Array.isArray(value) || value.some((item) => typeof item !== 'string')) {
    throw new Error(`${path} must be an array of strings`);
  }
  return value.map((item) => item.trim()).filter(Boolean);
}

function issueList(value) {
  if (!Array.isArray(value)) throw new Error('handoff.blockingIssues must be an array');
  return value.map((issue, index) => {
    if (issue === null || typeof issue !== 'object' || Array.isArray(issue)) {
      throw new Error(`handoff.blockingIssues[${index}] must be an object`);
    }
    return {
      id: requiredString(issue.id, `handoff.blockingIssues[${index}].id`),
      summary: requiredString(issue.summary, `handoff.blockingIssues[${index}].summary`),
      evidence: optionalString(issue.evidence, `handoff.blockingIssues[${index}].evidence`),
      recommendation: optionalString(
        issue.recommendation,
        `handoff.blockingIssues[${index}].recommendation`,
      ),
    };
  });
}

function evidenceList(value) {
  if (!Array.isArray(value)) throw new Error('handoff.evidence must be an array');
  return value.map((evidence, index) => {
    if (evidence === null || typeof evidence !== 'object' || Array.isArray(evidence)) {
      throw new Error(`handoff.evidence[${index}] must be an object`);
    }
    return {
      kind: requiredString(evidence.kind, `handoff.evidence[${index}].kind`),
      summary: requiredString(evidence.summary, `handoff.evidence[${index}].summary`),
      uri: optionalString(evidence.uri, `handoff.evidence[${index}].uri`),
    };
  });
}

function parseJSONObject(raw) {
  const text = requiredString(raw, 'model output');
  const fenced = text.match(/^```(?:json)?\s*([\s\S]*?)\s*```$/i);
  const candidate = fenced ? fenced[1] : text;
  let value;
  try {
    value = JSON.parse(candidate);
  } catch (error) {
    throw new Error(`model output must be one JSON object: ${error.message}`);
  }
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('model output must be one JSON object');
  }
  return value;
}

export function parseHandoffResult(role, raw) {
  const value = parseJSONObject(raw);
  const reportMarkdown = requiredString(value.reportMarkdown, 'reportMarkdown');
  const handoff = value.handoff;
  if (handoff === null || typeof handoff !== 'object' || Array.isArray(handoff)) {
    throw new Error('handoff must be an object');
  }
  if (handoff.schemaVersion !== HANDOFF_SCHEMA_VERSION) {
    throw new Error(`handoff.schemaVersion must be ${HANDOFF_SCHEMA_VERSION}`);
  }
  if (handoff.role !== role) throw new Error(`handoff.role must be ${role}`);
  const outcome = requiredString(handoff.outcome, 'handoff.outcome').toUpperCase();
  if (!OUTCOMES.has(outcome)) throw new Error(`unsupported handoff.outcome: ${outcome}`);

  const nextRecommendedCapability = optionalString(
    handoff.nextRecommendedCapability,
    'handoff.nextRecommendedCapability',
  );
  if (nextRecommendedCapability !== null && !KNOWN_CAPABILITY_IDS.has(nextRecommendedCapability)) {
    throw new Error(`unsupported handoff.nextRecommendedCapability: ${nextRecommendedCapability}`);
  }

  return {
    reportMarkdown,
    handoff: {
      schemaVersion: HANDOFF_SCHEMA_VERSION,
      role,
      outcome,
      summary: requiredString(handoff.summary, 'handoff.summary'),
      decisions: stringList(handoff.decisions, 'handoff.decisions'),
      blockingIssues: issueList(handoff.blockingIssues),
      evidence: evidenceList(handoff.evidence),
      nextRecommendedCapability,
    },
  };
}

export function handoffContractPrompt(role) {
  const nextCapabilityGuidance = NEXT_CAPABILITY_GUIDANCE[role];
  if (nextCapabilityGuidance === undefined) throw new Error(`unsupported handoff role: ${role}`);
  return `

交付协议：只输出一个合法 JSON 对象，不要输出 JSON 之外的文字或代码围栏。结构必须为：
{
  "reportMarkdown": "给人阅读的完整中文 Markdown 报告",
  "handoff": {
    "schemaVersion": "${HANDOFF_SCHEMA_VERSION}",
    "role": "${role}",
    "outcome": "READY|PASSED|BLOCKED|FAILED|INSUFFICIENT_EVIDENCE|NOT_AUTHORIZED",
    "summary": "供其他 Agent 快速理解的简洁摘要",
    "decisions": ["已经确认的决定"],
    "blockingIssues": [
      {"id": "B1", "summary": "阻塞问题", "evidence": "证据或 null", "recommendation": "建议或 null"}
    ],
    "evidence": [
      {"kind": "artifact|test|review|deployment|assumption", "summary": "证据摘要", "uri": "可访问引用或 null"}
    ],
    "nextRecommendedCapability": "下一能力的精确 Skill ID，或 null"
  }
}
nextRecommendedCapability 规则：${nextCapabilityGuidance}
不要使用角色简称、自然语言或未列出的能力标识。
不要把 A2A 的 TASK_STATE 当作业务结论；即使任务正常完成，业务 outcome 仍可为 BLOCKED 或 INSUFFICIENT_EVIDENCE。`;
}
