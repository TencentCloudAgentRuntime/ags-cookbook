import type { Context } from "@deepseek-ai/cordis";
import CredentialProvider, {
  type CredentialInfo,
  type CredentialKey,
  type CredentialRecord,
  type CredentialRecordEntry,
  type CredentialRecordInfo,
  type CredentialRef,
  type ResolvedCredential,
} from "@deepseek-ai/dsh-credentials";

/** Read-only environment credentials for stateless Brain replicas. */
export class EnvironmentCredentialProvider extends CredentialProvider {
  public constructor(ctx: Context) {
    super(ctx);
  }

  public async resolve(ref: CredentialRef): Promise<ResolvedCredential | undefined> {
    const value = process.env[ref];
    return value === undefined || value.length === 0 ? undefined : { value, source: "env" };
  }

  public async describe(ref: CredentialRef): Promise<CredentialInfo> {
    const configured = await this.resolve(ref) !== undefined;
    return configured ? { configured, source: "env", writable: false } : { configured, writable: false };
  }

  public async set(): Promise<void> {
    throw new Error("Credentials are configured through Brain environment variables");
  }

  public async unset(): Promise<void> {
    throw new Error("Credentials are configured through Brain environment variables");
  }

  public async readRecord(): Promise<CredentialRecord | undefined> {
    return undefined;
  }

  public async describeRecord(): Promise<CredentialRecordInfo> {
    return { configured: false, writable: false };
  }

  public async listRecords(): Promise<readonly CredentialRecordEntry[]> {
    return [];
  }

  public async modifyRecord(
    _key: CredentialKey,
    _mutate: (current: CredentialRecord | undefined) => Promise<CredentialRecord | undefined>,
  ): Promise<CredentialRecord | undefined> {
    throw new Error("Credential records are not writable in this deployment");
  }

  public async deleteRecord(): Promise<void> {
    throw new Error("Credential records are not writable in this deployment");
  }
}

export default EnvironmentCredentialProvider;
