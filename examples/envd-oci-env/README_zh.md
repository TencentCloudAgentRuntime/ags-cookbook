# 使用 envd 保留 OCI 镜像环境变量

本 cookbook 说明：当 envd 是容器 1 号进程时，为什么 OCI 镜像中的环境变量可能
无法传递给 envd 启动的命令，以及如何按需开启完整环境继承。

示例可以直接运行：它会使用仓库自带的 envd 二进制构建镜像、预热镜像、创建两个
临时 AGS 沙箱、验证开关关闭和开启的行为、检查覆盖优先级，最后清理临时资源。

## 问题原因

OCI 运行时会把镜像 `ENV` 交给容器初始进程：

```text
OCI 镜像 ENV -> envd（PID 1）-> envd 启动的命令
```

envd 默认不会把自己的完整环境隐式复制给子进程，而是重新组装环境：先设置
`PATH`、`HOME`、`USER`、`LOGNAME` 等身份变量，再追加 `/init` 环境变量和单次
执行请求提供的环境变量。

因此，envd 自己可能看得到镜像环境变量，但通过 envd 启动的命令看不到。

## 解决方案

`utils/envd/envd` 中的二进制增加了一个按需开启的开关：

```text
EXEC_ENABLE_ALL_ENV=1
```

应把该开关设置到 envd 自身，通常通过 `CustomConfiguration.Env` 设置。开启后，
envd 会先使用 PID 1 的完整环境初始化每个子进程，然后再追加原有显式变量。

实际优先级从低到高为：

```text
envd PID 1 环境
< PATH/HOME/USER/LOGNAME
< /init 环境变量
< 单次执行请求环境变量
```

未设置该开关或值不是 `1` 时，默认行为保持不变。

> 安全提示：开启后，envd 环境中的所有变量都会暴露给 envd 启动的命令。不要把
> 控制面凭据放入容器环境；如果只需传递少量白名单变量，应改用 `/init` 或单次
> 执行请求的环境变量。

## 前置条件

- Linux 或 macOS Bash
- Docker，并具备向目标镜像仓库推送镜像的权限
- 已配置目标 AGS 账号的 `agr` CLI
- 环境变量中存在 `TENCENTCLOUD_SECRET_ID` 和
  `TENCENTCLOUD_SECRET_KEY`
- AGS 可用于拉取目标镜像的 CAM 角色
- x86-64 基础镜像，并包含 `/bin/sh`、`/usr/bin/nice`、
  `/usr/bin/ionice` 和 `readlink`

本示例默认使用 `ubuntu:22.04`。

## 配置

进入本目录后执行：

```bash
make setup
```

编辑 `.env`：

| 变量 | 必填 | 含义 |
|---|---:|---|
| `TENCENTCLOUD_SECRET_ID` | 是 | 腾讯云 API 凭据 |
| `TENCENTCLOUD_SECRET_KEY` | 是 | 腾讯云 API 凭据 |
| `TENCENTCLOUD_REGION` | 是 | AGS 地域，例如 `ap-guangzhou` |
| `ENVD_DEMO_IMAGE` | 是 | 本地可推送且 AGS 可拉取的镜像地址 |
| `ENVD_IMAGE_REGISTRY_TYPE` | 是 | `personal` 或 `enterprise` |
| `AGS_ROLE_ARN` | 是 | AGS 拉取镜像使用的 CAM 角色 |
| `AGS_EXEC_USER` | 否 | 镜像中已存在的用户，默认 `root` |
| `BASE_IMAGE` | 否 | 应用基础镜像，默认 `ubuntu:22.04` |

`.env` 已被 Git 忽略，切勿提交真实凭据。

## 构建并发布

校验二进制、构建镜像并推送：

```bash
make verify
make build
make push
```

Docker 构建上下文必须是仓库根目录，因为 Dockerfile 会复制
`utils/envd/envd`；Makefile 已自动处理。

## 运行验证

```bash
make run
```

`make run` 会：

1. 预热 `ENVD_DEMO_IMAGE` 并等待状态变为 `Success`。
2. 创建一个未设置 `EXEC_ENABLE_ALL_ENV` 的临时 Tool。
3. 创建另一个设置了 `EXEC_ENABLE_ALL_ENV=1` 的临时 Tool。
4. 分别创建最长 20 分钟的临时沙箱。
5. 确认关闭开关时，子进程看不到 `ENVD_IMAGE_ONLY`。
6. 确认开启开关时 envd 是 PID 1，并能继承镜像环境和 AGS 运行时环境。
7. 确认单次执行请求可以覆盖继承的镜像值。
8. 无论成功或失败，均删除两个沙箱和 Tool。

预期输出包含：

```text
PASS: image env is absent when inheritance is disabled
PASS: PID 1, image env, and runtime env verified
PASS: request env overrides inherited image env
All envd inheritance checks passed
```

完整执行构建、推送、预热和验证：

```bash
make all
```

## 适配已有镜像

保留应用镜像原有的 `ENV`，加入仓库提供的二进制：

```dockerfile
COPY utils/envd/envd /usr/bin/envd
RUN chmod 0755 /usr/bin/envd
ENTRYPOINT ["/usr/bin/envd"]
```

然后在 AGS 自定义 Tool 中配置：

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

如果 envd 由包装进程启动而不是直接作为 PID 1，envd 继承的是包装进程的环境；
还需确认包装进程没有过滤镜像环境变量。

## 常见问题

- **`MissingParameter.RoleArn`**：设置 `AGS_ROLE_ARN`，确保该角色可以读取目标
  镜像仓库。
- **预热提示镜像不存在**：检查镜像地址，并确认
  `ENVD_IMAGE_REGISTRY_TYPE` 与仓库类型一致。
- **exec 返回 internal error**：将 `AGS_EXEC_USER` 设置为镜像中实际存在的用户。
- **Tool 一直未就绪**：确认 envd 监听 `49983`，且镜像包含前置条件中列出的命令。
- **发现不应暴露的敏感变量**：关闭开关，只通过 `/init` 或单次执行请求传递白名单
  变量。
