# 无状态会话交接参考实现（DSH 0.2.1-rc.2）

[English](./README.md)

本目录是 [dsh-0.2.1-rc.2](../../dsh-0.2.1-rc.2/README_zh.md) 持久化插件的一个**参考实现**，用于讨论多副本部署下的无状态会话交接。这里的“无状态”指副本不长期绑定会话，可以在回合边界被其他副本接管；一轮执行期间仍然需要 live session。它不是新的 DSH 版本，也不是可直接独立部署的示例；基础示例的插件、镜像和文档保持不变。

本参考实现覆盖无状态交接的插件侧部分：检测 EventId 冲突、停止重试、让出写句柄，并提供执行前检查和 teardown 辅助接口。它**不引入租约**，也**不能自行重建 live session**。

## 1. 与基础示例的关系

| 方面 | 基础示例 `dsh-0.2.1-rc.2` | 本参考实现 |
| --- | --- | --- |
| 正常写入路径 | 相同 | 相同 |
| EventId 冲突 | 批次留在缓冲区，下一次 flush 继续重试；副本会持续失败，需要重启 | 标记写句柄为 conflicted，丢弃未提交批次，拒绝后续写入，并发出 `session-persistence/conflict` |
| 恢复方式 | 重启副本 | 由上层销毁并重建 generation；本参考实现只提供检测和辅助接口 |
| 部署形态 | 可直接构建镜像 | 参考插件，需自行集成到 DSH 镜像和会话生命周期 |

差异以补丁形式保留在 [stateless-handoff.patch](./stateless-handoff.patch)，便于对照基础插件审查。补丁以基础插件的路径为基准，可在仓库根执行：

```bash
git apply examples/session-cookbook/deepseek-harness/reference/dsh-0.2.1-rc.2-stateless-handoff/stateless-handoff.patch
```

## 2. 插件行为

冲突发生时（Session API 返回 `ResourceInUse.EventIdDuplicate`）：

1. 抛出 `SessionPersistenceConflictError`，包含 `sessionId`、`eventId` 和原始错误。
2. 写句柄永久进入 conflicted 状态：
   - 后续 `append` / `flush` 直接以同一错误拒绝；
   - `enqueueLive` 不再缓冲新事件，而是通过失败回调上报；
   - 未提交的本地批次被丢弃，不重试、不改写序号。
3. 前台冲突由调用方收到错误；后台冲突会记录 error 级别日志，并发出 Cordis 事件：

   ```text
   session-persistence/conflict
   ```

   监听参数为 `(session, error)`。
4. `close()` 在 conflicted 状态下跳过排空，直接释放进程内写 claim，保证 teardown 能完成。
5. 新增四个辅助接口：
   - `handoffCheck(id, localEventCount)`：执行前检查云端状态，返回 `fresh` / `stale` / `local-ahead` / `not-found` 和 `turnClosed`；
   - `eventCount(id)`：读取云端事件数；
   - `writerCursor(id)`：读取本副本写句柄已持久化的游标；
   - `releaseWriter(id)`：等待该会话的写句柄关闭并释放进程内 claim，供 generation 重建前调用。

## 3. 上层必须做的恢复动作

插件无法重建 live session，也无法取消正在执行的 turn。集成方需要：

1. 监听 `session-persistence/conflict`，或捕获 `SessionPersistenceConflictError`。
2. 停止该 generation 接收新输入，并取消（或等待）当前执行。
3. 销毁当前 agent / generation。
4. `await releaseWriter(sessionId)`，确保旧 writer 已关闭、进程内 claim 已释放。
5. 通过 DSH 的恢复路径重新打开会话（预期是 `ctx.agents.resume({ resumeSessionId })`，需在 0.2.1-rc.2 上验证）。
6. 按执行状态决定是否重跑：
   - 本轮尚未开始执行：重建后可有界重试；
   - 本轮已经开始执行：返回“执行结果不确定”，默认不自动重跑；
   - 外部工具副作用无法由会话日志回滚，必要时需要工具自己的幂等键。

> 文档中的 `ctx.agents.resume()`、`handle.dispose()`、session-controller 的 generation 语义来自 DSH 仓库文档；本仓库没有这些包的源码。**这些能力必须在 DSH 0.2.1-rc.2 上实际验证**，不能由插件行为推断。

## 4. 控制器（handoff-controller.js）

插件只提供原语。`handoff-controller.js` 把它们收敛成一个显式状态机，供持有 live session 的上层调用。

集成方提供 host：

