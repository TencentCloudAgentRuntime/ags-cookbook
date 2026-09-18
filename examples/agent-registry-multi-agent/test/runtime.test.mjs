import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { createApp } from '../src/app.mjs';
import { buildAgentCard } from '../src/a2a-runtime.mjs';
import { CAPABILITY_IDS, HANDOFF_SCHEMA_VERSION, parseHandoffResult } from '../src/handoff.mjs';
import { ROLE_DEFINITIONS } from '../src/roles.mjs';

const advertisedBaseURL = 'http://127.0.0.1:18081';
let baseURL;
const completionClient = {
  model: 'test/deepseek-v4-pro',
  async complete({ systemPrompt, userPrompt }) {
    assert.match(systemPrompt, /Agent/);
    return JSON.stringify({
      reportMarkdown: `# 需求结论\n\n已处理：${userPrompt}`,
      handoff: {
        schemaVersion: HANDOFF_SCHEMA_VERSION,
        role: 'requirements',
        outcome: 'READY',
        summary: '需求已结构化，可以交给代码开发能力。',
        decisions: ['健康检查只表达进程存活'],
        blockingIssues: [],
        evidence: [{ kind: 'assumption', summary: '测试桩生成的需求证据', uri: null }],
        nextRecommendedCapability: CAPABILITY_IDS.developer,
      },
    });
  },
};

let server;

before(async () => {
  const { app } = createApp({ baseURL: advertisedBaseURL, completionClient });
  await new Promise((resolve, reject) => {
    server = app.listen(0, '127.0.0.1', (error) => error ? reject(error) : resolve());
  });
  baseURL = `http://127.0.0.1:${server.address().port}`;
});

after(async () => {
  await new Promise((resolve) => server.close(resolve));
});

test('all role cards satisfy the Registry A2A 1.0 shape', () => {
  assert.equal(ROLE_DEFINITIONS.length, 5);
  for (const role of ROLE_DEFINITIONS) {
    const card = buildAgentCard(role, advertisedBaseURL);
    assert.equal(card.supportedInterfaces[0].protocolBinding, 'JSONRPC');
    assert.equal(card.supportedInterfaces[0].protocolVersion, '1.0');
    assert.deepEqual(card.defaultInputModes, ['text/plain']);
    assert.deepEqual(card.defaultOutputModes, ['text/markdown', 'application/json']);
    assert.equal(card.skills.length, 1);
    assert.equal(card.version, '0.3.0');
  }
  assert.equal(buildAgentCard(
    ROLE_DEFINITIONS.find((role) => role.slug === 'developer'),
    advertisedBaseURL,
  ).version, '0.3.0');
});

test('role cards expose a complete capability handoff chain without a central workflow', () => {
  const bySlug = Object.fromEntries(ROLE_DEFINITIONS.map((role) => [role.slug, role]));
  assert.match(bySlug.requirements.description, /任何需要把新想法、功能开发或行为变更/);
  assert.match(bySlug.developer.description, /review-code-change/);
  assert.match(bySlug.reviewer.description, /不可互相替代/);
  assert.match(bySlug.tester.description, /prepare-release-and-acceptance/);
  assert.match(bySlug.release.description, /本地单文件页面/);
});

test('health lists five independently addressable agents', async () => {
  const response = await fetch(`${baseURL}/health`);
  assert.equal(response.status, 200);
  const body = await response.json();
  assert.equal(body.status, 'ok');
  assert.equal(body.agentCount, 5);
  assert.equal(body.model, completionClient.model);
});

