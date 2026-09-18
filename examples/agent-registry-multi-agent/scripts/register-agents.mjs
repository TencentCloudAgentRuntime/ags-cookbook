import 'dotenv/config';
import { createHash } from 'node:crypto';
import { buildAgentCard } from '../src/a2a-runtime.mjs';
import { recordNameForRole, registryConfigFromEnv } from '../src/config.mjs';
import { callRegistryAction } from '../src/registry-client.mjs';
import { listAllRegistryRecords, sameDescriptor } from '../src/registry-records.mjs';
import { ROLE_DEFINITIONS } from '../src/roles.mjs';

const config = registryConfigFromEnv();
const baseURL = process.env.DEMO_PUBLIC_BASE_URL || 'http://127.0.0.1:18080';

function registryWrite(action, payload) {
  // Do not replay a mutating request after an ambiguous network or service failure.
  // Rerunning this idempotent script first reads the committed state.
  return callRegistryAction(config, action, payload, { maxAttempts: 1 });
}

async function describeRegistry() {
  const response = await callRegistryAction(config, 'DescribeRegistry', {
    RegistryId: config.registryId,
  });
  if (!response.Registry) throw new Error('DescribeRegistry returned no Registry');
  if (response.Registry.Status !== 'ACTIVE') {
    throw new Error(`Registry ${config.registryId} must be ACTIVE`);
  }
  if (response.Registry.ApprovalMode !== 'AUTO') {
    throw new Error(
      `Registry ${config.registryId} uses ${response.Registry.ApprovalMode} approval. `
        + 'Use a dedicated AUTO Registry for this runnable demo, or create and approve the records manually.',
    );
  }
  return response.Registry;
}

async function stableVersion(recordId) {
  const response = await callRegistryAction(config, 'DescribeRegistryRecord', {
    RegistryId: config.registryId,
    RecordId: recordId,
  });
  return response.Version ?? null;
}

async function publishStable(recordId, versionId) {
  await registryWrite('UpdateRegistryRecord', {
    RegistryId: config.registryId,
    RecordId: recordId,
    LabelMutations: [{
      Operation: 'SET',
      Name: 'stable',
      VersionId: versionId,
      Reason: 'Publish the version used by the multi-agent cookbook',
    }],
  });
}

function descriptorVersionName(role, card) {
  const digest = createHash('sha256').update(JSON.stringify(card)).digest('hex').slice(0, 8);
  return `${role.version}-${digest}`;
}

async function matchingApprovedVersion(recordId, card) {
  const versions = [];
  let offset = 0;
  const limit = 100;
  while (true) {
    const response = await callRegistryAction(config, 'DescribeRegistryRecordVersionList', {
      RegistryId: config.registryId,
      RecordId: recordId,
      Offset: offset,
      Limit: limit,
      Filters: [{ Name: 'status', Values: ['APPROVED'] }],
    });
    const page = response.VersionSet ?? [];
    versions.push(...page);
    offset += page.length;
    if (page.length === 0 || page.length < limit || offset >= (response.TotalCount ?? offset)) break;
  }
  return versions.find(version => sameDescriptor(version.Descriptors, card));
}

await describeRegistry();
const existing = await listAllRegistryRecords(config);
const existingByName = new Map(existing.map(record => [record.Name, record]));
const results = [];

for (const role of ROLE_DEFINITIONS) {
  const name = recordNameForRole(role);
  const card = buildAgentCard(role, baseURL);
  const record = existingByName.get(name);

  if (!record) {
    const created = await registryWrite('CreateRegistryRecord', {
      RegistryId: config.registryId,
      Name: name,
      Description: role.description,
      DescriptorType: 'A2A',
      VersionName: role.version,
      AgentSource: { Type: 'MANUAL', Descriptors: JSON.stringify(card) },
    });
    if (!created.RecordId || !created.Version?.VersionId) {
      throw new Error(`CreateRegistryRecord returned an incomplete response for ${name}`);
    }
    const resolved = await stableVersion(created.RecordId);
    if (resolved?.VersionId !== created.Version.VersionId) {
      throw new Error(`AUTO Registry did not bind the created Version to stable for ${name}`);
    }
    results.push({
      role: role.slug,
      name,
      action: 'CREATED',
      recordId: created.RecordId,
      versionId: created.Version.VersionId,
    });
    continue;
  }

  const stable = await stableVersion(record.RecordId);
  if (stable && sameDescriptor(stable.Descriptors, card) && record.Description === role.description) {
    results.push({
      role: role.slug,
      name,
      action: 'UNCHANGED',
      recordId: record.RecordId,
      versionId: stable.VersionId,
    });
    continue;
  }

  if (record.Description !== role.description) {
    await registryWrite('UpdateRegistryRecord', {
      RegistryId: config.registryId,
      RecordId: record.RecordId,
      Description: role.description,
    });
  }

  if (stable && sameDescriptor(stable.Descriptors, card)) {
    results.push({
      role: role.slug,
      name,
      action: 'UPDATED_DESCRIPTION',
      recordId: record.RecordId,
      versionId: stable.VersionId,
    });
    continue;
  }

  const reusable = await matchingApprovedVersion(record.RecordId, card);
  if (reusable) {
    await publishStable(record.RecordId, reusable.VersionId);
    results.push({
      role: role.slug,
      name,
      action: 'REUSED_VERSION_AND_PUBLISHED',
      recordId: record.RecordId,
      versionId: reusable.VersionId,
    });
    continue;
  }

  const updated = await registryWrite('UpdateRegistryRecord', {
    RegistryId: config.registryId,
    RecordId: record.RecordId,
    VersionName: descriptorVersionName(role, card),
    ChangeLog: role.changeLog || 'Refresh the cookbook A2A descriptor',
    AgentSource: { Type: 'MANUAL', Descriptors: JSON.stringify(card) },
  });
  const versionId = updated.Version?.VersionId;
  if (!versionId || updated.Version.Status !== 'APPROVED') {
    throw new Error(`AUTO Registry did not return an approved Version for ${name}`);
  }
  await publishStable(record.RecordId, versionId);
  results.push({
    role: role.slug,
    name,
    action: 'CREATED_VERSION_AND_PUBLISHED',
    recordId: record.RecordId,
    versionId,
  });
}

console.log(JSON.stringify({
  registryId: config.registryId,
  endpoint: config.endpoint,
  publicBaseURL: baseURL,
  agents: results,
}, null, 2));
