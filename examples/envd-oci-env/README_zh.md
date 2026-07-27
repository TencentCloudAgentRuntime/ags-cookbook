# 使用 envd 保留 OCI 镜像环境变量

容器镜像可以通过 `ENV` 定义环境变量。

envd 作为容器的 1 号进程时，可以读取这些变量。但是，原版 envd 启动新命令时，
不会自动把所有变量传下去。新命令因此可能读不到镜像中的 `ENV`。

本 cookbook 提供修改后的 envd 源码，并说明如何自行编译和加入应用镜像。

## 问题现象

假设镜像中有以下配置：

```dockerfile
ENV MODEL_DIR=/models
ENTRYPOINT ["/usr/bin/envd"]
```

容器启动后，envd 可以读取 `MODEL_DIR=/models`。随后，AGS 通过 envd 启动应用或
Shell 命令。这些新命令可能读不到 `MODEL_DIR`。

```text
镜像 ENV -> envd（可以读取）-> 新命令（无法读取）
```

## 问题原因

envd 创建新进程时，会明确设置这个进程的环境变量列表。

原版 envd 只加入基础变量，以及为沙箱或当前命令明确设置的变量，不会复制 envd
自己收到的完整环境。因此，OCI 运行时交给 envd 的镜像 `ENV` 会在这里丢失。

## 我们修改了什么

仓库同时提供两个可以独立构建的源码版本：

| envd 版本 | 源码路径 | 公开源码版本 |
|---|---|---|
| `0.5.4` | `utils/envd/versions/0.5.4` | `017de20162f1d9ea340d3767eba2c43cd0dd8c33` |
| `0.2.11` | `utils/envd/versions/0.2.11` | `1af78dd38a2cedce7f513c26aa2deb443cb0f0ef` |

两个版本都增加了以下开关：

```text
EXEC_ENABLE_ALL_ENV=1
```

开关开启后，envd 会先复制自己的完整环境，再启动新命令：

```text
镜像 ENV -> envd（可以读取）-> 新命令（可以读取）
```

代码行为等价于：

```go
if os.Getenv("EXEC_ENABLE_ALL_ENV") == "1" {
    childEnv = append(childEnv, os.Environ()...)
}
```

只有值为 `1` 时才会开启。没有设置该变量，或者设置成其他值，envd 都保持原来的
行为。

`0.5.4` 源码还包含后续公开上游的 cgroup 检测修复。它会在启用 cgroup v2
进程管理前识别 cgroup v1。缺少该修复时，envd 在 cgroup v1 容器中启动子进程
可能报 `bad file descriptor`。

## 选择版本

envd 不会自动协商版本。请使用连接 envd 的客户端或集成方案明确要求的版本。
如果两者都没有指定版本，可以使用示例默认的 `0.5.4`。

在 `.env` 中设置：

```dotenv
ENVD_VERSION=0.5.4
```

或者：

```dotenv
ENVD_VERSION=0.2.11
```

两个版本应使用不同的镜像标签，例如：

```dotenv
ENVD_DEMO_IMAGE=ccr.ccs.tencentyun.com/your-namespace/your-repository:envd-0.5.4
```

Makefile 会自动选择对应的源码目录、Go 工具链和源码版本。本示例把选择参数命名为
`ENVD_VERSION`；直接在 `utils/envd` 下执行命令时，同一参数名为 `VERSION`。

## 把 envd 编译到镜像中

示例 Dockerfile 使用多阶段构建。与版本选择相关的部分如下：

```dockerfile
ARG GO_VERSION=1.25.4
ARG BASE_IMAGE=ubuntu:22.04

FROM golang:${GO_VERSION}-bookworm AS envd-builder
ARG ENVD_VERSION=0.5.4
WORKDIR /workspace
COPY utils/envd/versions/${ENVD_VERSION}/src ./src
COPY utils/envd/versions/${ENVD_VERSION}/shared ./shared
WORKDIR /workspace/src
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 \
    go build -trimpath -buildvcs=false -a -o /out/envd .

FROM ${BASE_IMAGE}
COPY --from=envd-builder /out/envd /usr/bin/envd
RUN chmod 0755 /usr/bin/envd
ENV EXEC_ENABLE_ALL_ENV=1
ENTRYPOINT ["/usr/bin/envd"]
```

最终镜像只包含编译后的 envd，不包含 Go 工具链。

## 配置 AGS

让 envd 成为容器的 1 号进程：

