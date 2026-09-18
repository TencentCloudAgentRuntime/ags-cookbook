import {
  A2A_PROTOCOL_VERSION,
  AGENT_CARD_PATH,
  Role,
  TaskState,
} from '@a2a-js/sdk';
import {
  AgentEvent,
  DefaultRequestHandler,
  InMemoryTaskStore,
} from '@a2a-js/sdk/server';
import {
  UserBuilder,
  agentCardHandler,
  jsonRpcHandler,
} from '@a2a-js/sdk/server/express';
import { HANDOFF_SCHEMA_VERSION, parseHandoffResult } from './handoff.mjs';

export const AGENT_CARD_VERSION = '0.2.0';

function textPart(text, mediaType = 'text/plain') {
  return {
    content: { $case: 'text', value: text },
    metadata: undefined,
    filename: '',
    mediaType,
  };
}

function dataPart(data) {
  return {
    content: { $case: 'data', value: data },
    metadata: { schemaVersion: HANDOFF_SCHEMA_VERSION },
    filename: 'handoff.json',
    mediaType: 'application/json',
  };
}

export function messageText(message) {
  return message.parts
    .filter((part) => part.content?.$case === 'text')
    .map((part) => part.content.value)
    .join('\n')
    .trim();
}

export function buildAgentCard(role, baseURL) {
  const endpoint = `${baseURL.replace(/\/$/, '')}/agents/${role.slug}/a2a`;
  return {
    name: role.name,
    description: role.description,
    supportedInterfaces: [
      {
        url: endpoint,
        protocolBinding: 'JSONRPC',
        protocolVersion: A2A_PROTOCOL_VERSION,
      },
    ],
    provider: {
      organization: 'Tencent Cloud Agent Runtime Cookbook',
      url: 'https://cloud.tencent.com/product/ags',
    },
    version: role.version ?? AGENT_CARD_VERSION,
    capabilities: {
      streaming: false,
      pushNotifications: false,
      extendedAgentCard: false,
    },
    securitySchemes: {},
    securityRequirements: [],
    defaultInputModes: ['text/plain'],
    defaultOutputModes: ['text/markdown', 'application/json'],
    skills: [
      {
        ...role.skill,
        inputModes: ['text/plain'],
        outputModes: ['text/markdown', 'application/json'],
        securityRequirements: [],
      },
    ],
  };
}

class RoleAgentExecutor {
  constructor(role, completionClient) {
    this.role = role;
    this.completionClient = completionClient;
    this.cancelledTasks = new Set();
    this.activeTasks = new Map();
  }

  cancelTask = async (taskId, eventBus) => {
    this.cancelledTasks.add(taskId);
    const active = this.activeTasks.get(taskId);
    active?.controller.abort();
    eventBus.publish(AgentEvent.statusUpdate({
      taskId,
      contextId: active?.contextId ?? '',
      status: {
        state: TaskState.TASK_STATE_CANCELED,
        timestamp: new Date().toISOString(),
        message: undefined,
      },
      metadata: { agentSlug: this.role.slug },
    }));
  };

  async execute(requestContext, eventBus) {
    const { taskId, contextId, userMessage } = requestContext;
    const controller = new AbortController();
    this.activeTasks.set(taskId, { controller, contextId });
    const task = requestContext.task ?? {
      id: taskId,
      contextId,
      status: {
        state: TaskState.TASK_STATE_SUBMITTED,
        timestamp: new Date().toISOString(),
        message: undefined,
      },
      artifacts: [],
      history: [userMessage],
      metadata: userMessage.metadata,
    };
    eventBus.publish(AgentEvent.task(task));

    try {
      eventBus.publish(AgentEvent.statusUpdate({
        taskId,
        contextId,
        status: {
          state: TaskState.TASK_STATE_WORKING,
          timestamp: new Date().toISOString(),
          message: {
            messageId: crypto.randomUUID(),
            contextId,
            taskId,
            role: Role.ROLE_AGENT,
            parts: [textPart(`${this.role.name} 正在处理并生成交接产物。`)],
            metadata: {},
            extensions: [],
            referenceTaskIds: [],
          },
        },
        metadata: { agentSlug: this.role.slug },
      }));

      const prompt = messageText(userMessage);
      if (!prompt) {
        throw new Error('A text input is required');
      }
      const rawResult = await this.completionClient.complete({
        systemPrompt: this.role.systemPrompt,
        userPrompt: prompt,
        signal: controller.signal,
        maxTokens: this.role.maxTokens,
      });
      const result = parseHandoffResult(this.role.slug, rawResult);

      if (this.cancelledTasks.has(taskId)) {
        return;
      }

      eventBus.publish(AgentEvent.artifactUpdate({
        taskId,
        contextId,
        artifact: {
          artifactId: crypto.randomUUID(),
          name: `${this.role.slug}-handoff.md`,
          description: `${this.role.name} 生成的协作交接产物`,
          parts: [textPart(result.reportMarkdown, 'text/markdown'), dataPart(result.handoff)],
          metadata: {
            agentSlug: this.role.slug,
            model: this.completionClient.model,
            schemaVersion: HANDOFF_SCHEMA_VERSION,
            outcome: result.handoff.outcome,
          },
          extensions: [],
        },
        append: false,
        lastChunk: true,
        metadata: { agentSlug: this.role.slug },
      }));

      eventBus.publish(AgentEvent.statusUpdate({
        taskId,
        contextId,
        status: {
          state: TaskState.TASK_STATE_COMPLETED,
          timestamp: new Date().toISOString(),
          message: undefined,
        },
        metadata: { agentSlug: this.role.slug },
      }));
    } catch (error) {
      if (this.cancelledTasks.has(taskId) || controller.signal.aborted) return;
      const cause = error?.cause;
      const errorCode = error?.code ?? cause?.code ?? error?.name ?? 'UNKNOWN';
      console.error('[delivery-demo] agent task failed', {
        agentSlug: this.role.slug,
        taskId,
        errorCode,
        retryable: error?.retryable ?? false,
        message: error?.message,
        cause: cause?.message,
      });
      eventBus.publish(AgentEvent.statusUpdate({
        taskId,
        contextId,
        status: {
          state: TaskState.TASK_STATE_FAILED,
          timestamp: new Date().toISOString(),
          message: {
            messageId: crypto.randomUUID(),
            contextId,
            taskId,
            role: Role.ROLE_AGENT,
            parts: [textPart(`处理失败：${error.message}`)],
            metadata: {},
            extensions: [],
            referenceTaskIds: [],
          },
        },
        metadata: {
          agentSlug: this.role.slug,
          errorCode,
          retryable: error?.retryable ?? false,
          upstream: 'openai-compatible',
        },
      }));
    } finally {
      this.cancelledTasks.delete(taskId);
      this.activeTasks.delete(taskId);
    }
  }
}

export function mountRoleAgent(app, { role, baseURL, completionClient }) {
  const card = buildAgentCard(role, baseURL);
  const handler = new DefaultRequestHandler(
    card,
    new InMemoryTaskStore(),
    new RoleAgentExecutor(role, completionClient),
  );
  const basePath = `/agents/${role.slug}`;
  app.use(`${basePath}/${AGENT_CARD_PATH}`, agentCardHandler({ agentCardProvider: handler }));
  app.use(`${basePath}/a2a`, jsonRpcHandler({
    requestHandler: handler,
    userBuilder: UserBuilder.noAuthentication,
  }));
  return card;
}
