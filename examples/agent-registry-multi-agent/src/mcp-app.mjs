import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { StreamableHTTPServerTransport } from '@modelcontextprotocol/sdk/server/streamableHttp.js';
import { createMcpExpressApp } from '@modelcontextprotocol/sdk/server/express.js';
import * as z from 'zod/v4';
import { A2A_MCP_RECORD_NAME, A2A_MCP_VERSION } from './mcp-descriptor.mjs';

const targetSchema = {
  registry_id: z.string().min(1).describe('RegistryId returned by Agent Registry discovery for the selected record.'),
  record_id: z.string().min(1).describe('A2A RecordId selected through Agent Registry discovery.'),
  version_id: z.string().min(1).describe('Immutable VersionId returned by Registry describe; labels are not accepted.'),
};

function toolResult(value) {
  return {
    content: [{ type: 'text', text: JSON.stringify(value, null, 2) }],
    structuredContent: value,
  };
}

function toolError(error) {
  const value = {
    error: error.message,
    ...(error.code ? { code: error.code } : {}),
    ...(error.requestId ? { requestId: error.requestId } : {}),
  };
  return {
    isError: true,
    content: [{ type: 'text', text: JSON.stringify(value, null, 2) }],
  };
}

function createServer(a2aClient) {
  const server = new McpServer({ name: A2A_MCP_RECORD_NAME, version: A2A_MCP_VERSION });

  server.registerTool('a2a_send_message', {
    description: 'Invoke one immutable A2A Agent Registry version. Use registry_id, record_id, and version_id returned by Registry '
      + 'describe; never invent an endpoint or encode JSON-RPC yourself. By default the call returns immediately with '
      + 'a Task handle, so call a2a_get_task until the state is terminal. The tool performs protocol conversion and '
      + 'transport only; the calling model remains responsible for agent selection and next-step decisions.',
    inputSchema: {
      ...targetSchema,
      message: z.string().min(1).describe('Semantic task input for the selected agent.'),
      reference_task_ids: z.array(z.string().min(1)).optional()
        .describe('Optional upstream A2A Task IDs that establish collaboration lineage.'),
      context_id: z.string().min(1).optional().describe('Optional existing A2A context identifier.'),
      task_id: z.string().min(1).optional().describe('Optional existing task for a follow-up message.'),
      return_immediately: z.boolean().default(true)
        .describe('Return a working Task handle immediately when supported; set false only for a bounded short task.'),
      include_artifact_content: z.boolean().default(false)
        .describe('Include human-readable artifact text. Structured handoff data is always returned when available.'),
    },
  }, async (args) => {
    try {
      return toolResult(await a2aClient.sendMessage({
        registryId: args.registry_id,
        recordId: args.record_id,
        versionId: args.version_id,
        message: args.message,
        referenceTaskIds: args.reference_task_ids,
        contextId: args.context_id,
        taskId: args.task_id,
        returnImmediately: args.return_immediately,
        includeArtifactContent: args.include_artifact_content,
      }));
    } catch (error) {
      return toolError(error);
    }
  });

  server.registerTool('a2a_get_task', {
    description: 'Read the latest state and structured handoff of an asynchronous A2A Task. Reuse the exact RegistryId, '
      + 'RecordId, and immutable VersionId used to start the Task. A protocol-level COMPLETED state does not imply that the '
      + 'agent business outcome passed; inspect handoff.outcome separately.',
    inputSchema: {
      ...targetSchema,
      task_id: z.string().min(1).describe('Server-generated A2A Task ID.'),
      include_artifact_content: z.boolean().default(false)
        .describe('Include human-readable artifact text. Structured handoff data is always returned when available.'),
    },
  }, async (args) => {
    try {
      return toolResult(await a2aClient.getTask({
        registryId: args.registry_id,
        recordId: args.record_id,
        versionId: args.version_id,
        taskId: args.task_id,
        includeArtifactContent: args.include_artifact_content,
      }));
    } catch (error) {
      return toolError(error);
    }
  });

  server.registerTool('a2a_cancel_task', {
    description: 'Request cancellation of an A2A Task using the same immutable Registry target used to start it.',
    inputSchema: {
      ...targetSchema,
      task_id: z.string().min(1).describe('Server-generated A2A Task ID.'),
    },
  }, async (args) => {
    try {
      return toolResult(await a2aClient.cancelTask({
        registryId: args.registry_id,
        recordId: args.record_id,
        versionId: args.version_id,
        taskId: args.task_id,
      }));
    } catch (error) {
      return toolError(error);
    }
  });

  return server;
}

export function createA2AMcpApp({ a2aClient }) {
  const app = createMcpExpressApp();
  app.get('/health', (_request, response) => {
    response.json({ status: 'ok', name: A2A_MCP_RECORD_NAME, version: A2A_MCP_VERSION });
  });
  app.post('/mcp', async (request, response) => {
    const server = createServer(a2aClient);
    const transport = new StreamableHTTPServerTransport({ sessionIdGenerator: undefined });
    response.on('close', () => {
      void transport.close();
      void server.close();
    });
    try {
      await server.connect(transport);
      await transport.handleRequest(request, response, request.body);
    } catch (error) {
      if (!response.headersSent) {
        response.status(500).json({
          jsonrpc: '2.0',
          error: { code: -32603, message: error.message },
          id: null,
        });
      }
    }
  });
  app.get('/mcp', (_request, response) => response.status(405).json({
    jsonrpc: '2.0', error: { code: -32000, message: 'Method not allowed.' }, id: null,
  }));
  app.delete('/mcp', (_request, response) => response.status(405).json({
    jsonrpc: '2.0', error: { code: -32000, message: 'Method not allowed.' }, id: null,
  }));
  return app;
}
