import 'dotenv/config';
import { ags } from 'tencentcloud-sdk-nodejs-ags';

const AgsClient = ags.v20250920.Client;

const VALID_REGISTRY_TYPES = ['personal', 'enterprise'] as const;

function requireEnv(name: string): string {
  const val = process.env[name];
  if (!val) throw new Error(`Missing required environment variable: ${name}`);
  return val;
}

async function main() {
  const secretId = requireEnv('TENCENTCLOUD_SECRET_ID');
  const secretKey = requireEnv('TENCENTCLOUD_SECRET_KEY');
  const region = process.env.TENCENTCLOUD_REGION || 'ap-guangzhou';
  const toolName = requireEnv('TOOL_NAME');
  const dockerRegistry = process.env.DOCKER_REGISTRY;
  const appName = process.env.APP_NAME || 'sandbox-hermes';
  const imageAddress = process.env.IMAGE_ADDRESS
    || (dockerRegistry ? `${dockerRegistry}/${appName}:latest` : '');
  if (!imageAddress) throw new Error('Missing IMAGE_ADDRESS or DOCKER_REGISTRY in .env');
  const imageRegistryType = process.env.IMAGE_REGISTRY_TYPE || 'personal';
  const cfsFileSystemId = requireEnv('CFS_FILE_SYSTEM_ID');
  const cfsPath = process.env.CFS_PATH || '/';
  const roleArn = requireEnv('ROLE_ARN');
  const mountName = process.env.MOUNT_NAME || 'cfs';

  if (!(VALID_REGISTRY_TYPES as readonly string[]).includes(imageRegistryType)) {
    throw new Error(`IMAGE_REGISTRY_TYPE must be 'personal' or 'enterprise', got: '${imageRegistryType}'`);
  }

  const client = new AgsClient({
    credential: { secretId, secretKey },
    region,
  });

  console.log(`Creating sandbox tool "${toolName}" in ${region}...`);
  console.log(`   Image: ${imageAddress} (${imageRegistryType})`);
  console.log(`   CFS:   ${cfsFileSystemId}:${cfsPath} -> /opt/data`);

  const resp = await client.CreateSandboxTool({
    ToolName: toolName,
    ToolType: 'custom',
    RoleArn: roleArn,
    NetworkConfiguration: { NetworkMode: 'PUBLIC' },
    CustomConfiguration: {
      Image: imageAddress,
      ImageRegistryType: imageRegistryType,
      Command: ['/entrypoint.sh'],
      Args: [],
      Env: [
        { Name: 'PYTHONUNBUFFERED', Value: '1' },
        { Name: 'HERMES_WEB_DIST', Value: '/opt/hermes/hermes_cli/web_dist' },
        { Name: 'PLAYWRIGHT_BROWSERS_PATH', Value: '/opt/hermes/.playwright' },
        { Name: 'TERM', Value: 'xterm' },
        { Name: 'SHLVL', Value: '1' },
        { Name: 'HERMES_HOME', Value: '/opt/data' },
        { Name: 'PATH', Value: '/opt/data/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin' },
        { Name: 'GATEWAY_ALLOW_ALL_USERS', Value: 'true' },
      ],
      Ports: [
        { Name: 'dashboard', Port: 9119, Protocol: 'TCP' },
        { Name: 'gateway', Port: 8642, Protocol: 'TCP' },
        { Name: 'envd', Port: 49983, Protocol: 'TCP' },
      ],
      Resources: { CPU: '4', Memory: '8Gi' },
      Probe: {
        HttpGet: { Path: '/health', Port: 49983, Scheme: 'HTTP' },
        ReadyTimeoutMs: 30000,
        ProbeTimeoutMs: 1000,
        ProbePeriodMs: 3000,
        SuccessThreshold: 1,
        FailureThreshold: 100,
      },
    },
    StorageMounts: [
      {
        Name: mountName,
        MountPath: '/opt/data',
        StorageSource: {
          Cfs: {
            FileSystemId: cfsFileSystemId,
            Path: cfsPath,
          },
        },
      },
    ],
  });

  console.log(`Sandbox tool created successfully!`);
  console.log(`   Tool ID:   ${resp.ToolId ?? '(check AGS console)'}`);
  console.log(`   Tool Name: ${toolName}`);
  console.log(`   Mount:     ${mountName} (CFS ${cfsFileSystemId}) -> /opt/data`);
}

main().catch((err) => {
  if (err.code?.startsWith('ResourceInUse') || err.message?.includes('already exists')) {
    console.error(`Tool "${process.env.TOOL_NAME}" already exists. Delete it first or use a different TOOL_NAME.`);
  } else {
    console.error('Failed to create sandbox tool:', err);
  }
  process.exit(1);
});
