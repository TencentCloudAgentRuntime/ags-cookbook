import assert from 'node:assert/strict';
import { test } from 'node:test';
import { TaskState } from '@a2a-js/sdk';
import { RegistryA2AClient, normalizeA2AResult } from '../src/a2a-client.mjs';
import { HANDOFF_SCHEMA_VERSION } from '../src/handoff.mjs';

const handoff = {
  schemaVersion: HANDOFF_SCHEMA_VERSION,
  role: 'reviewer',
  outcome: 'BLOCKED',
  summary: '缺少测试证据',
  decisions: [],
  blockingIssues: [],
  evidence: [],
  nextRecommendedCapability: 'implement-code-change',
};

function task(state = TaskState.TASK_STATE_COMPLETED) {
  return {
    id: 'task-1',
    contextId: 'context-1',
    status: { state, message: undefined },
    artifacts: [{
      artifactId: 'artifact-1',
      name: 'reviewer-handoff.md',
      description: 'review result',
      parts: [
        { content: { $case: 'text', value: '# Review\nBlocked' }, mediaType: 'text/markdown' },
        { content: { $case: 'data', value: handoff }, mediaType: 'application/json' },
      ],
      metadata: {},
    }],
  };
}

test('normalizeA2AResult keeps structured handoff and hides large text by default', () => {
  const result = normalizeA2AResult(task(), { recordId: 'rec-1', versionId: 'rv-1' });
  assert.equal(result.state, 'TASK_STATE_COMPLETED');
  assert.deepEqual(result.handoff, handoff);
  assert.equal(result.artifacts[0].parts[0].content, undefined);
  assert.deepEqual(result.artifacts[0].parts[1].content, handoff);
});

test('RegistryA2AClient resolves the immutable registry version before invocation', async () => {
  let sentRequest;
  const registryCall = async (_config, action, payload) => {
    assert.equal(action, 'DescribeRegistryRecord');
    assert.equal(payload.RegistryId, 'reg-selected');
    assert.equal(payload.RecordId, 'rec-1');
    assert.equal(payload.VersionId, 'rv-1');
    return {
      RequestId: 'request-1',
      Record: { Name: 'reviewer', DescriptorType: 'A2A' },
      Version: {
        VersionId: 'rv-1',
        Revision: 3,
        Descriptors: JSON.stringify({
          name: 'reviewer',
          supportedInterfaces: [{ url: 'http://127.0.0.1:18080/agents/reviewer/a2a', protocolBinding: 'JSONRPC', protocolVersion: '1.0' }],
          capabilities: {},
          defaultInputModes: ['text/plain'],
          defaultOutputModes: ['application/json'],
          skills: [],
          version: '1.0.0',
        }),
      },
    };
  };
  const clientFactory = {
    async createFromAgentCard(card) {
      assert.equal(card.name, 'reviewer');
      return {
        async sendMessage(request) {
          sentRequest = request;
          return task();
        },
      };
    },
  };
  const client = new RegistryA2AClient({
    registryConfig: { registryId: 'reg-default-must-not-be-used' },
    registryCall,
    clientFactory,
  });
  const result = await client.sendMessage({
    registryId: 'reg-selected',
    recordId: 'rec-1',
    versionId: 'rv-1',
    message: 'review this change',
    referenceTaskIds: ['task-upstream'],
  });
  assert.equal(sentRequest.configuration.returnImmediately, true);
  assert.deepEqual(sentRequest.message.referenceTaskIds, ['task-upstream']);
  assert.equal(sentRequest.message.metadata.registryId, 'reg-selected');
  assert.equal(result.target.registryId, 'reg-selected');
  assert.equal(result.target.requestId, 'request-1');
  assert.equal(result.target.revision, 3);
  assert.equal(result.handoff.outcome, 'BLOCKED');
});