test('A2A SendMessage returns a completed task with a role artifact', async () => {
  const response = await fetch(`${baseURL}/agents/requirements/a2a`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'A2A-Version': '1.0',
    },
    body: JSON.stringify({
      jsonrpc: '2.0',
      id: 'test-1',
      method: 'SendMessage',
      params: {
        message: {
          messageId: 'message-1',
          role: 'ROLE_USER',
          parts: [{ text: '设计健康检查需求', mediaType: 'text/plain' }],
        },
      },
    }),
  });
  assert.equal(response.status, 200);
  const body = await response.json();
  assert.equal(body.result.task.status.state, 'TASK_STATE_COMPLETED');
  assert.equal(body.result.task.artifacts.length, 1);
  assert.match(body.result.task.artifacts[0].parts[0].text, /设计健康检查需求/);
  assert.equal(body.result.task.artifacts[0].parts[0].mediaType, 'text/markdown');
  assert.equal(body.result.task.artifacts[1], undefined);
  assert.equal(body.result.task.artifacts[0].parts[1].mediaType, 'application/json');
  assert.equal(body.result.task.artifacts[0].parts[1].data.schemaVersion, HANDOFF_SCHEMA_VERSION);
  assert.equal(body.result.task.artifacts[0].parts[1].data.role, 'requirements');
  assert.equal(body.result.task.artifacts[0].parts[1].data.outcome, 'READY');
});

test('A2A CancelTask aborts the active model request and returns CANCELED promptly', async () => {
  let markStarted;
  let aborted = false;
  const started = new Promise((resolve) => { markStarted = resolve; });
  const abortableCompletionClient = {
    model: 'test/slow-model',
    async complete({ signal }) {
      markStarted();
      return new Promise((resolve, reject) => {
        const abort = () => {
          aborted = true;
          reject(signal.reason ?? new DOMException('Aborted', 'AbortError'));
        };
        if (signal.aborted) abort();
        else signal.addEventListener('abort', abort, { once: true });
      });
    },
  };
  const { app } = createApp({
    baseURL: advertisedBaseURL,
    completionClient: abortableCompletionClient,
  });
  const cancelServer = await new Promise((resolve, reject) => {
    const listening = app.listen(0, '127.0.0.1', (error) =>
      error ? reject(error) : resolve(listening));
  });
  const cancelBaseURL = `http://127.0.0.1:${cancelServer.address().port}`;
  try {
    const sendResponse = await fetch(`${cancelBaseURL}/agents/requirements/a2a`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'A2A-Version': '1.0' },
      body: JSON.stringify({
        jsonrpc: '2.0',
        id: 'cancel-send',
        method: 'SendMessage',
        params: {
          message: {
            messageId: 'cancel-message',
            role: 'ROLE_USER',
            parts: [{ text: '执行一个慢任务', mediaType: 'text/plain' }],
          },
          configuration: { returnImmediately: true },
        },
      }),
    });
    const sent = await sendResponse.json();
    const taskId = sent.result.task.id;
    await started;

    const startedAt = Date.now();
    const cancelResponse = await fetch(`${cancelBaseURL}/agents/requirements/a2a`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'A2A-Version': '1.0' },
      body: JSON.stringify({
        jsonrpc: '2.0',
        id: 'cancel-task',
        method: 'CancelTask',
        params: { id: taskId },
      }),
    });
    const canceled = await cancelResponse.json();
    assert.equal(cancelResponse.status, 200);
    assert.equal((canceled.result.task ?? canceled.result).status.state, 'TASK_STATE_CANCELED');
    assert.equal(aborted, true);
    assert.ok(Date.now() - startedAt < 1_000, 'cancel should not wait for model timeout');
  } finally {
    await new Promise((resolve) => cancelServer.close(resolve));
  }
});

test('handoff parser rejects free-form model output', () => {
  assert.throws(
    () => parseHandoffResult('requirements', '这是一个 Markdown 报告'),
    /must be one JSON object/,
  );
});

test('handoff parser rejects vague capability aliases', () => {
  assert.throws(
    () => parseHandoffResult('requirements', JSON.stringify({
      reportMarkdown: '# 需求结论\n\n可以开发。',
      handoff: {
        schemaVersion: HANDOFF_SCHEMA_VERSION,
        role: 'requirements',
        outcome: 'READY',
        summary: '可以开发',
        decisions: [],
        blockingIssues: [],
        evidence: [],
        nextRecommendedCapability: 'code-development',
      },
    })),
    /unsupported handoff.nextRecommendedCapability/,
  );
});
