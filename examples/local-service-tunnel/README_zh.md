# 本地服务隧道

这个示例解决一个常见问题：沙箱里的程序需要调用你本机或内网里的 HTTP 服务，但沙箱网络不能直接访问这些地址。

运行后，沙箱里的程序只需要请求 `http://127.0.0.1:18080`。请求会被转发到你本机运行的 `ags-tunnel-client.py`，再由本机 client 去访问真正的服务，比如内网 LLM 网关、工具服务或 reward service。服务地址和访问凭据都留在你的内网侧，沙箱可以继续使用 `NETWORK_MODE=SANDBOX`。

一个本机 `ags-tunnel-client.py` 进程可以同时连接多个沙箱。多个连接共用同一份白名单策略。

Claude Code 只是本目录里的演示程序。这个隧道能力不依赖 Claude Code，你可以把它接到自己的程序里。

## 架构

```mermaid
flowchart LR
  subgraph sandbox["沙箱内"]
    envd["/envd<br/>用于 commands.run / exec"]
    workload["你的程序<br/>本示例用 Claude Code 演示"]
    server["ags-tunnel-server<br/>沙箱内转发进程"]
    workload -->|"HTTP 127.0.0.1:18080"| server
  end

  subgraph local["沙箱外：用户本机 / 内网"]
    client["ags-tunnel-client.py<br/>白名单校验 + 凭据注入"]
    upstream["真实 HTTP 服务<br/>LLM 网关 / 工具服务 / reward service"]
    client -->|"带本机凭据请求"| upstream
  end

  client <-->|"沙箱暴露端口 18081<br/>WebSocket /ws"| server
```

## 沙箱里启动什么

创建 AGS custom tool 时，主进程启动命令配置为：

```json
{
  "Command": ["/bin/sh"],
  "Args": [
    "-lc",
    "/envd -port 49983 >/tmp/envd.log 2>&1 & exec /mnt/tunnel/bin/ags-tunnel-server"
  ]
}
```

这条命令会同时启动两件事：

- `/envd`：用于 `commands.run()` 和调试执行命令。
- `ags-tunnel-server`：接收沙箱内程序发来的 HTTP 请求，并通过 WebSocket 交给本机 client。

`/envd` 来自 envd 镜像卷，`ags-tunnel-server` 来自隧道二进制镜像卷。`scripts/run.py` 会创建对应的镜像卷挂载，并声明沙箱暴露端口。

健康检查会访问 envd 的 `GET /health`，端口是 `49983`。`ags-tunnel-server` 在沙箱内监听：

- `127.0.0.1:18080`：给沙箱内程序调用。
- `0.0.0.0:18081`：作为沙箱暴露的 WebSocket control port。

## 请求怎么走

```mermaid
sequenceDiagram
  box 沙箱内
    participant W as 程序
    participant S as ags-tunnel-server
  end
  box 用户本机 / 内网
    participant C as ags-tunnel-client.py
    participant U as 内网上游
  end

  C->>S: 建立 WebSocket /ws
  W->>S: HTTP 127.0.0.1:18080/v1/messages
  S->>C: request frame
  C->>C: 校验 method、path、目标 host/IP、port
  C->>C: 丢弃沙箱传来的 auth header，注入本机凭据
  C->>U: 请求真实服务
  U-->>C: HTTP 响应
  C-->>S: 响应数据
  S-->>W: HTTP response
```

这个示例转发的是 HTTP 请求，不是通用 TCP 隧道。这样做的好处是本机 client 可以在转发前检查 method、path、host、IP/CIDR、port 和 header，不会把沙箱变成一个能随意访问内网的入口。

## 文件结构

```text
tunnel/server/              沙箱内运行的隧道 server
tunnel/ags-tunnel-client.py 本机隧道 client 命令行入口
tunnel/ags_tunnel_client.py 可 import 的 Python client 模块，方便按需修改
scripts/run.py              创建 tool、启动沙箱实例、启动本机 client
scripts/cleanup.py          停止沙箱实例；DELETE_TOOL=1 时删除 tool
scripts/build-claude-code-dir.sh
                            构建 Linux amd64 Claude Code 演示目录
scripts/build-images.sh     构建并推送主镜像、隧道镜像、演示程序镜像
config/tunnel-policy.yaml   白名单策略
config/tunnel-sessions.yaml 可选；一个本机 client 连接多个沙箱时使用
```

## 最短运行步骤

```bash
cd examples/local-service-tunnel
python3 -m pip install -r requirements.txt
cp .env.example .env
```

填写 `.env`：

```bash
TENCENTCLOUD_SECRET_ID=<your_tencentcloud_secret_id>
TENCENTCLOUD_SECRET_KEY=<your_tencentcloud_secret_key>
TENCENTCLOUD_REGION=ap-guangzhou
ROLE_ARN=qcs::cam::uin/xxx:roleName/xxx
MAIN_IMAGE_REF=ccr.ccs.tencentyun.com/xxx/local-service-tunnel-main:20260626
TUNNEL_IMAGE_REF=ccr.ccs.tencentyun.com/xxx/ags-tunnel-bin:20260626
WORKLOAD_IMAGE_REF=ccr.ccs.tencentyun.com/xxx/demo-workload-claude-code:20260626
DEEPSEEK_API_KEY=<your_upstream_api_key>
```

