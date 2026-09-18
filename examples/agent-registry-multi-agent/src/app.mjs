import express from 'express';
import { mountRoleAgent } from './a2a-runtime.mjs';
import { ROLE_DEFINITIONS } from './roles.mjs';

export function createApp({ baseURL, completionClient }) {
  const app = express();
  app.disable('x-powered-by');
  app.use(express.json({ limit: '2mb' }));

  const cards = ROLE_DEFINITIONS.map((role) =>
    mountRoleAgent(app, { role, baseURL, completionClient }));

  app.get('/health', (_request, response) => {
    response.json({
      status: 'ok',
      model: completionClient.model,
      agentCount: cards.length,
      agents: ROLE_DEFINITIONS.map((role) => ({
        slug: role.slug,
        name: role.name,
        cardURL: `${baseURL}/agents/${role.slug}/.well-known/agent-card.json`,
      })),
    });
  });

  app.get('/', (_request, response) => {
    response.json({
      name: 'Agent Registry Multi-Agent Delivery Demo',
      health: `${baseURL}/health`,
      agents: ROLE_DEFINITIONS.map((role) => ({
        name: role.name,
        description: role.description,
        cardURL: `${baseURL}/agents/${role.slug}/.well-known/agent-card.json`,
        a2aURL: `${baseURL}/agents/${role.slug}/a2a`,
      })),
    });
  });

  return { app, cards };
}
