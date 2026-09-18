function required(value, name) {
  if (typeof value !== 'string' || value.trim() === '') {
    throw new Error(`${name} is required`);
  }
  return value.trim();
}

function optional(value) {
  return typeof value === 'string' && value.trim() !== '' ? value.trim() : undefined;
}

export function registryConfigFromEnv(env = process.env) {
  return {
    endpoint: optional(env.AGENT_REGISTRY_ENDPOINT) || 'https://registry.tencentcloudapi.com/',
    service: 'ags',
    version: '2025-09-20',
    region: required(env.TENCENTCLOUD_REGION, 'TENCENTCLOUD_REGION'),
    registryId: required(env.AGENT_REGISTRY_ID, 'AGENT_REGISTRY_ID'),
    secretId: required(env.TENCENTCLOUD_SECRET_ID, 'TENCENTCLOUD_SECRET_ID'),
    secretKey: required(env.TENCENTCLOUD_SECRET_KEY, 'TENCENTCLOUD_SECRET_KEY'),
    token: optional(env.TENCENTCLOUD_TOKEN),
  };
}

export function recordPrefixFromEnv(env = process.env) {
  return optional(env.DEMO_RECORD_PREFIX) || 'demo-rd';
}

export function recordNameForRole(role, env = process.env) {
  return `${recordPrefixFromEnv(env)}-${role.slug}-agent`;
}
