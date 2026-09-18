import 'dotenv/config';
import { ClientFactory } from '@a2a-js/sdk/client';
import { Role, taskStateToJSON } from '@a2a-js/sdk';
import { ROLE_DEFINITIONS } from '../src/roles.mjs';

const baseURL = process.env.DEMO_PUBLIC_BASE_URL || 'http://127.0.0.1:18080';
const prompt = process.argv.slice(2).join(' ').trim()
  || '我们要为内部订单服务新增 /healthz 接口，请给出本角色的交付产物。';
const only = process.env.DEMO_AGENT;
const roles = only ? ROLE_DEFINITIONS.filter((role) => role.slug === only) : ROLE_DEFINITIONS;
if (roles.length === 0) throw new Error(`unknown DEMO_AGENT: ${only}`);

for (const role of roles) {
  const client = await new ClientFactory().createFromUrl(
    baseURL,
    `/agents/${role.slug}/.well-known/agent-card.json`,
  );
  const result = await client.sendMessage({
    message: {
      messageId: crypto.randomUUID(),
      contextId: '',
      taskId: '',
      role: Role.ROLE_USER,
      parts: [{
        content: { $case: 'text', value: prompt },
        metadata: undefined,
        filename: '',
        mediaType: 'text/plain',
      }],
      metadata: { demo: 'multi-agent-delivery' },
      extensions: [],
      referenceTaskIds: [],
    },
  });
  const artifact = result.artifacts?.[0];
  const text = artifact?.parts?.find((part) => part.content?.$case === 'text')?.content?.value;
  const state = taskStateToJSON(result.status?.state);
  const failure = result.status?.message?.parts
    ?.find((part) => part.content?.$case === 'text')?.content?.value;
  console.log(`\n=== ${role.name} (${state}) ===`);
  console.log(text || failure || '(no text artifact)');
  if (state !== 'TASK_STATE_COMPLETED') process.exitCode = 1;
}
