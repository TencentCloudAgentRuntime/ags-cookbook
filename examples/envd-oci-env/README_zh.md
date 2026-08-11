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

仓库提供三个可以独立构建的源码分发版本：

| envd 版本 | 源码路径 | 公开源码版本 |
|---|---|---|
| `0.5.14` | `utils/envd/versions/0.5.14` | `a3fb26eb4344bbaf66c0d2478c086623b560ef41` |
| `0.5.14-modified` | `utils/envd/versions/0.5.14-modified` | `a3fb26eb4344bbaf66c0d2478c086623b560ef41` |
| `0.2.11` | `utils/envd/versions/0.2.11` | `1af78dd38a2cedce7f513c26aa2deb443cb0f0ef` |

`0.5.14` 和 `0.2.11` 增加了以下开关：

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

`0.5.14-modified` 采用不同方式：它记录 envd 启动时的环境和有效身份，并将其作为
命令及文件系统操作的默认值。该分发版本始终继承环境，不受
`EXEC_ENABLE_ALL_ENV` 控制；同时，非特权 envd 无需重新设置自身凭据。二进制报告的
版本仍为 `0.5.14`。

`0.5.14` 源码已经包含上游的 cgroup 检测逻辑。它会在启用 cgroup v2 进程管理
前识别 cgroup v1，避免 envd 启动子进程时报 `bad file descriptor`。

## 选择版本

envd 不会自动协商版本。请使用连接 envd 的客户端或集成方案明确要求的版本。
如果两者都没有指定版本，可以使用示例默认的 `0.5.14`。

在 `.env` 中设置：

```dotenv
ENVD_VERSION=0.5.14
```

或者：

```dotenv
ENVD_VERSION=0.5.14-modified
```

或者：

```dotenv
ENVD_VERSION=0.2.11
```

各源码分发版本应使用不同的镜像标签，例如：

```dotenv
ENVD_DEMO_IMAGE=ccr.ccs.tencentyun.com/your-namespace/your-repository:envd-0.5.14
```

Makefile 会自动选择对应的源码目录、Go 工具链和源码版本。本示例把选择参数命名为
`ENVD_VERSION`；直接在 `utils/envd` 下执行命令时，同一参数名为 `VERSION`。
对于 `0.5.14-modified` 这类带后缀的源码选择器，验证时会去掉后缀，再与
`/usr/bin/envd -version` 比较。

## 把 envd 编译到镜像中

示例 Dockerfile 使用多阶段构建。与版本选择相关的部分如下：

