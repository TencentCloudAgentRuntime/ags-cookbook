import assert from 'node:assert/strict'
import test from 'node:test'
import { PROVIDER, missingVariables, modelSettings } from './configure-model.mjs'

const env = {
  LLM_BASE_URL: ' https://tokenhub.tencentmaas.com/v1 ',
  LLM_MODEL: 'deepseek-v4-flash',
  LLM_API_KEY: 'secret-value',
}

test('missingVariables reports unset and blank model variables', () => {
  assert.deepEqual(missingVariables(env), [])
  assert.deepEqual(missingVariables({ ...env, LLM_MODEL: '  ', LLM_API_KEY: undefined }), ['LLM_MODEL', 'LLM_API_KEY'])
})

test('modelSettings points DSH at the configured service without writing the API key', () => {
  const settings = Object.fromEntries(modelSettings(env).map(([path, value]) => [path.join('.'), value]))
  assert.deepEqual(settings[`llm-pi-ai.providers.${PROVIDER}`], {
    displayName: 'Configured Model Service',
    apiKeyEnv: 'LLM_API_KEY',
    api: 'openai-completions',
    baseURL: 'https://tokenhub.tencentmaas.com/v1',
    models: [{ id: 'deepseek-v4-flash' }],
  })
  assert.deepEqual(settings['agent-default-model'], { provider: PROVIDER, model: 'deepseek-v4-flash' })
  assert.equal(JSON.stringify(settings).includes(env.LLM_API_KEY), false)
})
