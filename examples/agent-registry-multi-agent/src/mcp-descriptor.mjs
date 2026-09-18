export const A2A_MCP_RECORD_NAME = 'demo.local/a2a-client';
export const A2A_MCP_VERSION = '0.2.0';
export const MCP_SCHEMA_URI = 'https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json';

export function buildA2AMcpDescriptor(baseURL) {
  const url = new URL(baseURL);
  url.pathname = `${url.pathname.replace(/\/$/, '')}/mcp`;
  url.search = '';
  url.hash = '';
  return {
    $schema: MCP_SCHEMA_URI,
    name: A2A_MCP_RECORD_NAME,
    title: 'Agent Registry A2A Client',
    description: 'Resolve an immutable A2A Agent Registry version and invoke it through normalized MCP tools.',
    version: A2A_MCP_VERSION,
    remotes: [{ type: 'streamable-http', url: url.toString() }],
  };
}