| host 方法 | 职责 |
| --- | --- |
| `localEventCount(sessionId)` | 本副本已持久化的事件数；可直接用 `persistence.writerCursor(sessionId)` |
| `invalidate(sessionId)` | 停止接收输入、取消或等待当前 turn、销毁 agent，并等待 teardown 完成 |
| `resume(sessionId)` | 走 DSH 的恢复路径重新打开会话（预期是 `ctx.agents.resume({ resumeSessionId })`） |
| `flush(sessionId)`（可选） | 在 `local-ahead` 时先执行 flush |
| `liveAgentStatus(sessionId)`（可选） | `ctx.agents.get(id)?.status`：`'idle' \| 'running' \| undefined` |
| `liveTurnState(sessionId)`（可选） | `sessionProjections.stateOf(session, 'turnBoundary')` 折算出的 `'none' \| 'open' \| 'closed'` |

后两个是可选的 liveness 端口。没有它们时控制器保持保守：`fresh` 遇到未结束回合一律返回 busy。`attachDshHandoff` 会自动从 `ctx.agents` 和 `ctx.sessionProjections` 推导，不需要调用方手写。

`dsh-handoff.js` 把接线收敛成一个 generation port：

```js
const { controller, dispose } = attachDshHandoff(ctx, {
  generation: {
    invalidate: id => ctx.sessionController.invalidateGeneration(id),
    resume: id => ctx.sessionController.resumeGeneration(id),
    flush: id => flushSession(id), // 可选
  },
})
```

- `localEventCount` 自动接到 `persistence.writerCursor`；
- liveness 端口自动来自 `ctx.agents` / `ctx.sessionProjections`；
- `generation` 是唯一与 DSH 版本相关的部分；
- `attachDshHandoff` 同时订阅 `session-persistence/conflict`，并注册 `sessionHandoff` 服务。

控制器用法：

```js
const controller = createHandoffController({ persistence, host, logger })
const decision = await controller.preflight(sessionId)
// run | rebuilt | create | blocked；未结束回合抛 HandoffBusyError
```

`preflight` 的决策：

| 检查结果 | live agent | 回合边界 | 动作 |
| --- | --- | --- | --- |
| `not-found` | — | — | `create`，按新建会话处理 |
| `local-ahead` | — | — | 有 `flush` 就先 flush 再检查，否则 `blocked` |
| `stale` | `running` | — | 抛 `HandoffBusyError`（`local-turn-running`），不重建正在跑的回合 |
| `stale` | idle / 无 | `open` | 抛 `HandoffBusyError`，不自动补 closer |
| `stale` | idle / 无 | `closed` | 依次 `invalidate` → `releaseWriter` → `resume`，返回 `rebuilt` |
| `fresh` | `running` | `open` | `run`：本副本正在跑，followup 正常排队 |
| `fresh` | idle / 无 | `open` | 抛 `HandoffBusyError`：无人驱动但回合开口 = 崩溃残留或刚 resume |
| `fresh` | 任意 | `closed` / `none` | `run` |

`recover(sessionId)` 用于冲突事件：只重建 generation，不重跑 turn。并发调用会合并为一次重建；`invalidate` 或 `releaseWriter` 失败时不会 `resume`。`preflight` 的检查也会等待进行中的重建结束，避免在 generation 拆到一半时读 writer cursor。

Cordis 集成可以直接订阅冲突事件：

```js
const dispose = attachConflictRecovery(ctx, controller)
```

它监听 `session-persistence/conflict`，对出错的会话调用 `recover(sessionId, 'conflict')`，并返回 disposer。

接入点：

1. 部署时加载 [`plugin/dsh-handoff-plugin.js`](./plugin/dsh-handoff-plugin.js)（Cordis 名 `@tencentcloud/ags-dsh-session-persistence/handoff`）。它调用 `attachDshHandoff`，创建 controller、注册 `sessionHandoff` 服务并订阅冲突事件。
2. 补丁在 `SessionCommandController.prompt` 中、`resolveAgent` 之后、admission 之前调用 `sessionHandoff.beforePrompt(sessionId)`；返回 `rebuilt` 时重新 resolve Agent 再继续。`steer` 不经过这个检查。
3. 冲突事件：由 `attachConflictRecovery` 调用 `recover`；这一轮不要继续写入。
4. 轮结束后：确保 `session/flush` 成功，下一轮 `preflight` 才能看到 durable cursor。

`invalidate` / `resume` / liveness 端口都基于 0.2.1-rc.2 的公开 API；控制器本身仍用 fake host 覆盖状态机、执行顺序和失败路径。真实构建与 A→B→A 验证见 [dockerfiles/README_zh.md](./dockerfiles/README_zh.md)。

## 5. 执行前检查

集成方可以在每轮开始前调用 `handoffCheck(id, localEventCount)`：

