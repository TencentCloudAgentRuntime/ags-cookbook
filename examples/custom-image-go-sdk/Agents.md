# Agents

## 目标
运行一个最简 Demo：在启动 sbx 时支持覆盖镜像及完整自定义配置。

## 快速开始
1. 复制配置：`cp .env.example .env`
2. 在 `.env` 填入密钥和工具名
3. 可选配置 `CustomConfiguration` 相关环境变量（见下方）
4. 执行：`go mod tidy`
5. 执行：`go run .`

## .env 配置项一览

| 环境变量 | 说明 | 示例 |
|---|---|---|
| `AGS_RUNTIME_IMAGE` | 覆盖镜像地址（为空则用工具默认） | `tkeai.tencentcloudcr.com/ns/img:latest` |
| `AGS_RUNTIME_IMAGE_REGISTRY_TYPE` | 镜像仓库类型 | `enterprise` / `personal` |
| `AGS_CUSTOM_COMMAND` | 启动命令，JSON 数组 | `["/init"]` |
| `AGS_CUSTOM_ARGS` | 启动参数，JSON 数组 | `["sleep","infinity"]` |
| `AGS_CUSTOM_PORTS` | 端口配置，JSON 数组 | `[{"Name":"http","Protocol":"TCP","Port":80}]` |
| `AGS_PROBE_PATH` | 探针路径（非空时启用探针） | `/health` |
| `AGS_PROBE_PORT` | 探针端口 | `49999` |
| `AGS_PROBE_SCHEME` | 探针协议 | `HTTP` |
| `AGS_PROBE_READY_TIMEOUT_MS` | 就绪超时（毫秒） | `30000` |
| `AGS_PROBE_TIMEOUT_MS` | 单次探测超时（毫秒） | `1000` |
| `AGS_PROBE_PERIOD_MS` | 探测间隔（毫秒） | `1000` |
| `AGS_PROBE_SUCCESS_THRESHOLD` | 成功阈值 | `1` |
| `AGS_PROBE_FAILURE_THRESHOLD` | 失败阈值 | `100` |

## Demo 行为
1. 创建 AGS 控制面客户端
2. 构造 `StartSandboxInstanceRequest`
3. 当 `AGS_RUNTIME_IMAGE` 非空时，从 `.env` 读取并填充 `CustomConfiguration`（镜像/命令/参数/端口/探针）
4. 启动 sbx，输出实例 ID
5. 数据面连接 sbx 并执行代码
6. 程序退出时自动停止实例

## 文件
- `main.go`：主流程
- `.env`：本地配置（已被 `.gitignore` 忽略）
- `.env.example`：模板配置
- `go.mod` / `go.sum`：Go 依赖管理
- `.gitignore`：忽略 `.env` 和构建产物
- `README.md`：中文说明
