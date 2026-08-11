# 支持 OCI 环境变量继承的 envd 源码

本目录提供三个可以直接构建的 envd 源码分发版本，不包含预编译二进制。

标准分发版本增加了按需继承 envd 进程环境的能力；`0.5.14-modified` 则始终把
envd 启动时的身份和环境作为默认值：

| envd 版本 | 公开源码版本 | Go 版本 | 源码路径 |
|---|---|---|---|
| `0.5.14` | `a3fb26eb4344bbaf66c0d2478c086623b560ef41` | `1.25.9` | `versions/0.5.14/` |
| `0.5.14-modified` | `a3fb26eb4344bbaf66c0d2478c086623b560ef41` | `1.25.9` | `versions/0.5.14-modified/` |
| `0.2.11` | `1af78dd38a2cedce7f513c26aa2deb443cb0f0ef` | `1.24.3` | `versions/0.2.11/` |

三个分发版本相互独立，envd 不会与客户端自动协商版本。请使用客户端或集成方案明确
要求的版本。如果两者都没有指定版本，可以先使用默认的 `0.5.14`。

`0.5.14` 已经包含上游的 cgroup v2 检测逻辑。它会在 cgroup v1 环境中回退到
空实现，避免 envd 使用无效的 cgroup 文件描述符启动子进程。

## 目录结构

每个版本都包含：

| 路径 | 内容 |
|---|---|
| `src/` | envd 源代码和测试 |
| `shared/` | 该版本实际引用的公开公共源码包 |
| `LICENSE` | Apache License 2.0 |
| `SOURCE.md` | 精确的源码版本和分发修改说明 |

envd 模块保留原有的 Go module path。`go.mod` 会使用同版本目录下的 `shared/`
模块，因此客户不需要再拉取其他源码仓库。

## 编译

编译只依赖 Docker。

分别编译各版本：

```bash
make build VERSION=0.5.14
make build VERSION=0.5.14-modified
make build VERSION=0.2.11
```

直接在 `utils/envd` 下执行命令时，用 `VERSION` 选择源码。
`examples/envd-oci-env` cookbook 使用 `ENVD_VERSION` 表示同一选择，并把它传给
这里的 Makefile。

一次编译全部版本：

```bash
make build-all
```

Linux/amd64 产物为：

```text
bin/envd-0.5.14
bin/envd-0.5.14-modified
bin/envd-0.2.11
```

生成 Linux/arm64 版本：

```bash
make build-all TARGET_ARCH=arm64
```

`bin/` 下的文件不会提交到仓库。

## 测试

执行全部版本的环境继承和进程测试：

```bash
make test-all
```

只测试其中一个版本：

```bash
make test VERSION=0.5.14
make test VERSION=0.5.14-modified
make test VERSION=0.2.11
```

使用 Go race detector 再执行一次：

```bash
make test-race-all
```

执行全部测试和构建步骤：

```bash
make verify-all
```

## 新增能力

`0.5.14` 和 `0.2.11` 的功能修改位于：

```text
versions/<version>/src/internal/services/process/handler/handler.go
```

默认行为保持不变。envd 启动时设置 `EXEC_ENABLE_ALL_ENV=1` 后，通过 envd 启动的
命令会先继承 envd 的完整进程环境。

开关既可以来自镜像 `ENV`，也可以来自创建沙箱时提供的容器环境配置。它必须在
envd 启动前存在；只在某一次子进程请求中设置已经太晚。

容器运行时会把 OCI 镜像 `ENV` 和 AGS `CustomConfiguration.Env` 合并到 envd
自身的进程环境中。envd 随后依次应用身份变量、沙箱平台在启动阶段提供的公共命令
默认值，以及当前命令的变量。同名时，后应用的值会覆盖前面的值。

两个按需继承版本都包含开关关闭、开关开启和同名变量覆盖测试：

```text
versions/<version>/src/internal/services/process/handler/environment_test.go
```

`0.5.14-modified` 会在 envd 启动时记录完整环境和启动身份（进程的 real UID、GID 和
supplementary groups）。请求未指定其他用户时，命令和文件系统操作会使用这些默认值。该分发版本始终继承环境，
`EXEC_ENABLE_ALL_ENV` 不控制这一行为；相关测试位于 `internal/execcontext`、
`internal/permissions` 和受影响的服务包中。二进制报告的版本仍为 `0.5.14`。

### 把 OCI User / Workdir 作为命令默认值（`0.5.14-modified`）

该分发版本还会记录 envd 的启动身份和启动工作目录，并把它们用作未显式指定时的命令
默认值：

| 请求 | 使用的身份 | 使用的工作目录 |
|---|---|---|
| 无 user、无 `cwd` | envd 启动身份 | envd 启动工作目录 |
| 显式 user、无 `cwd` | 在 rootfs 中解析出的该用户 | envd 启动工作目录 |
| 无 user、显式 `cwd` | envd 启动身份 | 请求的路径 |
| 显式 user、显式 `cwd` | 该用户 | 请求的路径 |

由容器运行时启动 envd 时，envd 的启动身份和启动工作目录来自镜像的 `USER` 与
`WORKDIR`，因此这两项就成为命令默认值。

有三点需要特别说明：

- 启动身份取自进程的**real** UID、GID 和 supplementary groups。setuid envd 的
  effective UID 为 0，若读取 effective UID 就会把 root 误记为默认身份。
- 它是纯数值快照，不依赖 passwd 条目，因此镜像 `USER` 为纯数字 UID 时同样可用。
- 是否需要为子进程设置凭据，取决于目标身份与 envd 当前 **effective** UID、GID 和
  当前 groups 的比较结果。若改为与 real ID 比较，setuid 场景下会跳过降权，把
  root effective UID 泄漏给命令。当目标身份已经一致时直接继承而不重复设置，
  这样非特权 envd 不会在缺少权限的情况下调用 `setgroups`。

`PWD` 以及身份变量（`HOME`、`USER`、`LOGNAME`）描述的是**被启动的进程**，而不是
envd 自身：它们写在启动环境快照之后，因此显式 user 或显式 `cwd` 都能被正确反映。
请求级环境变量仍然可以覆盖它们，与既有优先级一致。

若命令无法在解析后的工作目录中启动，错误信息会同时给出目标用户、目录，以及看起来
缺少 search 权限的路径分量。是否允许进入始终由内核裁定——内核还会考虑 POSIX ACL、
SELinux 和 capabilities，而这些都不体现在传统权限位上——因此 envd 不会替内核提前
判定，也不会拒绝内核本来允许的请求。

若无法确定启动工作目录，默认值会退化为 `/` 并向 stderr 输出警告，以确保默认值不会
悄悄回落到用户 HOME。

解析显式用户时若无法读取用户组数据库，命令仍会以该用户的主组运行，并记录一条
warning。丢失 supplementary groups 不会导致请求被拒绝，因为主身份仍然正确。

`/init` 的 `DefaultUser` 和 `DefaultWorkdir` 仍然保留给设置它们的调用方，并且
优先于记录下来的启动值。由于身份变量现在写在启动环境快照之后，通过环境注入
`HOME`、`USER`、`LOGNAME` 的 `/init` 调用方不再能覆盖它们；请求级变量仍然可以。E2B 兼容数据面链路不会设置这两项。

完整改动清单以及特权 setuid 测试的运行方式见
`versions/0.5.14-modified/SOURCE.md`。

可选择版本的多阶段 Docker 构建和 AGS 使用方法见 `examples/envd-oci-env`。
