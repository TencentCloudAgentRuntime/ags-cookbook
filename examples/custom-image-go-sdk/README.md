# custom-image-go-sdk-cookbook

一个最简 Go Demo：演示如何在启动 AGS 实例时动态切换镜像。

实现思路参考 `ags-cookbook/tutorials/yunapi/python/custom.ipynb` 中“启动实例时传入自定义配置”的方式。

## 功能说明
- 使用 `tencentcloud-sdk-go` 调用控制面 API 启动沙箱实例。
- 调用 `StartSandboxInstance` 时，如果设置了 `AGS_RUNTIME_IMAGE`，则通过 `CustomConfiguration.Image` 覆盖工具默认镜像。
- 支持通过 `.env` 配置完整的 `CustomConfiguration`（命令、参数、端口、探针）。
- 使用 `ags-go-sdk` 数据面连接实例并执行代码，退出时自动停止实例。

## 项目结构
- `main.go`：单文件入口
- `.env`：本地配置（已被 `.gitignore` 忽略）
- `.env.example`：配置模板
- `go.mod` / `go.sum`：Go 依赖管理
- `.gitignore`：忽略 `.env` 和构建产物
- `Agents.md`：快速执行说明

## 配置
先复制模板：

```bash
cp .env.example .env
```

关键配置项：
- `TENCENTCLOUD_SECRET_ID` / `TENCENTCLOUD_SECRET_KEY`
- `TENCENTCLOUD_REGION`（默认 `ap-guangzhou`）
- `AGS_TOOL_NAME`（已创建的自定义工具名称）
- `AGS_RUNTIME_IMAGE`（可选，启动时覆盖镜像）
- `AGS_RUNTIME_IMAGE_REGISTRY_TYPE`（可选，`enterprise` 或 `personal`）

CustomConfiguration 扩展配置（`AGS_RUNTIME_IMAGE` 非空时生效）：
- `AGS_CUSTOM_COMMAND`：启动命令，JSON 数组，如 `["/init"]`
- `AGS_CUSTOM_ARGS`：启动参数，JSON 数组，如 `["sleep","infinity"]`
- `AGS_CUSTOM_PORTS`：端口配置，JSON 数组
- `AGS_PROBE_PATH`：探针路径（非空时启用探针）
- `AGS_PROBE_PORT` / `AGS_PROBE_SCHEME`：探针端口和协议
- 更多探针参数见 `.env.example`

> 如果不设置 `AGS_RUNTIME_IMAGE`，会使用工具默认镜像。

## 运行
```bash
go mod tidy
go run .
```

## Quick Start

```bash
make run
```

