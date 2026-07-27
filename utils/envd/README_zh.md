# 支持 OCI 环境变量继承的 envd

本目录提供一个 Linux/amd64 静态链接的 `envd` 二进制。它支持让 envd
启动的子进程按需继承 envd 自身的完整环境变量。

## 产物信息

| 字段 | 值 |
|---|---|
| 文件 | `envd` |
| envd 版本 | `0.6.11` |
| 平台 | Linux/amd64 |
| 链接方式 | 静态链接 |
| Go 工具链 | `1.26.5` |
| 内嵌构建版本 | `7c23f7b-execenv` |
| 构建日期 | 2026-07-27 |
| SHA-256 | `6e48a7fa21384be23577f881ec8eaabc7610f15da62a02368e124144faa7f1ed` |

使用前请校验：

```bash
./verify.sh
```

## 新增行为

默认行为保持不变。envd 启动时未设置 `EXEC_ENABLE_ALL_ENV=1`，子进程仍只会
获得 envd 显式组装的环境变量。

envd 自身设置 `EXEC_ENABLE_ALL_ENV=1` 后，通过 envd 启动的每个子进程会先继承
envd 的完整进程环境。随后追加 envd 默认值、`/init` 环境变量以及单次执行请求
的环境变量，因此更具体、后追加的值优先。

`enable-all-env.patch` 以零上下文补丁形式包含该二进制对应的生产代码修改，可通过
`git apply --unidiff-zero` 应用。

## 安全提示

该开关会把 envd 的完整环境传给子进程。如果 envd 环境中包含不应由沙箱命令读取
的控制面凭据或其他敏感值，请不要启用。只需传递少量白名单变量时，应使用
`/init` 或单次执行请求的环境变量。

完整的 AGS 操作和验证流程见 `examples/envd-oci-env`。
