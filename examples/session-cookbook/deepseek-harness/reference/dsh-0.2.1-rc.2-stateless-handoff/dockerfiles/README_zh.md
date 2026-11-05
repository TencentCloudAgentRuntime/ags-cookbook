# DSH 源码补丁与镜像构建（dsh-v0.2.1-rc.2）

## 1. 为什么必须打补丁

persistence 插件能检测冲突、停止写入，但它看不到 turn 边界，也拿不到销毁 live generation 的 capability：

- `session/event` 是提交后的事件，监听器失败不会阻止 loop；
- `AgentHandle.dispose()` 只属于 `ctx.agents.create/resume` 的持有者；
- `session-controller` 没有公开的“按 sessionId 失效 generation”入口。

所以要实现“执行前检查 + 冲突后重建”，必须在 `session-controller` 里补三个点。

## 2. 补丁内容

### 2.1 保留 `AgentHandle`

`ApiSessionAgentController` 原来只取 `ctx.agents.create/resume` 返回的 `.agent`，把 handle 丢掉了。补丁按 Session 保存 handle，并在 create/resume 的三条路径上写入。

### 2.2 失效与重建 generation

```ts
async invalidateGeneration(sessionId): Promise<void> {
  // 先等待进行中的 resolve/claim 结束（handle 是它们写入的）
  // 幂等：没有 live handle 时，清理完状态直接返回
  // 删除 handles / resumes / claims，然后 await handle.dispose()
}

async resumeGeneration(sessionId): Promise<Agent> {
  await this.invalidateGeneration(sessionId)
  // resolveAgent() → ctx.agents.resume() 从持久化重读
}
```

`SessionController` 上有同名的委托方法，供集成插件调用。

### 2.3 pre-prompt hook

调用点在 `SessionCommandController.prompt`，**在 `resolveAgent` 之后、admission 之前**：

```ts
let agent = await this.resolveAgent(request.sessionId)
if (hasPromptRequest(agent, request.requestId)) return { accepted: true }
if (request.mode !== 'steer') {
  const handoff = this.ctx.get('sessionHandoff')
  if (handoff !== undefined) {
    const decision = await handoff.beforePrompt(request.sessionId)
    if (decision.action === 'rebuilt') agent = await this.resolveAgent(request.sessionId)
  }
}
```

为什么不在 `SessionController.prompt` 更早的位置：

- 首次 prompt 时本副本还没有 writer handle，`writerCursor()` 是 `undefined`，检查会失败；
- `resolveAgent` 之后 writer 一定存在，`invalidate` 也一定有真实 generation 可销毁；
- hook 抛出非 `RemoteError` 时，补丁映射为 `session/agent-busy`。

`steer` 必须跳过：它是在当前回合内插入的，重建会把正在跑的回合拆掉。

补丁同时声明了 `SessionHandoffService` 和 `SessionHandoffDecision`，未安装该服务时行为与原文一致。

## 3. 源码来源与版本

和 `deployment-cookbook/deepseek-harness/all-in-one/dockerfiles/Dockerfile` 使用同一套方式：从 GitHub clone 固定 tag，并校验 commit。

| 项 | 值 |
| --- | --- |
| tag | `dsh-v0.2.1-rc.2` |
| commit | `687f282e8625c6b8d11ff58211a90524be2e4317` |
| pnpm | `11.28.5`（DSH 根 `package.json` 的 `packageManager`） |

## 4. 构建镜像

构建上下文是本参考目录（`dsh-0.2.1-rc.2-stateless-handoff/`），不是仓库根：

```bash
cd examples/session-cookbook/deepseek-harness/reference/dsh-0.2.1-rc.2-stateless-handoff
docker build -t ags-dsh-stateless-handoff -f dockerfiles/Dockerfile .
```

镜像分两阶段：

1. **build**：clone tag、校验 commit、`git apply` 补丁、`pnpm install --frozen-lockfile`；
2. 跑 session-controller 的 `agent` / `commands-queue-attachment` / `controller` 测试；
3. `pnpm run build:official`，再用 `release:pack` 打出 vendor 和 dsh 两套 tarball；
4. **runtime**：安装 tarball，安装本目录插件，把 `@deepseek-ai` peer 依赖链接到 DSH 自己的副本，最后放入 Cordis 配置和 entrypoint。

第一次构建会编译整个 DSH，耗时较长。

构建阶段需要 apt 安装 `git` / `g++` / `make` / `python3`。`node:24.8.0-bookworm-slim` 的 Debian keyring 早于 bookworm 的归档密钥轮换，`apt-get update` 会报 `NoPubKey`，因此构建阶段默认使用 `node:24.22.2-bookworm-slim`，运行阶段仍使用基础示例的 `24.8.0`。需要内网镜像时覆盖：

```bash
docker build \
  --build-arg BUILD_IMAGE=your-registry/node:24.22.2-bookworm-slim \
  --build-arg RUNTIME_IMAGE=your-registry/node:24.8.0-bookworm-slim \
  -t ags-dsh-stateless-handoff -f dockerfiles/Dockerfile .
```

若某个版本把 `@deepseek-ai` 包提升到别的路径，覆盖 `DSH_MODULES`：

```bash
docker build --build-arg DSH_MODULES=/usr/local/lib/node_modules/@deepseek-ai ...
```