```dockerfile
ARG GO_VERSION=1.25.9
ARG BASE_IMAGE=ubuntu:22.04

FROM golang:${GO_VERSION}-bookworm AS envd-builder
ARG ENVD_VERSION=0.5.14
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

对于按需继承的 `0.5.14` 和 `0.2.11`，需要在 envd 启动前开启完整环境继承。
可以写入镜像：

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
了同名变量，AGS 容器环境配置会覆盖镜像中的值。`0.5.14-modified` 始终继承启动
环境，不需要设置这个开关。

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

- 二进制报告底层 envd 版本（`0.5.14-modified` 对应 `0.5.14`）；
- 按需继承版本在 `EXEC_ENABLE_ALL_ENV=0` 时不继承完整环境，而
  `0.5.14-modified` 仍会继承启动环境；
- 设置 `EXEC_ENABLE_ALL_ENV=1` 后可以读取镜像和沙箱级变量；
- 当前命令设置的值可以覆盖继承值。

示例镜像中包含 `EXEC_ENABLE_ALL_ENV=1`。为了用同一个镜像验证关闭状态，第一个
临时 Tool 会在 `CustomConfiguration.Env` 中设置 `EXEC_ENABLE_ALL_ENV=0`。这也
验证了 AGS 容器环境配置可以覆盖镜像值。第二个 Tool 不覆盖该开关，因此镜像中的
值仍然生效。
对 `0.5.14-modified`，第一个 Tool 改为验证启动环境继承仍然生效，因为该版本不
使用这个开关。

临时沙箱和 Tool 会自动清理。

`ENVD_VERSION=0.5.14` 时的预期结果：

```text
PASS: envd 0.5.14 does not inherit image env when disabled
PASS: envd 0.5.14 PID 1, image env, and runtime env verified
PASS: command-specific env overrides inherited image env
All envd inheritance checks passed
```

换用 `ENVD_VERSION=0.2.11` 和另一个镜像标签可以验证旧版本。设置
`ENVD_VERSION=0.5.14-modified` 可以验证始终启用的启动身份和环境行为，其 PASS
输出中的二进制版本为 `0.5.14`。

## 常见问题

- **`MissingParameter.RoleArn`**：设置 `AGS_ROLE_ARN`，确保该角色可以读取目标
  镜像仓库。
- **预热提示镜像不存在**：检查镜像地址，并确认
  `ENVD_IMAGE_REGISTRY_TYPE` 与仓库类型一致。
- **exec 返回 internal error**：将 `AGS_EXEC_USER` 设置为镜像中实际存在的用户。
- **Tool 一直未就绪**：确认 envd 监听 `49983`，且镜像包含“在 AGS 中验证”列出的
  命令。

---

# 把 OCI `USER` 和 `WORKDIR` 作为命令默认值

上面讲的是镜像的 `ENV`。这一节讲命令需要的另外两项 OCI 配置：**以谁的身份**执行，
**在哪个目录**执行。

需要 `ENVD_VERSION=0.5.14-modified`。

## 现象

假设业务镜像结尾是：

```dockerfile
USER appuser
WORKDIR /opt/app/work
```

而通过 E2B Python SDK 启动命令时不指定 user 和 cwd：

```python
sandbox.commands.run("id; pwd")
```

使用未修改的 envd 时，命令会以 **root** 身份在 **`/root`** 中执行——既不是镜像的
`USER`，也不是它的 `WORKDIR`。用本仓库自带的 fixture 实测：

```text
未修改的 envd 0.5.14:  uid=0      pwd=/root
0.5.14-modified:       uid=10001  pwd=/opt/app/work
```

两个独立原因。身份方面，envd 把自己的 *effective* UID 当作启动身份记录；在 setuid
二进制下该值为 0，于是 root 被误记为默认用户。目录方面，envd 从未记录启动工作目录，
路径解析因此回落到用户 HOME。

## 行为合同

| SDK 调用 | 以谁执行 | 在哪执行 |
|---|---|---|
| `run(cmd)` | 镜像的 OCI `USER` | 镜像的 OCI `WORKDIR` |
| `run(cmd, user="root")` | `root` | 镜像的 OCI `WORKDIR` |
| `run(cmd, cwd="/tmp")` | 镜像的 OCI `USER` | `/tmp` |
| `run(cmd, user="root", cwd="/tmp")` | `root` | `/tmp` |

显式 `user` 可以是业务 rootfs 中任何可解析的用户名。OCI `USER` 即使是纯数字 UID 且
`/etc/passwd` 无该条目，也能作为默认身份正常工作。

`PWD` 始终与进程实际启动的目录一致。若目标用户无权进入解析后的目录，请求会失败，
错误信息同时包含用户和目录。

## envd Image Volume 为什么是 setuid

envd 与业务镜像分开交付，通过 `StorageMounts.Image` 挂载。Image Volume **只提供
文件**：它自己的 OCI `USER`、`WORKDIR`、`ENTRYPOINT`、`CMD`、`ENV` 都不会合并到业务
进程。这些全部由业务镜像提供。

要让 envd 能把命令切换到显式指定的用户，它需要本来不具备的权限——因为 OCI 运行时是以
镜像中非特权的 `USER` 启动它的。权限来自文件元数据：

```text
/usr/bin/envd   owner 0:0   mode 4755
```

内核于是给 envd：

```text
real UID = 镜像的 OCI USER      effective UID = 0
```

envd 记录 **real** 身份作为默认值，并为每个未指定用户的命令降权回该身份。
`Dockerfile.envd-volume` 在镜像层内固化 owner 和 mode，因为挂载是只读的，运行时无法
`chmod`。

两个挂载层面的前提：挂载不能带 `nosuid`，进程必须 `NoNewPrivs=0`。任一条不满足，
setuid 位都会失效。

## 文件

| 文件 | 用途 |
|---|---|
| `Dockerfile.envd-volume` | Image Volume 制品：`scratch` 基础上的 `/usr/bin/envd`，`0:0`、mode `4755` |
| `Dockerfile.fixture-a` | 业务 fixture：`USER appuser`、`WORKDIR /opt/app/work`、多个用户和一个共享组 |
| `Dockerfile.fixture-b` | 业务 fixture：`USER 61234:61235`，无 passwd 条目 |
| `verify-envd-volume.sh` | 在导出的镜像层中检查 `0:0`/`4755` |
| `validate_user_workdir.py` | 断言本体，全部通过 E2B Python SDK |
| `validate_user_workdir.sh` | 准备 AGS 资源、执行断言、清理 |

## 构建与校验

```bash
make envd-volume-build ENVD_VERSION=0.5.14-modified \
    ENVD_VOLUME_IMAGE=<registry>/<namespace>/envd-oci-user-workdir:<唯一 tag>
