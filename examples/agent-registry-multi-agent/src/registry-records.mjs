import { callRegistryAction } from './registry-client.mjs';

export function parseDescriptors(value) {
  if (value !== null && typeof value === 'object' && !Array.isArray(value)) return value;
  return JSON.parse(value);
}

function canonical(value) {
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`;
  if (value !== null && typeof value === 'object') {
    const entries = Object.keys(value).sort()
      .map((key) => `${JSON.stringify(key)}:${canonical(value[key])}`);
    return `{${entries.join(',')}}`;
  }
  return JSON.stringify(value);
}

export function sameDescriptor(left, right) {
  try {
    return canonical(parseDescriptors(left)) === canonical(parseDescriptors(right));
  } catch {
    return false;
  }
}

export async function listAllRegistryRecords(config, options = {}) {
  const registryCall = options.registryCall ?? callRegistryAction;
  const limit = options.limit ?? 100;
  const records = [];
  let offset = 0;
  while (true) {
    const response = await registryCall(config, 'DescribeRegistryRecordList', {
      RegistryId: config.registryId,
      Offset: offset,
      Limit: limit,
      ...(options.filters ? { Filters: options.filters } : {}),
    });
    const page = response.RecordSet ?? [];
    records.push(...page);
    offset += page.length;
    if (page.length === 0 || page.length < limit || offset >= (response.TotalCount ?? offset)) break;
  }
  return records;
}

export async function syncRecordDescription(config, record, description, options = {}) {
  if (record.Description === description) return false;
  const registryCall = options.registryCall ?? callRegistryAction;
  try {
    await registryCall(config, 'UpdateRegistryRecord', {
      RegistryId: config.registryId,
      RecordId: record.RecordId,
      Description: description,
    });
  } catch (error) {
    if (error.code !== 'InternalError') throw error;
  }

  const refreshed = await listAllRegistryRecords(config, {
    registryCall,
    filters: [{ Name: 'name', Values: [record.Name] }],
  });
  const committed = refreshed.find((candidate) => candidate.RecordId === record.RecordId);
  if (committed?.Description !== description) {
    throw new Error(`record description was not committed: ${record.Name}`);
  }
  return true;
}