`build:official` 默认按 CPU 数并行执行构建 gate。内存较小的 Docker VM（例如 8G）可能在 `host compiler` 之后的 bundle / aggregate check 阶段 OOM，表现为 BuildKit 报 `error reading from server: EOF`。这时限制 gate 并发：

```bash
docker build --build-arg DSH_GATE_CONCURRENCY=1 -t ags-dsh-stateless-handoff -f dockerfiles/Dockerfile .
```

`pnpm install` 会从 `cdn.sheetjs.com` 拉取一个 xlsx tarball；慢网络下默认 60s 的 fetch 超时不够。Dockerfile 已把 `--fetch-timeout` 提高到 600s，不需要额外参数。

## 5. 运行时加载

[`agent-runtime-session.cordis.yml`](./agent-runtime-session.cordis.yml) 在基础示例的基础上多插入一个插件：

```yaml
- id: dsh-stateless-handoff
  name: '@tencentcloud/ags-dsh-session-persistence/handoff'
```

它必须在 `session-persistence-agent-runtime` 之后加载。集成插件（[`../plugin/dsh-handoff-plugin.js`](../plugin/dsh-handoff-plugin.js)）会：

- 调用 `attachDshHandoff`，把 `localEventCount` 接到 `writerCursor`；
- 从 `ctx.agents.get(id)?.status` 和 `ctx.sessionProjections.stateOf(session, 'turnBoundary')` 提供 liveness 端口；
- 注册 `sessionHandoff` 服务，供补丁中的 `prompt` 调用 `beforePrompt`；
- 订阅 `session-persistence/conflict`，冲突时 `invalidateGeneration` → `releaseWriter` → `resumeGeneration`。

## 6. 验证

构建阶段已经会跑三个 session-controller 测试文件。构建完成后，至少手工验证三条链路：

1. **A→B→A（无冲突）**
   - A 完成一轮并 flush；
   - B 在同一会话上完成一轮；
   - 下一轮回到 A：`preflight` 应返回 `stale` + `closed`，触发 `invalidateGeneration` + `resumeGeneration`，不进入模型调用前就完成重建。
2. **冲突恢复**
   - 让 A 在旧 generation 上继续写，触发 `ResourceInUse.EventIdDuplicate`；
   - 插件应标记 conflicted、停止重试、发 `session-persistence/conflict`；
   - 集成插件应完成重建，后续写入成功。
3. **未结束回合**
   - 制造一个没有 `turn/end` 的日志；
   - 新请求应返回 busy，而不是自动补 closer；
   - 如果 live Agent 正在驱动该回合（`status === 'running'`），同一副本的 followup 应正常排队。

## 7. 兼容性

- 补丁只针对 `dsh-v0.2.1-rc.2` / `687f282e...`，不要假设它能直接应用到最新版本。
- 升级 DSH 时重新 clone 新 tag，先 `git apply --check`；冲突通常只出现在四个位置：
  - `ApiSessionAgentController` 的 create/resume 与 handle 保存；
  - `SessionCommandController.prompt` 的 admission 路径；
  - `SessionController` 的委托方法；
  - Cordis `Context` 的服务声明。
- 如果上游后续提供原生的 pre-prompt / generation-invalidate hook，应删除补丁，直接注册服务。
- 如果同时需要 AGS 部署补丁（`0001-support-ags-deployment-web.patch`），先应用部署补丁再应用本补丁，并重新跑测试。

## 8. 验证状态

已在本机 Docker 环境完成以下验证（2026-11-05）：

| 项 | 结果 |
| --- | --- |
| 镜像构建 | ✅ `ags-dsh-stateless-handoff` 2.15GB |
| 构建期 session-controller 测试 | ✅ 3 files / 40 tests |
| `build:official` | ✅ 9 个 gate 全部 PASS，包含 host / client aggregate check |
| web profile 插件加载 | ✅ `[dsh-stateless-handoff] handoff service registered` |
| A→B→A | ✅ 副本 A → B → A 的回合全部 `completed`，无 EventId 冲突 |
| stale 交接 | ✅ A 的第三次请求日志：`handoff preflight {action:"rebuilt",state:"stale",turnState:"closed"}`，并出现 `rebuild started/finished` |

日志中的关键证据：

```text
[dsh-stateless-handoff] handoff rebuild started  {"reason":"preflight-stale"}
[dsh-stateless-handoff] handoff rebuild finished {"reason":"preflight-stale"}
[dsh-stateless-handoff] handoff preflight {"action":"rebuilt","state":"stale","turnState":"closed"}
```

未覆盖：

- 真实写入冲突（`ResourceInUse.EventIdDuplicate`）触发的 `recover()` 只在单测和插件级集成测试里覆盖，没有在镜像里人为制造；
- 未结束回合的 busy 行为只在单测覆盖；
- 工作区状态和工具副作用幂等不在本方案范围内。

构建环境注意：

- 8G 左右的 Docker VM 需要 `DSH_GATE_CONCURRENCY=1`，否则 `build:official` 的并行 gate 会 OOM；
- 运行阶段一次安装 700+ 个全局 tarball 也会 OOM；Dockerfile 已限制 V8 堆、先装 vendor 再装 dsh，并使用 `--legacy-peer-deps`；
- `xlsx@0.20.3` 只从 `cdn.sheetjs.com` 分发，慢网络下会拖慢 `pnpm install`；Dockerfile 已用 pnpm store cache mount 和 30 分钟 fetch timeout 缓解。
