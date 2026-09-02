import type { Context } from "@deepseek-ai/cordis";
import { hostname } from "node:os";

export const name = "ags-web-startup";

declare module "@deepseek-ai/cordis" {
  interface Context {
    webStartup: {
      readonly host: string;
      readonly port: number;
      readonly openBrowser: boolean;
      readonly trustedHosts: readonly string[];
    };
  }
}

/** Deployment-owned Web bind settings; the browser is reached through agr instance proxy. */
export function apply(ctx: Context): void {
  const region = process.env.AGS_REGION ?? "ap-shanghai";
  const domain = process.env.AGS_DATA_PLANE_DOMAIN ?? "tencentags.com";
  ctx.provide("webStartup", {
    host: "0.0.0.0",
    port: 3080,
    openBrowser: false,
    trustedHosts: [
      "127.0.0.1",
      "localhost",
      `*.${region}.${domain}`,
      `*.${region}.agents.${domain}`,
      `3080-${hostname()}.${region}.${domain}`,
    ],
  });
}
