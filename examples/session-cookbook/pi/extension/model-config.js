// Builds pi's models.json from the LLM_* variables. The key is not written to the
// file: pi reads $LLM_API_KEY from the environment when it makes a request.
export const PROVIDER = 'custom'

export function modelsJson(env = process.env) {
  const missing = ['LLM_BASE_URL', 'LLM_MODEL', 'LLM_API_KEY'].filter(name => !env[name]?.trim())
  if (missing.length > 0) {
    throw new Error(`set ${missing.join(', ')}; see .env.example`)
  }
  return {
    providers: {
      [PROVIDER]: {
        baseUrl: env.LLM_BASE_URL.trim(),
        api: 'openai-completions',
        apiKey: '$LLM_API_KEY',
        models: [{ id: env.LLM_MODEL.trim() }],
      },
    },
  }
}
