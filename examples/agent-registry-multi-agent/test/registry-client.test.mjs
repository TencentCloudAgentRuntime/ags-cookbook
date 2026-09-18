import assert from 'node:assert/strict';
import test from 'node:test';
import { callRegistryAction } from '../src/registry-client.mjs';

const config = {
  endpoint: 'https://registry.example.com',
  region: 'ap-test',
  secretId: 'test-id',
  secretKey: 'test-key',
};

test('callRegistryAction retries transient InternalError responses', async () => {
  let calls = 0;
  const fetchImpl = async () => {
    calls += 1;
    if (calls === 1) {
      return new Response(JSON.stringify({
        Response: { Error: { Code: 'InternalError', Message: 'retry me' } },
      }), { status: 200 });
    }
    return new Response(JSON.stringify({ Response: { RecordSet: [] } }), { status: 200 });
  };

  const response = await callRegistryAction(
    config,
    'DescribeRegistryRecordList',
    {},
    { fetchImpl, retryDelayMs: 0 },
  );

  assert.equal(calls, 2);
  assert.deepEqual(response.RecordSet, []);
});

test('callRegistryAction does not retry validation errors', async () => {
  let calls = 0;
  const fetchImpl = async () => {
    calls += 1;
    return new Response(JSON.stringify({
      Response: { Error: { Code: 'InvalidParameter', Message: 'bad input' } },
    }), { status: 200 });
  };

  await assert.rejects(
    callRegistryAction(config, 'DescribeRegistryRecord', {}, { fetchImpl, retryDelayMs: 0 }),
    /InvalidParameter/,
  );
  assert.equal(calls, 1);
});
