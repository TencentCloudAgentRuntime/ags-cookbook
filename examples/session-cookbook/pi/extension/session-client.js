import TencentCloudSdk from 'tencentcloud-sdk-nodejs-ags'
import { seqOfEvent } from './session-codec.js'

const { Client } = TencentCloudSdk.ags.v20250920

export const AGENT_METADATA_KEY = 'example.com/pi-agent-id'

const MAX_RATE_LIMIT_RETRIES = 5
const PAGE_SIZE = 100

function required(value, name) {
  const result = value?.trim()
  if (!result) throw new Error(`${name} is required`)
  return result
}

export function configFromEnv(env = process.env) {
  return {
    region: required(env.AGR_REGION, 'AGR_REGION'),
    endpoint: env.SESSION_API_ENDPOINT?.trim() || undefined,
    secretId: required(env.TENCENTCLOUD_SECRET_ID, 'TENCENTCLOUD_SECRET_ID'),
    secretKey: required(env.TENCENTCLOUD_SECRET_KEY, 'TENCENTCLOUD_SECRET_KEY'),
    sessionToken: env.TENCENTCLOUD_SESSION_TOKEN?.trim() || undefined,
    spaceId: required(env.SESSION_SPACE_ID, 'SESSION_SPACE_ID'),
    userId: required(env.SESSION_USER_ID, 'SESSION_USER_ID'),
    agentId: env.SESSION_AGENT_ID?.trim() || undefined,
  }
}

function isRateLimited(error) {
  return String(error?.code ?? '').startsWith('RequestLimitExceeded')
}

/** The Session API calls this example needs, keyed to one SessionSpace and user. */
export class SessionClient {
  constructor(config, sdkClient) {
    this.config = config
    this.client = sdkClient ?? new Client({
      credential: {
        secretId: config.secretId,
        secretKey: config.secretKey,
        token: config.sessionToken,
      },
      region: config.region,
      profile: { httpProfile: config.endpoint ? { endpoint: config.endpoint } : {} },
    })
  }

  // Rate-limited calls were not executed, so retrying them is safe. AppendEvent is
  // also idempotent through its stable EventId.
  async request(action, payload) {
    for (let attempt = 0; ; attempt += 1) {
      try {
        return await this.client.request(action, payload)
      } catch (error) {
        if (!isRateLimited(error) || attempt >= MAX_RATE_LIMIT_RETRIES) throw error
        await new Promise(resolve => setTimeout(resolve, 200 * 2 ** attempt + Math.random() * 100))
      }
    }
  }

  key(sessionId, extra = {}) {
    return { SpaceId: this.config.spaceId, UserId: this.config.userId, SessionId: sessionId, ...extra }
  }

  ownsSession(session) {
    return !this.config.agentId
      || session.Metadata?.some(item => item.Name === AGENT_METADATA_KEY && item.Value === this.config.agentId)
  }

  /** The Session, or undefined when it does not exist. */
  async describeSession(sessionId) {
    try {
      const response = await this.request('DescribeSession', this.key(sessionId, { NumRecentEvents: 0 }))
      return response.Session ?? undefined
    } catch (error) {
      if (error?.code === 'ResourceNotFound.SessionNotExist') return undefined
      throw error
    }
  }

  async createSession(sessionId, state) {
    try {
      await this.request('CreateSession', this.key(sessionId, {
        State: { CustomState: state },
        ...(this.config.agentId ? { Metadata: [{ Name: AGENT_METADATA_KEY, Value: this.config.agentId }] } : {}),
      }))
    } catch (error) {
      // A retried CreateSession whose first attempt landed.
      if (error?.code !== 'ResourceInUse.SessionIdDuplicate') throw error
      const existing = await this.describeSession(sessionId)
      if (existing?.State?.CustomState !== state) throw error
    }
  }

  async appendEvent(sessionId, event) {
    await this.request('AppendEvent', this.key(sessionId, { Event: event }))
  }

  async countEvents(sessionId) {
    const response = await this.request('DescribeEvents', this.key(sessionId, { Offset: 0, Limit: 1 }))
    return Number(response.TotalCount ?? 0)
  }

  /** Every Event of the Session, ordered by the sequence number the codec stored. */
  async listEvents(sessionId) {
    const events = []
    for (let offset = 0; ;) {
      const response = await this.request('DescribeEvents', this.key(sessionId, { Offset: offset, Limit: PAGE_SIZE }))
      const page = response.Events ?? []
      events.push(...page)
      offset += page.length
      if (page.length === 0 || offset >= Number(response.TotalCount ?? offset)) break
    }
    return events.sort((left, right) => (seqOfEvent(left) ?? Infinity) - (seqOfEvent(right) ?? Infinity))
  }

  /** Session ids of this user, narrowed to SESSION_AGENT_ID when it is set. */
  async listSessionIds() {
    const ids = []
    for (let offset = 0; ;) {
      const response = await this.request('DescribeSessions', {
        SpaceId: this.config.spaceId,
        UserIds: [this.config.userId],
        ...(this.config.agentId
          ? { Filters: [{ Name: `metadata:${AGENT_METADATA_KEY}`, Values: [this.config.agentId] }] }
          : {}),
        Offset: offset,
        Limit: PAGE_SIZE,
      })
      const page = response.Sessions ?? []
      ids.push(...page.map(session => session.SessionId))
      offset += page.length
      if (page.length === 0 || offset >= Number(response.TotalCount ?? offset)) break
    }
    return ids
  }
}
