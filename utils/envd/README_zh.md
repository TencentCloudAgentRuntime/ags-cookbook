# 支持 OCI 环境变量继承的 envd 源码

本目录提供可以直接构建的 envd 源代码，不包含预编译的 envd 二进制。

源码基于 envd `0.5.14`、版本 `a3fb26e`，并增加了按需继承 envd 进程环境的能力。

## 目录结构

| 路径 | 内容 |
|---|---|
| `src/` | envd 源代码和测试 |
| `shared/` | envd 实际引用的公共源码包 |
| `Makefile` | 使用容器完成构建和测试 |
| `LICENSE` | 源码许可证 |

envd 模块保留原有的 Go module path。`go.mod` 使用本目录下的 `shared/` 模块，因此
客户不需要再拉取其他源码仓库。

## 编译

编译只依赖 Docker：

```bash
make build
```

构建使用 Go `1.25.9`，产物位于：

```text
bin/envd
```

默认生成 Linux/amd64 版本。生成 Linux/arm64 版本：

```bash
make build TARGET_ARCH=arm64
```

`bin/` 下的文件不会提交到仓库。

## 测试

执行环境继承和进程相关的回归测试：

```bash
make test
```

使用 Go race detector 再执行一次：

```bash
make test-race
```

## 新增能力

修改代码位于：

```text
src/internal/services/process/handler/handler.go
```

默认行为保持不变。envd 启动时设置 `EXEC_ENABLE_ALL_ENV=1` 后，通过 envd 启动的
命令会先继承 envd 的完整进程环境。

沙箱启动时明确配置的变量，以及通过 `agr instance exec --env` 为某条命令设置的
变量，会在继承后应用。同名时，这些明确设置的值优先。

开关关闭、开关开启和同名变量覆盖的测试位于：

```text
src/internal/services/process/handler/environment_test.go
```

多阶段 Docker 构建和 AGS 使用方法见 `examples/envd-oci-env`。
