import 'dotenv/config';
import { recordNameForRole, registryConfigFromEnv } from '../src/config.mjs';
import { callRegistryAction } from '../src/registry-client.mjs';
import { listAllRegistryRecords } from '../src/registry-records.mjs';
import { ROLE_DEFINITIONS } from '../src/roles.mjs';

if (process.env.CONFIRM_DELETE !== 'yes') {
  throw new Error('Refusing cleanup. Set CONFIRM_DELETE=yes to delete only this demo\'s five records.');
}

const config = registryConfigFromEnv();
const managedNames = new Set(ROLE_DEFINITIONS.map(role => recordNameForRole(role)));
const records = await listAllRegistryRecords(config);
const targets = records.filter(record => managedNames.has(record.Name));

for (const record of targets) {
  await callRegistryAction(config, 'DeleteRegistryRecord', {
    RegistryId: config.registryId,
    RecordId: record.RecordId,
    Reason: 'Clean up the agent-registry-multi-agent cookbook',
  }, { maxAttempts: 1 });
  console.log(`Deleted ${record.Name} (${record.RecordId})`);
}

console.log(`Cleanup complete: ${targets.length} record(s) deleted.`);
