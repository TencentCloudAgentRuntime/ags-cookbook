import 'dotenv/config';
import { ags } from 'tencentcloud-sdk-nodejs-ags';

const AgsClient = ags.v20250920.Client;

const STARTUP_SCRIPT = [
  "/usr/bin/envd > /tmp/envd.log 2>&1 &",
  "while true; do",
  "su -s /bin/bash node -c 'OPENCLAW_HOME=/openclaw node /app/openclaw.mjs gateway --port 8080 --bind lan --allow-unconfigured';",
  "echo '[restart] openclaw exited ($?), restarting in 1s...';",
  "sleep 1;",
  "done",
].join(' ');

const VALID_REGISTRY_TYPES = ['personal', 'enterprise'] as const;

function requireEnv(name: string): string {
  const val = process.env[name];
  if (!val) throw new Error(`Missing required environment variable: ${name}`);
  return val;
}

async function main() {
  const secretId = requireEnv('TENCENTCLOUD_SECRET_ID');
  const secretKey = requireEnv('TENCENTCLOUD_SECRET_KEY');
  const region = process.env.TENCENTCLOUD_REGION || 'ap-shanghai';
  const toolName = requireEnv('TOOL_NAME');
  const imageAddress = requireEnv('IMAGE_ADDRESS');
  const imageRegistryType = process.env.IMAGE_REGISTRY_TYPE || 'personal';
  const cosEndpoint = requireEnv('COS_ENDPOINT');
  const cosBucketName = requireEnv('COS_BUCKET_NAME');
  const cosBucketPath = process.env.COS_BUCKET_PATH || '/';
  const roleArn = requireEnv('ROLE_ARN');
  // MOUNT_NAME defaults to 'cos' here because CreateSandboxTool always needs
  // a StorageMount name. This is distinct from the server.ts use case where
  // omitting MOUNT_NAME skips MountOptions entirely at instance start time.
  const mountName = process.env.MOUNT_NAME || 'cos';

  if (!(VALID_REGISTRY_TYPES as readonly string[]).includes(imageRegistryType)) {
    throw new Error(`IMAGE_REGISTRY_TYPE must be 'personal' or 'enterprise', got: '${imageRegistryType}'`);
  }
  if (!cosBucketPath.startsWith('/')) {
    throw new Error(`COS_BUCKET_PATH must start with '/', got: '${cosBucketPath}'`);
  }

  const client = new AgsClient({
    credential: { secretId, secretKey },
    region,
  });

  console.log(`🔧 Creating sandbox tool "${toolName}" in ${region}...`);
  console.log(`   Image: ${imageAddress} (${imageRegistryType})`);
  console.log(`   COS:   ${cosBucketName}${cosBucketPath} → /openclaw`);

  const resp = await client.CreateSandboxTool({
    ToolName: toolName,
    ToolType: 'custom',
    RoleArn: roleArn,
    NetworkConfiguration: { NetworkMode: 'PUBLIC' },
    CustomConfiguration: {
      Image: imageAddress,
      ImageRegistryType: imageRegistryType,
      Command: ['/bin/bash'],
      Args: ['-l', '-c', STARTUP_SCRIPT],
      Resources: { CPU: '4000m', Memory: '8Gi' },
      Probe: {
        // Port 49983 is the AGS envd daemon, not OpenClaw. envd exposes
        // /health for sandbox readiness probing; OpenClaw runs on 8080.
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
        MountPath: '/openclaw',
        StorageSource: {
          Cos: {
            Endpoint: cosEndpoint,
            BucketName: cosBucketName,
            BucketPath: cosBucketPath,
          },
        },
      },
    ],
  });

  console.log(`✅ Sandbox tool created successfully!`);
  console.log(`   Tool ID:   ${resp.ToolId ?? '(check AGS console)'}`);
  console.log(`   Tool Name: ${toolName}`);
  console.log(`   Mount:     ${mountName} → /openclaw`);
}

main().catch((err) => {
  if (err.code?.startsWith('ResourceInUse') || err.message?.includes('already exists')) {
    console.error(`❌ Tool "${process.env.TOOL_NAME}" already exists. Delete it first or use a different TOOL_NAME.`);
  } else {
    console.error('❌ Failed to create sandbox tool:', err);
  }
  process.exit(1);
});
