# 从 GitHub Actions 调用 AGS 沙箱

在独立沙箱中测试 Agent 生成的代码，避免直接在 GitHub Actions Runner 执行候选代码。
本示例将 checkout 上传到腾讯云 Agent Sandbox（AGS），运行测试、实时回传日志，
取回 JSON 和 JUnit 报告，最后销毁沙箱。

`workload/candidate.py` 是可重复验证的固定候选代码，不会调用模型。
可将其替换为 Agent 生成的 `unique_in_order(values)` 实现（去重且保留首次出现顺序）。
五个用例覆盖空输入、重复值、无重复输入、负数和字符串，无需模型凭证或沙箱出网。

```text
GitHub 托管 Runner → AGS SDK → 新建沙箱 → 执行命令 → 回传报告/产物 → 销毁
```

本示例不是运行在 AGS 内的原生 GitHub Actions Runner，也不提供
`runs-on: [self-hosted, tencent-agr]` 能力。
候选代码和测试框架位于同一沙箱：隔离宿主执行环境，但不是防篡改评分系统。
仅上传可丢弃且不含秘密的工作区；文件名排除规则不等同于完整凭证扫描。

## 验证内容

- 打包当前 checkout；默认排除 `.git`、虚拟环境、缓存、`.env` 和 `.env.*`，
  但保留 `.env.example`
- 一次任务创建一个沙箱并上传 checkout
- 在沙箱执行一条 Shell 命令，默认不转发宿主环境变量
- 独立记录并传播业务退出码，不依赖数据面命令以非零状态结束
- 实时回传 stdout/stderr；超时或断连时保留已经收到的日志
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

预期输出：

```text
Ran 5 tests
OK
{"tests": 5, "failures": 0, "errors": 0, "status": "passed"}
```

`ags-results/run-report.json` 中应为 `status: succeeded`、`workload_exit_code: 0`、
`cleanup: killed`。`ags-results/artifacts.tar.gz` 包含 `workload/output/result.json`
和 `workload/output/junit.xml`。错误实现返回业务退出码 1，仍会生成测试报告；
候选代码挂起时受命令超时限制。

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

只有 SDK 明确返回路径不存在时才按缺失产物告警。存在性检查的权限或连接错误、
以及路径存在但 tar 非零退出，都会使任务失败。打包失败时输出 tar 日志，不再下载产物。

路径检查、打包、传输或产物下载异常会将整体 `exit_code` 设为 2、`status` 设为
`infrastructure_error`。`workload_exit_code` 单独保留业务结果，未取得时为 null。
`main.py` 返回整体退出码；GNU Make 在 recipe 失败时返回 2，原始业务退出码需查报告。

Make 通过环境变量原样传递命令和路径。调用时仍需给宿主 Shell 正确加引号，例如：

```bash
make run COMMAND='python -c "print(1)" && echo "$PATH" | head -c 100'
```

上述单引号内的变量与命令替换仅在沙箱中执行。请传入字面值，
此目标不会展开 `$(OTHER_VARIABLE)` 等 Make 变量引用。

如果 `OUTPUT_DIR` 位于 `WORKSPACE` 内，上传时会自动排除该目录及全部子项，
连续运行也不会重新上传历史结果；其他同名目录仍会保留。输出目录不能与工作区相同。
每次运行开始时只删除脚本拥有的 `artifacts.tar.gz` 和 `run-report.json`，保留其他文件。
下载失败或产物缺失不会残留上次的压缩包。并发运行应使用不同输出目录。

## 在 GitHub Actions 中运行

仓库已经包含
[`ags-sandbox-phase0.yml`](../../.github/workflows/ags-sandbox-phase0.yml)。

1. 新建仓库级 Actions Secret：`E2B_API_KEY`。
2. 可选：新建仓库级 Variable：`E2B_DOMAIN`；默认值为
   `ap-guangzhou.tencentags.com`。
3. 打开 **Actions > AGS Sandbox Code Evaluation > Run workflow**，选择包含该工作流的分支。
4. 查看任务日志并下载名为 `ags-sandbox-...` 的 workflow artifact。

产物包括：

- `run-report.json`：沙箱 ID、模板、工作负载结果、耗时、清理结果及命令摘要；
  不持久化命令原文
- `artifacts.tar.gz`：从沙箱下载的业务结果目录

工作流上传整个仓库，因此压缩包内路径以 `examples/github-actions-sandbox/workload/output/`
开头，与上面本地 `make run` 的较短路径不同。工作流的报告校验步骤要求内置候选代码
通过全部五个用例；更换评测任务时，也需同步校验预期。

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

本地测试只执行固定、可信的测试代码，不会执行可替换的 `workload/candidate.py`。
请使用 `make run` 在 AGS 中评测候选代码；不要在宿主机直接运行
`workload/ci_task.py` 来执行不可信代码。

可复现验证步骤和出网需求分别见 [`VALIDATION.md`](./VALIDATION.md) 与
[`NETWORK_REQUIREMENTS.md`](./NETWORK_REQUIREMENTS.md)。

## 常见问题

- **沙箱创建失败**：检查 API Key、AGS 域名、模板权限及 Runner 到 AGS 的 HTTPS。
- **找不到命令**：沙箱镜像缺少所需运行时或工具链；本示例需要 Python 3、Bash 和 tar/gzip。
- **依赖下载失败**：只把必要的依赖源加入沙箱网络策略，参见出网需求清单。
- **没有产物压缩包**：确认结果路径是 checkout 内的相对路径，并由任务实际创建。
- **清理状态为 `failed`**：保留报告中的沙箱 ID，交由 AGS 运维侧对账回收。

取消工作流或强制终止调用进程可能阻止清理代码运行。沙箱超时（默认 900 秒）限制实例生命周期，
但不代表取消工作流后会立即清理。
