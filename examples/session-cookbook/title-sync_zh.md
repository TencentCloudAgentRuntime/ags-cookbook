# 会话标题同步

[English](./title-sync.md)

适用于 session-cookbook 里所有把框架会话存进云端 Session 的示例（DSH 基础与切换实现、pi 文件/RPC 与切换实现）。各示例的 README 只链接到本文。

## 解决什么问题

框架里改了会话标题，云端 Session 顶层的 `Title` 字段却没变。结果是：

- 在云端控制台或别的客户端看到的标题和框架里不一致；
- 新启动的 DSH 实例列出会话时，因为本机还没有标题缓存，显示为"未命名"。

## 现在的行为

**写入。** 框架产生一次新的改名事件，并通过 `AppendEvent` 成功保存后，再调用一次 `ModifySession` 把 `Title` 更新为同一个值。事件没保存成功，`Title` 就不会动。

**显式清空。** pi 可以把名称清空。清空会被当作一次改名，`Title` 被明确设为空串。云端服务在后续用户消息到来时会自动用消息内容生成一个兜底标题；为了让"清空"保持有效，清空之后每追加一条用户消息，会再调用一次 `ModifySession` 把标题压回空串。

**为什么清空能在重启后依然有效。** 每次改名事件的 `StateDelta` 里会带一个 `sessionTitleSync` 标记（含版本号、事件序号和标题）。新的进程读到这个标记，就知道这个会话的标题是我们同步过的，不会把空标题当成"没设置"。

**读取只读不写。** 读取和列举会话从不调用 `ModifySession`，也不补写历史会话的标题。没有 `sessionTitleSync` 标记的存量会话保持原样，不迁移。

**DSH 冷启动列表。** 新实例本地没有标题缓存时，列表会使用云端列表里的 `Title` 来显示。只要框架自己已经有标题（本机缓存或活跃会话），就以框架的为准。这一步只读云端已有字段，不会重放历史。

## 失败时会怎样

| 情况 | 行为 |
| --- | --- |
| `ModifySession` 失败（例如标题服务暂时不可用） | 当前这次保存会报错，**即使事件本身已经保存成功**；待同步的标题被记下，下一次保存时重试 |
| 重试之前又产生了更新的标题 | 新标题取代旧标题，旧标题不会被重试写回 |
| 另一个实例已经写了更新的标题 | 本实例读到云端更新的 `sessionTitleSync` 标记后，放弃自己待重试的旧标题 |
| 两个实例几乎同时改名 | `ModifySession` 没有版本条件，**后到的写入生效**。这个窗口无法消除，只能保证不会用已知更旧的标题覆盖更新的 |
| `CustomState`、`Extensions` 不是合法 JSON | 按"没有标记"处理，不影响读取和正常保存 |
| 改名事件的 `StateDelta` 不是 JSON 对象 | 发送前直接报错，错误码 `invalid-title-event`，**不可重试**（同样的内容重试不会成功），避免写出损坏的状态 |

标题服务故障会让保存报错，这是有意的选择：同步失败不会被静默吞掉。代价是标题服务长时间不可用时，会话的保存会持续失败，直到它恢复。

## 额外的请求成本

- 每次改名：多 1 次 `ModifySession`。
- 显式清空之后，每条用户消息：多 1 次 `ModifySession`。
- 读取、列举：不增加请求。

## 实现位置与同步约定

核心逻辑在 `session-titles.js`。为了让每个示例目录都能独立构建，**每个目录各带一份完全相同的副本**：

- `pi/extension/session-titles.js`
- `pi/reference/pi-1.4.0-stateless-handoff/extension/session-titles.js`
- `deepseek-harness/dsh-0.2.1-rc.2/plugin/session-titles.js`
- `deepseek-harness/reference/dsh-0.2.1-rc.2-stateless-handoff/plugin/session-titles.js`

DSH 的两个目录还各带一份 `cloud-title-hints.js`（列表显示用）。

修改任何一份都要同步到其余副本。每个目录的 `session-titles.test.js` 里有一个测试会比较这些副本，不一致就会失败。

内存里按会话保存的同步状态，会在会话被销毁时释放（DSH 在 `session/disposed` 时调用 `forget`）。
