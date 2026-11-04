# DSH 源码补丁（dsh-v0.2.1-rc.2）

这个补丁把无状态交接需要的两个能力加到 DSH 的 session-controller：

1. **保留 `AgentHandle`**：`ctx.agents.create/resume` 返回的 handle 是唯一能销毁 agent 的 capability。原实现只取 `.agent`，handle 被丢弃；补丁把它保存在 `ApiSessionAgentController.handles`。
2. **generation 失效/重建**：新增 `invalidateGeneration(sessionId)` 和 `resumeGeneration(sessionId)`；前者 `await handle.dispose()`，后者 dispose 后重新 `resolveAgent`（即从持久化 resume）。
3. **pre-prompt hook**：在 `SessionController.prompt` 为非 `steer` 请求调用 `ctx.get('sessionHandoff')?.beforePrompt(sessionId)`；插件在这里执行 `controller.preflight()`。

## 源码来源与版本

和 `deployment-cookbook/deepseek-harness/all-in-one/dockerfiles/Dockerfile` 使用同一套方式：直接从 GitHub clone 固定 tag，并校验 commit。

```bash
git clone --depth 1 --branch dsh-v0.2.1-rc.2 \
  https://github.com/deepseek-ai/deepseek-harness.git
git -C deepseek-harness rev-parse HEAD
# 必须为 687f282e8625c6b8d11ff58211a90524be2e4317
```

目标版本：

| 项 | 值 |
| --- | --- |
| tag | `dsh-v0.2.1-rc.2` |
| commit | `687f282e8625c6b8d11ff58211a90524be2e4317` |
| pnpm | `11.28.5`（DSH 根 `package.json` 的 `packageManager`） |

## 应用与构建

```bash
cd deepseek-harness
git apply --check /path/to/0001-stateless-handoff.patch
git apply /path/to/0001-stateless-handoff.patch

pnpm install --frozen-lockfile
pnpm run build:official
pnpm release:pack --family vendor --out dist/npm-vendor
pnpm release:pack --family dsh --out dist/npm-dsh
```

构建完成后，按 [基础 0.2.1-rc.2 镜像](../../../dsh-0.2.1-rc.2/dockerfiles/Dockerfile) 的方式安装插件并链接 `@deepseek-ai` 模块；本参考目录的 `plugin/` 可以替换该示例的 `plugin/`。

建议至少运行：

```bash
pnpm exec vitest run packages/api/session-controller/tests/agent.host.spec.ts
```

## 插件侧接线

补丁只提供 hook，不直接依赖本插件。需要一个很小的 Cordis 集成插件调用 `attachDshHandoff`：

```js
import { attachDshHandoff } from '@tencentcloud/ags-dsh-session-persistence'

export const name = 'dsh-stateless-handoff'
export const inject = ['sessionController', 'sessionPersistence']

export function apply(ctx) {
  attachDshHandoff(ctx, {
    generation: {
      invalidate: id => ctx.sessionController.invalidateGeneration(id),
      resume: id => ctx.sessionController.resumeGeneration(id),
    },
    logger: (message, fields) => ctx.logger.info(`${message} ${JSON.stringify(fields)}`),
  })
}
```

`attachDshHandoff` 会：

- 把 `localEventCount` 接到 `sessionPersistence.writerCursor`；
- 注册 `sessionHandoff` 服务，供补丁中的 `prompt` 调用 `beforePrompt`；
- 订阅 `session-persistence/conflict`，冲突时走 `controller.recover`。

## 兼容性与维护

- 补丁只针对 `dsh-v0.2.1-rc.2` / `687f282e...`，不要假设它能直接应用到最新版本。
- 升级 DSH 时重新 clone 新 tag，先 `git apply --check`；冲突通常只出现在三个位置：
  - `ApiSessionAgentController` 的 create/resume；
  - `SessionController.prompt` 的准入路径；
  - Cordis `Context` 的服务声明。
- 补丁保持最小：只增加 handle 保留、generation invalidate/resume 和一个可选的 `sessionHandoff` hook；未安装该服务时行为不变。
- 如果上游后续提供了原生的 pre-prompt/generation-invalidate hook，应删除补丁，直接注册服务。
- 如果同时需要 AGS 部署补丁（`0001-support-ags-deployment-web.patch`），先应用部署补丁再应用本补丁，并重新跑上面的测试。

## 验证状态

补丁只做了 `git apply --check` 和代码审查，**没有在本仓库构建/运行 DSH**。要宣称可用，必须完成：

1. 用上面命令构建镜像；
2. 运行 session-controller 测试；
3. 在真实 DSH 进程里跑 A→B→A：B 写入后，A 收到下一轮请求时 `preflight` 发现 stale，`invalidateGeneration` + `resumeGeneration` 后从云端继续。