| state | 含义 | 建议动作 |
| --- | --- | --- |
| `fresh` | 云端与本地已持久化的事件数一致 | 正常执行 |
| `stale` | 云端领先，另一个 writer 已经写入 | 先重建 generation，再执行 |
| `local-ahead` | 本地领先，可能有未 flush 的事件 | 先 flush 或重建，不要直接执行 |
| `not-found` | 会话尚不存在 | 按新建处理 |

`handoffCheck` 还返回三态 `turnState`、派生的 `turnClosed` 和 `lastEvent`：

| `turnState` | 含义 |
| --- | --- |
| `none` | 还没有任何事件，会话从未开始过回合 |
| `closed` | 扫描窗口内最后一个回合边界是 `turn/end` |
| `open` | 最后边界是 `turn/start`，或非空窗口内没有任何边界（回合比窗口长） |

`turnState` 只是持久化日志的尾部判断，**不是 liveness 信号**：`open` 无法区分“另一个副本还在跑”和“崩溃残留”。真正的死活由 live Agent 的 `status` 决定（见第 4 节状态表）。拿不到 live 状态时保持保守：`fresh + open` 返回 busy。

限制与成本：

- 这个检查不是锁，检查和写入之间仍可能竞争；写时的 EventId 冲突检测是最后一道防线。
- `turnClosed` 不是 liveness 信号，无法区分“旧执行已经崩溃”和“仍在另一个副本执行”；它也不能替代 DSH 自己的中断修复逻辑。
- “上一轮已结束”还要求 `turn/end` 已成功持久化（flush 完成）；只写入 `turn/end` 但 flush 失败不算完成。
- 读取成本：`fresh` / `local-ahead` 只发 1 次 `DescribeEvents`，`turnClosed` 从本地 write handle 的日志尾部判断；只有 `stale` 需要第 2 次读取云端尾部。

## 6. 第一阶段边界

本参考实现只覆盖“回合之间切换”的场景：

**支持**

- A 执行完一轮、完整持久化后，B 接手下一轮；
- 旧 generation 仍然存活但云端已经被别人写过的冲突检测与止损；
- 冲突后由上层重建 generation，再继续。

**不支持**

- 同一会话的重叠执行；
- 冲突轮自动重跑；
- 崩溃后自动接续进行中的回合；
- 工作区文件、进程和模型连接的迁移；
- 从日志判断另一个副本是否仍在执行。仅凭事件日志无法区分“崩溃中断”和“活跃回合”，因此不要自动终结未结束的回合。

## 7. 需要验证的 DSH 能力

已在 `dsh-v0.2.1-rc.2` 源码上确认：

1. `ctx.agents.resume()`、`ctx.agents.create()` 返回 `AgentHandle`，`handle.dispose()` 存在；它是销毁 live generation 的唯一 capability。
2. `Agent` 公开 `status: 'idle' | 'running'`（`agent/status` 同步发布），这是判断“本副本是否仍在驱动回合”的 liveness 信号。
3. `ctx.sessionProjections.stateOf(session, 'turnBoundary')` 提供 `openTurnStartSeq` / `lastTurn`，可无歧义地区分 `none` / `open` / `closed`。
4. 0.2.1-rc.2 没有自动补 `turn/end` 的中断修复；`turn()` 追加 `turn/start` 时也不检查已有开口。因此“未结束回合”必须由上层显式处理。
5. `session-controller` 没有 retain/release generation 的公开语义；generation 的生命周期由 `ctx.agents` 中的 handle 决定，本参考实现通过保存并 dispose handle 来失效。

仍需在真实构建后验证：

- `handle.dispose()` 是否等待写句柄关闭（本实现随后调用 `persistence.releaseWriter` 作为显式屏障）；
- `turn/end` 之后是否保证一次成功的 `session/flush`；
- 恢复后 inbox / queued prompt 是否保留；`agent/*` 是实时控制状态，不保证随会话日志恢复。