```json
{
  "Command": ["/usr/bin/envd"]
}
```

需要在 envd 启动前开启完整环境继承。可以写入镜像：

```dockerfile
ENV EXEC_ENABLE_ALL_ENV=1
```

也可以写入 AGS Tool 的容器环境配置：

```json
{
  "Env": [
    {
      "Name": "EXEC_ENABLE_ALL_ENV",
      "Value": "1"
    }
  ]
}
```

两种方式都会让开关进入 envd 这个 1 号进程的环境，不需要同时设置。如果两处设置
了同名变量，AGS 容器环境配置会覆盖镜像中的值。

重新构建镜像和 Tool 后，通过 envd 启动的命令就可以读取镜像 `ENV`：

```bash
agr instance exec <instance-id> --user root -- printenv MODEL_DIR
```

预期输出：

```text
/models
```

不要使用 `agr instance exec --env EXEC_ENABLE_ALL_ENV=1` 开启该能力。这个值只会
随某一次子进程请求传入，此时 envd 已经启动，无法再改变 envd 的继承行为。

## 同名变量如何覆盖

不同入口可以设置同一个环境变量。后设置的值优先：

| 来源 | 含义 | 作用范围 |
|---|---|---|
| envd 的进程环境 | 容器运行时交给 1 号进程的最终值，包括镜像 `ENV` 和 AGS `CustomConfiguration.Env` | 所有后续命令的起始环境 |
| 基础身份变量 | envd 设置的 `PATH`、`HOME`、`USER` 和 `LOGNAME` | 所有后续命令 |
| 沙箱启动默认值 | 沙箱平台初始化 envd 时提供的公共命令变量（如果有） | 所有后续命令 |
| 当前命令的变量 | `agr instance exec --env KEY=VALUE` | 只影响当前命令，优先级最高 |

为一条命令临时覆盖镜像中的值：

```bash
agr instance exec <instance-id> \
  --user root \
  --env MODEL_DIR=/temporary-models \
  -- printenv MODEL_DIR
```

## 在 AGS 中验证

需要准备：

- Bash、Docker 和 `agr`
- 个人版或企业版镜像仓库
- AGS 拉取镜像使用的 CAM 角色
- x86-64 基础镜像，其中包含 `/bin/sh`、`/usr/bin/nice`、
  `/usr/bin/ionice` 和 `readlink`

创建配置文件：

```bash
make setup
```

编辑 `.env`，填写腾讯云凭据、地域、镜像地址、镜像仓库类型、
`AGS_ROLE_ARN` 和 `ENVD_VERSION`。

然后执行：

```bash
make verify
make build
make push
make run
```

`make run` 会预热所选镜像，创建两个临时沙箱，并检查：

- 二进制报告的 envd 版本与选择一致；
- 设置 `EXEC_ENABLE_ALL_ENV=0` 时仍然不继承完整环境；
- 设置 `EXEC_ENABLE_ALL_ENV=1` 后可以读取镜像和沙箱级变量；
- 当前命令设置的值可以覆盖继承值。

示例镜像中包含 `EXEC_ENABLE_ALL_ENV=1`。为了用同一个镜像验证关闭状态，第一个
临时 Tool 会在 `CustomConfiguration.Env` 中设置 `EXEC_ENABLE_ALL_ENV=0`。这也
验证了 AGS 容器环境配置可以覆盖镜像值。第二个 Tool 不覆盖该开关，因此镜像中的
值仍然生效。

临时沙箱和 Tool 会自动清理。

`ENVD_VERSION=0.5.4` 时的预期结果：

```text
PASS: envd 0.5.4 does not inherit image env when disabled
PASS: envd 0.5.4 PID 1, image env, and runtime env verified
PASS: command-specific env overrides inherited image env
All envd inheritance checks passed
```

换用 `ENVD_VERSION=0.2.11` 和另一个镜像标签，再执行一次即可验证第二个版本。

## 常见问题

- **`MissingParameter.RoleArn`**：设置 `AGS_ROLE_ARN`，确保该角色可以读取目标
  镜像仓库。
- **预热提示镜像不存在**：检查镜像地址，并确认
  `ENVD_IMAGE_REGISTRY_TYPE` 与仓库类型一致。
- **exec 返回 internal error**：将 `AGS_EXEC_USER` 设置为镜像中实际存在的用户。
- **Tool 一直未就绪**：确认 envd 监听 `49983`，且镜像包含“在 AGS 中验证”列出的
  命令。