```

`envd-volume-build` 会先跑 envd 测试套件，再构建，最后校验层元数据。也可以单独校验
已有镜像：

```bash
make envd-volume-verify ENVD_VOLUME_IMAGE=<reference>
```

期望输出：

```text
   tar owner:  0:0
   OK: owner is 0:0
   OK: mode is -rwsr-xr-x (4755), setuid bit present
   sha256:     <二进制 digest>
VERIFY OK: ... carries /usr/bin/envd as 0:0 mode 4755
```

不要把制品打成 `latest`。可变 tag 无法固定到 digest，而 digest 是识别某次具体 envd
构建的唯一依据。

然后构建 fixture 并推送：

```bash
make fixtures-build FIXTURE_A_IMAGE=<ref-a> FIXTURE_B_IMAGE=<ref-b>
make user-workdir-push ENVD_VERSION=0.5.14-modified \
    ENVD_VOLUME_IMAGE=<ref> FIXTURE_A_IMAGE=<ref-a> FIXTURE_B_IMAGE=<ref-b>
```

## 在 AGS 上运行

```bash
make setup            # 然后编辑 .env
make run-user-workdir
```

Tool 以只读方式挂载 Image Volume，并把 `Command` 指向挂载后的二进制：

```text
StorageMounts[0].MountPath                       /opt/envd
StorageMounts[0].StorageSource.Image.Reference   <envd Image Volume>
CustomConfiguration.Image                        <业务 fixture>
CustomConfiguration.Command                      ["/opt/envd/usr/bin/envd"]
```

`ImageRegistryType` 接受 `personal` 或 `enterprise`。请用 `agr schema` 确认当前接受
的取值，不要照抄旧文档。使用 `--storage-mounts` 时 `--role-arn` 为必填，
`Probe.ReadyTimeoutMs` 上限为 `30000`。

`validate_user_workdir.sh` 会删除它创建的所有 Tool 和 Instance（失败时也会），并报告
仍匹配本轮前缀的资源数量。

## 在 AGS 上运行的两个前提

**SDK 会拒绝 AGS 的 API key 格式。** `e2b` 用 `^e2b_[0-9a-f]+$` 校验 API key，而 AGS
签发的是 `ark_` 前缀的 key。请使用 `e2b >= 2.30` 并设置 `E2B_VALIDATE_API_KEY=false`，
或传入 `validate_api_key=False`。2.30 以下版本没有该开关。

**默认用户相关用例需要控制面上报正确的 envd 版本。** 只要控制面上报的 envd 版本低于
`0.4.0`，SDK 就会注入历史默认用户名 `user`：

```python
if user is None and envd_version < ENVD_DEFAULT_USER:   # 0.4.0
    user = default_username                             # "user"
```

业务镜像没有 `user` 账户，envd 因此拒绝，请求以 `invalid username: 'user'` 失败。
显式 `user` 的用例不受影响。在断定 envd 有问题之前，先确认你的部署上报了什么：

```python
print(sandbox._envd_version)          # 控制面上报的版本
sandbox.commands.run("/opt/envd/usr/bin/envd -version", user="root")   # 实际运行的版本
```

## 排障

| 现象 | 检查项 |
|---|---|
| 命令以 root 而非 OCI `USER` 执行 | `ENVD_VERSION` 是否为 `0.5.14-modified`；沙箱内 `envd -version` |
| 命令在 `/root` 而非 OCI `WORKDIR` 执行 | 同上；只有修改版会记录启动 cwd |
| `invalid username: 'user'` | 控制面 envd 版本低于 `0.4.0`，见上文 |
| `Invalid API key format` | 需 `e2b >= 2.30` 且 `E2B_VALIDATE_API_KEY=false` |
| 显式 `user="root"` 失败 | `stat` 挂载后的 envd：必须是 `0:0` 且 `4755` |
| `NoNewPrivs: 1` 或挂载带 `nosuid` | setuid 位被抑制，沙箱无法切换用户 |
| 命令因 cwd 权限失败 | 错误信息已含用户和目录；检查每一级父目录的 search 权限 |

常用探针，均可通过 SDK 执行：

```python
sandbox.commands.run("id; pwd; echo $PWD")
sandbox.commands.run("stat -c '%u:%g %04a' /opt/envd/usr/bin/envd", user="root")
sandbox.commands.run("grep -E '^(Uid|Gid|Groups|NoNewPrivs):' /proc/1/status", user="root")
sandbox.commands.run("grep /opt/envd /proc/self/mountinfo", user="root")
```

envd 自身 PID 1 上的 `Uid: <oci-uid> 0 0 0` 就是 setuid 正常工作的状态：real UID 是
镜像的 `USER`，effective UID 是 0。
