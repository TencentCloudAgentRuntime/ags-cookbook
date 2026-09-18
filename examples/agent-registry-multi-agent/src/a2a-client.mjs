import crypto from 'node:crypto';
import { ClientFactory } from '@a2a-js/sdk/client';
import { Role, taskStateToJSON } from '@a2a-js/sdk';
import { callRegistryAction } from './registry-client.mjs';

function requiredString(value, name) {
  if (typeof value !== 'string' || value.trim() === '') throw new Error(`${name} is required`);
  return value.trim();
}

function descriptorObject(value) {
  if (value !== null && typeof value === 'object' && !Array.isArray(value)) return value;
  if (typeof value !== 'string') throw new Error('resolved A2A Descriptors must be an object or JSON string');
  let parsed;
  try {
    parsed = JSON.parse(value);
  } catch (error) {
    throw new Error(`resolved A2A Descriptors are invalid JSON: ${error.message}`);
  }
  if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error('resolved A2A Descriptors must contain one JSON object');
  }
  return parsed;
}

function partContent(part) {
  if (part?.content?.$case === 'text') return { type: 'text', value: part.content.value };
  if (part?.content?.$case === 'data') return { type: 'data', value: part.content.value };
  if (typeof part?.text === 'string') return { type: 'text', value: part.text };
  if (part?.data !== undefined) return { type: 'data', value: part.data };
  return null;
}

function normalizeArtifact(artifact, includeArtifactContent) {
  const parts = Array.isArray(artifact?.parts) ? artifact.parts : [];
  const normalizedParts = parts.map((part) => {
    const content = partContent(part);
    return content === null ? null : {
      type: content.type,
      mediaType: part.mediaType || (content.type === 'data' ? 'application/json' : 'text/plain'),
      ...(includeArtifactContent || content.type === 'data' ? { content: content.value } : {}),
    };
  }).filter(Boolean);
  return {
    artifactId: artifact?.artifactId,
    name: artifact?.name,
    description: artifact?.description,
    metadata: artifact?.metadata ?? {},
    parts: normalizedParts,
  };
}

function failureMessage(task) {
  const parts = task?.status?.message?.parts ?? [];
  return parts.map(partContent).find((part) => part?.type === 'text')?.value;
}

export function normalizeA2AResult(result, target, includeArtifactContent = false) {
  if (result?.status === undefined) {
    return {
      kind: 'message',
      target,
      messageId: result?.messageId,
      contextId: result?.contextId,
      parts: (result?.parts ?? []).map(partContent).filter(Boolean),
    };
  }
  const artifacts = (result.artifacts ?? []).map((artifact) =>
    normalizeArtifact(artifact, includeArtifactContent));
  const handoff = artifacts
    .flatMap((artifact) => artifact.parts)
    .find((part) => part.type === 'data' && part.mediaType === 'application/json')?.content ?? null;
  return {
    kind: 'task',
    target,
    taskId: result.id,
    contextId: result.contextId,
    state: taskStateToJSON(result.status.state),
    failure: failureMessage(result) ?? null,
    handoff,
    artifacts,
  };
}

export class RegistryA2AClient {
  constructor({
    registryConfig,
    clientFactory = new ClientFactory(),
    registryCall = callRegistryAction,
  }) {
    this.registryConfig = registryConfig;
    this.clientFactory = clientFactory;
    this.registryCall = registryCall;
  }

  async resolveTarget({ registryId, recordId, versionId }) {
    const response = await this.registryCall(this.registryConfig, 'DescribeRegistryRecord', {
      RegistryId: requiredString(registryId, 'registry_id'),
      RecordId: requiredString(recordId, 'record_id'),
      VersionId: requiredString(versionId, 'version_id'),
    });
    if (response.Record?.DescriptorType !== 'A2A') {
      throw new Error(`Registry Record ${recordId} is not an A2A record`);
    }
    const version = response.Version ?? response.StableVersion;
    if (!version?.VersionId) throw new Error(`Registry Record ${recordId} did not resolve a version`);
    if (version.VersionId !== versionId) {
      throw new Error(`Registry resolved ${version.VersionId}, expected immutable version ${versionId}`);
    }
    const card = descriptorObject(version.Descriptors);
    if (!Array.isArray(card.supportedInterfaces) || card.supportedInterfaces.length === 0) {
      throw new Error(`A2A Record ${recordId} has no supported interface`);
    }
    return {
      requestId: response.RequestId,
      registryId,
      recordId,
      versionId: version.VersionId,
      revision: version.Revision,
      recordName: response.Record.Name,
      card,
    };
  }

  async clientFor(target) {
    return this.clientFactory.createFromAgentCard(target.card);
  }

  async sendMessage(args) {
    const target = await this.resolveTarget(args);
    const client = await this.clientFor(target);
    const result = await client.sendMessage({
      tenant: '',
      message: {
        messageId: crypto.randomUUID(),
        contextId: args.contextId ?? '',
        taskId: args.taskId ?? '',
        role: Role.ROLE_USER,
        parts: [{
          content: { $case: 'text', value: requiredString(args.message, 'message') },
          metadata: undefined,
          filename: '',
          mediaType: 'text/plain',
        }],
        metadata: {
          registryId: target.registryId,
          registryRecordId: target.recordId,
          registryVersionId: target.versionId,
        },
        extensions: [],
        referenceTaskIds: args.referenceTaskIds ?? [],
      },
      configuration: {
        acceptedOutputModes: ['application/json', 'text/markdown', 'text/plain'],
        taskPushNotificationConfig: undefined,
        historyLength: 0,
        returnImmediately: args.returnImmediately ?? true,
      },
      metadata: undefined,
    });
    return normalizeA2AResult(result, {
      requestId: target.requestId,
      registryId: target.registryId,
      recordId: target.recordId,
      recordName: target.recordName,
      versionId: target.versionId,
      revision: target.revision,
    }, args.includeArtifactContent);
  }

  async getTask(args) {
    const target = await this.resolveTarget(args);
    const client = await this.clientFor(target);
    const result = await client.getTask({
      tenant: '',
      id: requiredString(args.taskId, 'task_id'),
      historyLength: 0,
    });
    return normalizeA2AResult(result, {
      requestId: target.requestId,
      registryId: target.registryId,
      recordId: target.recordId,
      recordName: target.recordName,
      versionId: target.versionId,
      revision: target.revision,
    }, args.includeArtifactContent);
  }

  async cancelTask(args) {
    const target = await this.resolveTarget(args);
    const client = await this.clientFor(target);
    const result = await client.cancelTask({
      tenant: '',
      id: requiredString(args.taskId, 'task_id'),
    });
    return normalizeA2AResult(result, {
      requestId: target.requestId,
      registryId: target.registryId,
      recordId: target.recordId,
      recordName: target.recordName,
      versionId: target.versionId,
      revision: target.revision,
    }, false);
  }
}
