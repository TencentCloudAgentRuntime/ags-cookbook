# 从 GitHub Actions 调用 AGS 沙箱

这个 Phase 0 Cookbook 从现有 GitHub 托管 Runner 调用腾讯云 Agent Sandbox
（AGS），将 checkout 后的仓库放进一个全新沙箱执行：

```text
GitHub 托管 Runner → AGS SDK → 新建沙箱 → 执行命令 → 回传报告/产物 → 销毁
```

本示例不是运行在 AGS 内的原生 GitHub Actions Runner，也不提供后续阶段的
`runs-on: [self-hosted, tencent-agr]` 能力。

## 验证内容

- 打包当前 checkout；默认排除 `.git`、虚拟环境、缓存、`.env` 和 `.env.*`，
  但保留 `.env.example`
- 一次任务创建一个沙箱并上传 checkout
- 在沙箱执行一条 Shell 命令，默认不转发宿主环境变量
- 独立记录并传播业务退出码，不依赖数据面命令以非零状态结束
- 将 stdout/stderr 返回 GitHub Actions 日志
- 将指定结果路径下载为 `artifacts.tar.gz`
- 生成机器可读的 `run-report.json`
- 无论成功、任务失败或基础设施失败，都尝试销毁沙箱

## 前置条件

- Python 3.12 或更高版本
- [`uv`](https://docs.astral.sh/uv/)
- 有权使用目标沙箱模板的 AGS API Key
- 现有 Runner 可以通过 HTTPS 访问配置的 AGS 域名

## 必需环境变量

```bash
export E2B_API_KEY="your_ags_api_key"
export E2B_DOMAIN="ap-guangzhou.tencentags.com"
```

其他可选配置见 [`.env.example`](./.env.example)，脚本不会自动加载该文件。

## 本地运行

```bash
make setup
make run
```

在本目录运行其他仓库或 CI 命令时，显式传入路径：

```bash
make run \
  WORKSPACE=/path/to/checkout \
  COMMAND="python -m unittest" \
  ARTIFACT_PATH=test-results \
  OUTPUT_DIR=ags-results
```

`ARTIFACT_PATH` 必须是上传后工作区内的相对路径。如果路径不存在，会产生告警，
但不会覆盖工作负载本身的退出码。

## 在 GitHub Actions 中运行

仓库已经包含
[`ags-sandbox-phase0.yml`](../../.github/workflows/ags-sandbox-phase0.yml)。

1. 新建仓库级 Actions Secret：`E2B_API_KEY`。
2. 可选：新建仓库级 Variable：`E2B_DOMAIN`；默认值为
   `ap-guangzhou.tencentags.com`。
3. 打开 **Actions > AGS Sandbox Phase 0 > Run workflow**。
4. 查看任务日志并下载名为 `ags-sandbox-...` 的 workflow artifact。

产物包括：

- `run-report.json`：沙箱 ID、模板、工作负载结果、耗时、清理结果及命令摘要；
  不持久化命令原文
- `artifacts.tar.gz`：从沙箱下载的业务结果目录

## 转发工作负载凭证

脚本默认不会将 GitHub Actions 环境变量或 Secret 传进沙箱。只有显式指定的变量
才会转发：

```bash
uv run python main.py \
  --workspace /path/to/checkout \
  --command "./ci.sh" \
  --artifact-path test-results \
  --env PACKAGE_REGISTRY_TOKEN
```

不要把 Secret 写进 `--command`，命令可能出现在进程诊断信息中。工作负载输出会进入
Actions 日志，因此 workflow 仍需避免主动输出 Secret，并正确配置 GitHub 脱敏。

## 验证

无需 AGS 凭证即可运行单元测试：

```bash
make test
```

Phase 0 验收记录和出网需求分别见 [`VALIDATION.md`](./VALIDATION.md) 与
[`NETWORK_REQUIREMENTS.md`](./NETWORK_REQUIREMENTS.md)。

## 常见问题

- **沙箱创建失败**：检查 API Key、AGS 域名、模板权限及 Runner 到 AGS 的 HTTPS。
- **找不到命令**：沙箱镜像缺少所需运行时或工具链，应记录到镜像需求并更换受控模板验证。
- **依赖下载失败**：只把必要的依赖源加入沙箱网络策略，参见出网需求清单。
- **没有产物压缩包**：确认结果路径是 checkout 内的相对路径，并由任务实际创建。
- **清理状态为 `failed`**：保留报告中的沙箱 ID，交由 AGS 运维侧对账回收。