已在 Docker 镜像中验证（2026-11-05）：镜像构建成功，`build:official` 9 个 gate 全部通过，session-controller 40/40；web profile 加载 handoff 插件后，A→B→A 的回合全部完成，A 回到 stale generation 时日志为 `handoff preflight {action:"rebuilt",state:"stale",turnState:"closed"}`，并出现 `rebuild started/finished`。详见 [dockerfiles/README_zh.md](./dockerfiles/README_zh.md#8-验证状态)。

本目录已针对 `dsh-v0.2.1-rc.2`（commit `687f282e8625c6b8d11ff58211a90524be2e4317`）生成源码补丁 [0001-stateless-handoff.patch](./dockerfiles/0001-stateless-handoff.patch)，做法与 deployment cookbook all-in-one 一致：clone 固定 tag、校验 commit、`git apply` 后构建。补丁：

- 保留 `ctx.agents.create/resume` 返回的 `AgentHandle`，并按 Session 保存；
- 新增幂等的 `invalidateGeneration(sessionId)` 和 `resumeGeneration(sessionId)`；
- 在 `SessionCommandController.prompt` 中、`resolveAgent` 之后、admission 之前调用 `sessionHandoff.beforePrompt(sessionId)`；`rebuilt` 时重新 resolve Agent；`steer` 跳过。

补丁已通过 `git apply --check`，并提供了从源码构建的 [Dockerfile](./dockerfiles/Dockerfile)，但尚未在本仓库实际构建/运行 DSH。补丁针对固定 tag，升级 DSH 时需要重新 clone、`git apply --check` 并复核插入点；不要假设它直接适用于最新版本。

## 8. 测试

```bash
make setup   # 安装基础示例锁定的 peer 依赖
make check   # node --check + node --test
```

测试覆盖：

- EventId 冲突后句柄永久 conflicted、拒绝后续写入；
- 后台 drain 冲突丢弃未提交批次，而不是继续重试；
- `releaseWriter` 关闭写句柄并释放进程内 claim；
- `writerCursor` 返回本副本写句柄的持久化游标；
- `handoffCheck` 返回 `fresh` / `stale` / `local-ahead` / `not-found` 和三态 `turnState`；
- 空日志返回 `turnState: 'none'`，不会再被当成“未结束回合”；
- `handoffCheck` 的读取成本：`fresh` / `local-ahead` 只发 1 次 `DescribeEvents`，`stale` 发 2 次；
- 两个副本在回合边界交接后，旧 writer 的下一轮写入冲突并停止；
- 控制器：`preflight` 的全部决策分支，包括 `fresh + open + running` 放行、`fresh + open + idle` 拒绝、`stale + running` 拒绝重建；`recover` 的重建顺序、并发重建合并、`invalidate` / `releaseWriter` 失败时不 `resume`、`attachConflictRecovery` 的事件路由；
- `dsh-handoff`：generation port 校验、`writerCursor` 接线、`flush` 透传、liveness 端口接线、从 `ctx.agents` / `ctx.sessionProjections` 推导回合状态、冲突事件接线；
- 集成插件：`apply` 注册 `sessionHandoff` 和冲突监听，冲突走 `invalidateGeneration` → `resumeGeneration`；
- 端到端：A 的日志落后 → `controller.preflight` 重建 → `resume` 后继续追加；
- 端到端：A 发生写入冲突 → `controller.recover` 重建 → `resume` 后继续追加；
- 瞬时错误仍保留批次重试（与基础插件一致）。

## 9. 文件说明

| 文件 | 说明 |
| --- | --- |
| [`plugin/index.js`](./plugin/index.js) | 参考插件 |
| [`plugin/constants.js`](./plugin/constants.js) | 共享事件名 |
| [`plugin/handoff-controller.js`](./plugin/handoff-controller.js) | 无状态交接状态机 |
| [`plugin/dsh-handoff.js`](./plugin/dsh-handoff.js) | DSH generation port、liveness 端口与 Cordis 接线 |
| [`plugin/dsh-handoff-plugin.js`](./plugin/dsh-handoff-plugin.js) | 运行时集成插件（`.../handoff` 导出） |
| [`plugin/index.test.js`](./plugin/index.test.js) | 插件与端到端测试 |
| [`plugin/handoff-controller.test.js`](./plugin/handoff-controller.test.js) | 控制器测试 |
| [`plugin/dsh-handoff.test.js`](./plugin/dsh-handoff.test.js) | generation port、liveness 与集成插件测试 |
| [`plugin/package.json`](./plugin/package.json) | 依赖声明与 `./handoff` 子路径导出 |
| [`stateless-handoff.patch`](./stateless-handoff.patch) | 相对基础插件的差异 |
| [`dockerfiles/0001-stateless-handoff.patch`](./dockerfiles/0001-stateless-handoff.patch) | DSH 0.2.1-rc.2 源码补丁 |
| [`dockerfiles/Dockerfile`](./dockerfiles/Dockerfile) | 从源码构建带补丁的 DSH 镜像 |
| [`dockerfiles/agent-runtime-session.cordis.yml`](./dockerfiles/agent-runtime-session.cordis.yml) | 加载 persistence + handoff 两个插件 |
| [`dockerfiles/entrypoint.sh`](./dockerfiles/entrypoint.sh) | 与基础示例相同的入口 |
| [`.dockerignore`](./.dockerignore) | 构建时排除 `plugin/node_modules` 链接 |
| [`dockerfiles/README_zh.md`](./dockerfiles/README_zh.md) | 源码获取、构建与验证 |
| [`Makefile`](./Makefile) | `setup` / `check` |
