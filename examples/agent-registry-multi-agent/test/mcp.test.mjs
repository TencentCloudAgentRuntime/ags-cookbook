import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StreamableHTTPClientTransport } from '@modelcontextprotocol/sdk/client/streamableHttp.js';
import { createA2AMcpApp } from '../src/mcp-app.mjs';

let listener;
let client;
let lastSend;
let lastGet;
let lastCancel;

before(async () => {
  const app = createA2AMcpApp({
    a2aClient: {
      async sendMessage(args) {
        lastSend = args;
        return {
          kind: 'task',
          taskId: 'task-1',
          state: 'TASK_STATE_WORKING',
          handoff: null,
          artifacts: [],
        };
      },
      async getTask(args) {
        lastGet = args;
        return {
          kind: 'task',
          taskId: args.taskId,
          state: 'TASK_STATE_COMPLETED',
          handoff: { outcome: 'READY' },
          artifacts: [],
        };
      },
      async cancelTask(args) {
        lastCancel = args;
        return { kind: 'task', taskId: args.taskId, state: 'TASK_STATE_CANCELED' };
      },
    },
  });
  await new Promise((resolve, reject) => {
    listener = app.listen(0, '127.0.0.1', (error) => error ? reject(error) : resolve());
  });
  const endpoint = new URL(`http://127.0.0.1:${listener.address().port}/mcp`);
  client = new Client({ name: 'demo-test-client', version: '1.0.0' });
  await client.connect(new StreamableHTTPClientTransport(endpoint));
});

after(async () => {
  await client.close();
  await new Promise((resolve) => listener.close(resolve));
});

test('MCP exposes A2A send/get/cancel tools', async () => {
  const listed = await client.listTools();
  assert.deepEqual(
    listed.tools.map((tool) => tool.name).sort(),
    ['a2a_cancel_task', 'a2a_get_task', 'a2a_send_message'],
  );
});

test('a2a_send_message forwards semantic arguments without exposing JSON-RPC', async () => {
  const result = await client.callTool({
    name: 'a2a_send_message',
    arguments: {
      registry_id: 'reg-selected',
      record_id: 'rec-1',
      version_id: 'rv-1',
      message: 'analyze requirement',
    },
  });
  assert.equal(result.isError, undefined);
  assert.equal(result.structuredContent.taskId, 'task-1');
  assert.equal(lastSend.registryId, 'reg-selected');
  assert.equal(lastSend.recordId, 'rec-1');
  assert.equal(lastSend.versionId, 'rv-1');
  assert.equal(lastSend.message, 'analyze requirement');
  assert.equal(lastSend.returnImmediately, true);
});

test('a2a_get_task and a2a_cancel_task preserve the selected RegistryId', async () => {
  const target = {
    registry_id: 'reg-selected',
    record_id: 'rec-1',
    version_id: 'rv-1',
    task_id: 'task-1',
  };
  const getResult = await client.callTool({ name: 'a2a_get_task', arguments: target });
  assert.equal(getResult.isError, undefined);
  assert.equal(lastGet.registryId, 'reg-selected');

  const cancelResult = await client.callTool({ name: 'a2a_cancel_task', arguments: target });
  assert.equal(cancelResult.isError, undefined);
  assert.equal(lastCancel.registryId, 'reg-selected');
});

test('a2a_send_message rejects an ambiguous target without RegistryId', async () => {
  const result = await client.callTool({
    name: 'a2a_send_message',
    arguments: { record_id: 'rec-1', version_id: 'rv-1', message: 'analyze requirement' },
  });
  assert.equal(result.isError, true);
  assert.match(result.content[0].text, /registry_id/);
});
