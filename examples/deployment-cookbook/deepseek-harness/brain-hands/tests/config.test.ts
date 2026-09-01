import { describe, expect, it } from "vitest";

import { mysqlConfigFromEnv, mysqlPoolOptions } from "../src/mysql/config.js";
import { brainConfigFromEnv } from "../src/brain/config.js";

const validEnv = {
  MYSQL_HOST: "mysql.example.com",
  MYSQL_PORT: "3306",
  MYSQL_USER: "dsh",
  MYSQL_PASSWORD: "secret",
  MYSQL_DATABASE: "dsh-cookbook",
};

describe("MySQL configuration", () => {
  it("accepts the cookbook database name with a hyphen", () => {
    expect(mysqlConfigFromEnv(validEnv)).toMatchObject({ database: "dsh-cookbook" });
  });

  it("rejects database identifiers that could become SQL", () => {
    expect(() => mysqlConfigFromEnv({
      ...validEnv,
      MYSQL_DATABASE: "dsh-cookbook; DROP DATABASE mysql",
    })).toThrow(/MYSQL_DATABASE/);
  });

  it("keeps multi-statement execution disabled for runtime pools", () => {
    expect(mysqlPoolOptions(mysqlConfigFromEnv(validEnv)).multipleStatements).toBe(false);
  });
});

describe("Brain configuration", () => {
  it("derives the envd data-plane URL without exposing client-controlled identity", () => {
    const config = brainConfigFromEnv({
      ...validEnv,
      BRAIN_WORKSPACE_USER_ID: "cookbook-user",
      AGS_REGION: "ap-shanghai",
      HANDS_DEPLOYMENT_ID: "dpl-example",
      TENCENTCLOUD_SECRET_ID: "id",
      TENCENTCLOUD_SECRET_KEY: "key",
    });
    expect(config.hands.baseUrl).toBe(
      "https://49983-dpl-example.ap-shanghai.agents.tencentags.com",
    );
    expect(config.hands.apiEndpoint).toBe("ags.tencentcloudapi.com");
    expect(config.llm).toMatchObject({ provider: "tokenhub", model: "deepseek-v4-flash" });
    expect(config.workspaceUserId).toBe("cookbook-user");
  });
});
