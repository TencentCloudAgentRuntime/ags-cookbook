# shell2http

一个轻量级的 HTTP 服务，通过 RESTful API 执行 Shell 命令。基于 Go 实现，使用 Nix 管理运行时环境依赖。

## 功能特性

- **HTTP API 执行命令**：通过 POST 请求执行任意 Shell 命令
- **超时控制**：支持自定义超时时间，防止命令长时间阻塞
- **环境变量支持**：可传入额外环境变量，支持命令中的变量展开
- **工作目录指定**：支持指定命令执行的工作目录
- **丰富的运行时工具**：内置 bash、git、nodejs、curl、jq、claude-code 等常用工具

## API 接口

### 健康检查

```
GET /health
```

响应示例：
```json
{
  "status": "ok",
  "time": "2025-01-25T10:00:00Z"
}
```

### 执行命令

```
POST /exec
Content-Type: application/json
```

请求参数：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| command | string | 是 | 要执行的 Shell 命令 |
| timeout | int | 否 | 超时时间（秒），默认 60s，最大 3600s |
| env | object | 否 | 额外的环境变量 |
| workdir | string | 否 | 工作目录 |

请求示例：
```json
{
  "command": "ls -la",
  "timeout": 30,
  "env": {
    "MY_VAR": "hello"
  },
  "workdir": "/workspace"
}
```

响应参数：

| 字段 | 类型 | 说明 |
|------|------|------|
| success | bool | 命令是否执行成功 |
| exit_code | int | 命令退出码 |
| output | string | 标准输出和标准错误合并内容 |
| error | string | 错误信息（失败时） |
| duration_ms | int64 | 执行耗时（毫秒） |
| timeout | bool | 是否超时 |

响应示例：
```json
{
  "success": true,
  "exit_code": 0,
  "output": "total 16\ndrwxr-xr-x 2 root root 4096 ...",
  "duration_ms": 15
}
```

## 环境变量配置

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| PORT | 8080 | 服务监听端口 |
| DEFAULT_TIMEOUT | 60 | 默认命令超时时间（秒） |
| MAX_TIMEOUT | 3600 | 最大允许超时时间（秒） |

## 内置工具

运行时环境通过 Nix 管理，包含以下工具：

- **Shell**: bash
- **基础工具**: coreutils, findutils, sed, awk, grep, tar, gzip
- **网络工具**: curl, wget
- **文本处理**: jq
- **版本控制**: git
- **运行时**: Node.js 22
- **AI 工具**: claude-code
- **其他**: which, file, tree, procps, stress-ng

## 构建与运行

### Docker 构建

```bash
docker build -t shell2http .
```

### Docker 运行

```bash
docker run -d -p 8080:8080 shell2http
```

### 自定义配置运行

```bash
docker run -d \
  -p 8080:8080 \
  -e DEFAULT_TIMEOUT=120 \
  -e MAX_TIMEOUT=7200 \
  shell2http
```

## 使用示例

```bash
# 健康检查
curl http://localhost:8080/health

# 执行简单命令
curl -X POST http://localhost:8080/exec \
  -H "Content-Type: application/json" \
  -d '{"command": "echo hello"}'

# 带环境变量执行
curl -X POST http://localhost:8080/exec \
  -H "Content-Type: application/json" \
  -d '{"command": "echo $NAME", "env": {"NAME": "world"}}'

# 指定工作目录和超时
curl -X POST http://localhost:8080/exec \
  -H "Content-Type: application/json" \
  -d '{"command": "pwd && ls", "workdir": "/tmp", "timeout": 10}'
```

## 开发

### 本地开发环境

使用 Nix Flakes 进入开发环境：

```bash
nix develop
```

### 构建

```bash
go build -o shell2http main.go
```
