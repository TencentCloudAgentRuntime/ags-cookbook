import 'dotenv/config';
import { RegistryA2AClient } from './a2a-client.mjs';
import { registryConfigFromEnv } from './config.mjs';
import { createA2AMcpApp } from './mcp-app.mjs';

const registryConfig = registryConfigFromEnv();
const host = process.env.DEMO_MCP_HOST || '127.0.0.1';
const port = Number(process.env.DEMO_MCP_PORT || 18081);
const app = createA2AMcpApp({ a2aClient: new RegistryA2AClient({ registryConfig }) });

app.listen(port, host, (error) => {
  if (error) throw error;
  console.log(`[a2a-client-mcp] ready at http://${host}:${port}/mcp`);
  console.log(`[a2a-client-mcp] registry: ${registryConfig.registryId}`);
});
