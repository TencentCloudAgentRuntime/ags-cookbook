# 使用 envd 保留 OCI 镜像环境变量

容器镜像可以通过 `ENV` 定义环境变量。

envd 作为容器的 1 号进程时，可以读取这些变量。但是，原版 envd 启动新命令时，
不会自动把这些变量传下去。新命令因此可能读不到镜像中的 `ENV`。

本 cookbook 提供一个修改后的 envd，并说明如何把它加入客户镜像。

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

原版 envd 只加入基础变量和明确指定的变量，不会复制 envd 自己收到的完整环境。
因此，OCI 运行时交给 envd 的镜像 `ENV` 会在这里丢失。

## 我们修改了什么

仓库中的 `utils/envd/envd` 增加了以下开关：

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

## 如何使用

### 1. 把 envd 加入镜像

仓库中的二进制适用于 Linux/amd64。

```dockerfile
COPY utils/envd/envd /usr/bin/envd
RUN chmod 0755 /usr/bin/envd
ENTRYPOINT ["/usr/bin/envd"]
```

Docker 构建上下文需要包含 `utils/envd/envd`。本示例的 Makefile 已经使用仓库根
目录作为构建上下文。

### 2. 让 envd 作为 1 号进程

在 AGS 自定义 Tool 中，把启动命令设置为：

```json
{
  "Command": ["/usr/bin/envd"]
}
```

如果先启动包装脚本，再由包装脚本启动 envd，envd 只能继承包装脚本保留下来的
环境变量。此时需要确认包装脚本没有过滤镜像 `ENV`。

### 3. 开启完整环境继承

在同一个 AGS 自定义 Tool 中设置：

```json
{
  "Command": ["/usr/bin/envd"],
  "Env": [
    {
      "Name": "EXEC_ENABLE_ALL_ENV",
      "Value": "1"
    }
  ]
}
```

重建 Tool 并启动沙箱后，通过 envd 启动的命令就可以读取镜像 `ENV`。

例如：

```bash
agr instance exec <instance-id> --user root -- printenv MODEL_DIR
```

预期输出：

```text
/models
```

## 同名变量如何覆盖

不同入口可以设置同一个环境变量。后设置的值优先：

| 来源 | 含义 | 作用范围 |
|---|---|---|
| envd 的进程环境 | OCI 镜像 `ENV` 和 AGS `CustomConfiguration.Env` | 所有后续命令 |
| 基础身份变量 | envd 根据执行用户设置的 `PATH`、`HOME`、`USER`、`LOGNAME` | 所有后续命令 |
| 沙箱初始化变量 | 平台可以在沙箱启动时调用 envd 的 `/init` 接口，设置公共默认值 | 初始化后的所有命令 |
| 当前命令的变量 | 例如 `agr instance exec --env KEY=VALUE` | 只影响当前命令，优先级最高 |

本场景不需要客户手动调用 `/init`。如果当前命令需要临时覆盖镜像中的值，直接使用
`--env`：

```bash
agr instance exec <instance-id> \
  --user root \
  --env MODEL_DIR=/temporary-models \
  -- printenv MODEL_DIR
```

## 安全提示

该开关会把 envd 的所有环境变量传给新命令，其中可能包含密码、Token 或代理配置。

只有确认 envd 环境中的变量都允许被沙箱命令读取时，才应开启该功能。如果只需传递
少量变量，可以使用 `agr instance exec --env`，不必开启完整环境继承。

## 验证示例

需要准备：

- Bash、Docker 和 `agr`
- 可推送的个人版或企业版镜像仓库
- AGS 拉取镜像使用的 CAM 角色
- x86-64 基础镜像，其中包含 `/bin/sh`、`/usr/bin/nice`、
  `/usr/bin/ionice` 和 `readlink`

创建配置文件：

```bash
make setup
```

编辑 `.env`，填写腾讯云凭据、地域、镜像地址、镜像仓库类型和
`AGS_ROLE_ARN`。`.env` 已被 Git 忽略，不能提交真实凭据。

然后执行：

```bash
make verify
make build
make push
make run
```

`make run` 会验证开关关闭、开关开启和当前命令覆盖三种情况。创建的临时沙箱和
Tool 会自动清理。

预期结果：

```text
PASS: image env is absent when inheritance is disabled
PASS: PID 1, image env, and runtime env verified
PASS: command-specific env overrides inherited image env
All envd inheritance checks passed
```

## 常见问题

- **`MissingParameter.RoleArn`**：设置 `AGS_ROLE_ARN`，确保该角色可以读取目标
  镜像仓库。
- **预热提示镜像不存在**：检查镜像地址，并确认
  `ENVD_IMAGE_REGISTRY_TYPE` 与仓库类型一致。
- **exec 返回 internal error**：将 `AGS_EXEC_USER` 设置为镜像中实际存在的用户。
- **Tool 一直未就绪**：确认 envd 监听 `49983`，且镜像包含验证示例中列出的命令。
- **发现不应暴露的敏感变量**：关闭开关，只向具体命令传递允许使用的变量。