需要自己构建或更新镜像时执行：

```bash
./scripts/build-images.sh main
./scripts/build-images.sh tunnel
./scripts/build-claude-code-dir.sh
./scripts/build-images.sh workload
```

`build-claude-code-dir.sh` 会在 Linux amd64 容器里完成安装，并输出 `dist/claude-code-linux-amd64/claude-code`。最终传入演示程序镜像的目录只包含 Claude Code launcher 和 Linux 二进制：

```text
dist/claude-code-linux-amd64/claude-code/
  bin/claude
  claude/bin/claude
```

Node.js、npm、`node_modules` 只在构建阶段使用，不会复制进演示程序镜像。如果你已有等价的 Linux amd64 Claude Code 目录，可以在构建演示程序镜像前设置 `CLAUDE_CODE_DIR=/path/to/claude-code`。

运行：

```bash
make run
```

`scripts/run.py` 会完成完整演示流程：创建 AGS custom tool、启动沙箱实例、获取沙箱端口访问 token、启动本机隧道 client，然后调用一次沙箱里的 `/demo/run`。

如果只想把隧道拉起来，不运行 Claude Code demo，可以设置 `RUN_DEMO=0`。

期望 demo 输出：

```text
DEMO_OUTPUT=.state/demo-output.json
```

这个 JSON 文件里应包含 `local-service-tunnel-ok`。

清理：

```bash
make cleanup
DELETE_TOOL=1 make cleanup
```

## 白名单

本机 client 只读取 YAML 策略文件。默认文件是 `config/tunnel-policy.yaml`，可通过 `AGS_TUNNEL_POLICY_FILE` 覆盖。

```yaml
upstream_base: "https://example.internal/v1"
allow_insecure_upstream: false
allowed_upstream_hosts:
  - "example.internal"
allowed_upstream_ports:
  - 443
allowed_ip_cidrs:
  - "10.0.0.0/8"
allowed_paths:
  - "/v1/messages"
allowed_path_prefixes: []
allowed_methods:
  - "POST"
```

如果同时配置 `allowed_upstream_hosts` 和 `allowed_ip_cidrs`，两个条件都必须通过。不要把白名单放宽成通配配置。

本机 client 可以同时连接多个沙箱。多个连接仍然共用同一份白名单。需要连接多个沙箱时，使用 `--session-file config/tunnel-sessions.yaml` 指定连接清单；如果需要更复杂的白名单逻辑，直接修改 `tunnel/ags_tunnel_client.py` 里的 `TunnelPolicy`。

## 白名单验证

这个测试验证两件事：允许的路径能访问到本机服务，不在白名单里的路径会被拦截。

测试会启动一个临时本机 HTTP 服务，然后通过 envd 在沙箱内执行 `curl`：

```bash
RUN_ALLOWLIST_TEST=1 make run
make cleanup
```

期望文件：

```text
.state/allowlist-allowed.txt
.state/allowlist-denied.txt
```

期望结果：

- `/allowlist-ok` 返回 `HTTP/1.1 200 OK`。
- `/blocked` 返回 `HTTP/1.1 502 Bad Gateway`。

## 多轮请求验证

这个测试会启动一个本机模拟 LLM 服务，然后从沙箱内通过隧道连续发送两次 `/v1/messages` 请求。第二次请求会带上第一轮的响应，用来确认同一条隧道连接可以承载连续请求。

```bash
RUN_MULTI_TURN_TEST=1 make run
make cleanup
```

期望文件：

```text
.state/multi-turn-output.txt
```

期望结果：

- 第一轮请求返回 `turn-1-ok`。
- 第二轮请求只有在 conversation history 中带上 `turn-1-ok` 时才返回 `turn-2-ok`。

## Claude Code 演示

本目录用 Claude Code 做演示。它运行在非交互 `-p` 模式下，所以默认只是一次 prompt 调用。需要验证连续请求时，用上面的 `RUN_MULTI_TURN_TEST=1`。

如果 prompt 需要 Claude Code 调用工具，可以设置：

```bash
CLAUDE_PERMISSION_MODE=bypassPermissions \
PROMPT='分析今天的天气和股票表现，最后输出 local-service-tunnel-ok' \
make run
```

上面的权限参数只是为了让本示例里的 Claude Code demo 少一点交互确认。实际接入自己的程序时，不需要关心 Claude Code；程序把原本要发往内网服务的 HTTP 请求发到 `http://127.0.0.1:18080` 即可。

## 安全边界

- 真实服务的访问凭据保留在用户本机。
- 沙箱发出的请求会先经过本机 client 校验。
- 本机 client 会丢弃沙箱传来的 auth header，再注入本机凭据。
- YAML 策略限制真实服务的 host、IP/CIDR、port、path、method 和可转发 header。
- 多个沙箱连接共用同一份 YAML 白名单，连接清单不能放宽策略。
