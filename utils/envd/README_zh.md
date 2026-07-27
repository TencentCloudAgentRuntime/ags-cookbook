# 支持 OCI 环境变量继承的 envd 源码

本目录同时提供两个可以直接构建的 envd 源码版本，不包含预编译二进制。

两个版本都增加了按需继承 envd 进程环境的能力：

| envd 版本 | 公开源码版本 | Go 版本 | 源码路径 |
|---|---|---|---|
| `0.5.4` | `017de20162f1d9ea340d3767eba2c43cd0dd8c33` | `1.25.4` | `versions/0.5.4/` |
| `0.2.11` | `1af78dd38a2cedce7f513c26aa2deb443cb0f0ef` | `1.24.3` | `versions/0.2.11/` |

两个版本相互独立，envd 不会与客户端自动协商版本。请使用客户端或集成方案明确
要求的版本。如果两者都没有指定版本，可以先使用默认的 `0.5.4`。

`0.5.4` 还回移了公开上游提交
`452097909d71775a8953f1b4e4574519cbcb123d`。该修复会正确识别 cgroup v1
并回退到空实现，避免 envd 使用无效的 cgroup 文件描述符启动子进程。

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

分别编译两个版本：

```bash
make build VERSION=0.5.4
make build VERSION=0.2.11
```

直接在 `utils/envd` 下执行命令时，用 `VERSION` 选择源码。
`examples/envd-oci-env` cookbook 使用 `ENVD_VERSION` 表示同一选择，并把它传给
这里的 Makefile。

一次编译两个版本：

```bash
make build-all
```

Linux/amd64 产物为：

```text
bin/envd-0.5.4
bin/envd-0.2.11
```

生成 Linux/arm64 版本：

```bash
make build-all TARGET_ARCH=arm64
```

`bin/` 下的文件不会提交到仓库。

## 测试

执行两个版本的环境继承和进程测试：

```bash
make test-all
```

只测试其中一个版本：

```bash
make test VERSION=0.5.4
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

每个版本的功能修改都位于：

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

每个版本都包含开关关闭、开关开启和同名变量覆盖测试：

```text
versions/<version>/src/internal/services/process/handler/environment_test.go
```

可选择版本的多阶段 Docker 构建和 AGS 使用方法见 `examples/envd-oci-env`。
