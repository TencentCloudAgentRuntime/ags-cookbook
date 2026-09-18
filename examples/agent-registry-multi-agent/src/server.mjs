import 'dotenv/config';
import { createApp } from './app.mjs';
import { OpenAICompatibleClient } from './openai-client.mjs';

const host = process.env.DEMO_HOST || '127.0.0.1';
const port = Number(process.env.DEMO_PORT || 18080);
if (!Number.isInteger(port) || port < 1 || port > 65535) {
  throw new Error('DEMO_PORT must be an integer between 1 and 65535');
}
const publicBaseURL = process.env.DEMO_PUBLIC_BASE_URL || `http://${host}:${port}`;
const completionClient = new OpenAICompatibleClient();
const { app, cards } = createApp({ baseURL: publicBaseURL, completionClient });

const server = app.listen(port, host, (error) => {
  if (error) throw error;
  console.log(`[delivery-demo] ${cards.length} A2A agents ready at ${publicBaseURL}`);
  console.log(`[delivery-demo] model: ${completionClient.model}`);
  for (const card of cards) {
    console.log(`[delivery-demo] ${card.name}: ${card.supportedInterfaces[0].url}`);
  }
});

for (const signal of ['SIGINT', 'SIGTERM']) {
  process.on(signal, () => {
    server.close(() => process.exit(0));
  });
}
