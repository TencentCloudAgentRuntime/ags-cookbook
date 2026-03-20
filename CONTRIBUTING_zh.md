# 贡献指南

感谢你为 Agent Sandbox Cookbook 做贡献。

## 开始前建议

推荐本地具备：

- `uv`
- `python3`
- `go`（Go 示例需要）
- `git`

可先执行：

```bash
make bootstrap
make examples-list
```

## 开发流程

1. Fork 仓库
2. Clone 你的 fork
3. 添加 upstream
4. 从 `main` 创建分支
5. 完成修改
6. 本地至少跑通与你修改相关的最小示例
7. 提交 PR

示例：

```bash
git clone https://github.com/YOUR_USERNAME/ags-cookbook.git
cd ags-cookbook
git remote add upstream https://github.com/TencentCloudAgentRuntime/ags-cookbook.git
git checkout -b fix/your-change
```

## 示例规范

每个示例建议至少包含：

- `README.md`
- 带 `make run` 的 `Makefile`
- 需要环境变量时提供 `.env.example`
- 独立依赖管理
  - Python：优先 `pyproject.toml` + `uv.lock`
  - Go：`go.mod` / `go.sum`

### README 建议包含

1. 示例功能说明
2. 前置条件
3. 必要环境变量
4. 安装步骤
5. 运行命令
6. 预期输出 / 产物
7. 若依赖外部模板或工具，应说明常见失败原因

## Python 示例

- 优先使用 `uv sync` 与 `uv run`
- `pyproject.toml` 中的 `requires-python` 必须准确
- 密钥必须通过环境变量注入
- 对长流程、多步骤流程增加清晰日志

## Go 示例

- 统一使用 `TENCENTCLOUD_*`
- 启动与清理逻辑应明确可见

## Commit Message

建议使用：

- `feat:`
- `fix:`
- `docs:`
- `refactor:`
- `test:`
- `chore:`

## PR 质量要求

好的 PR 应尽量做到：

- 行为变化同步更新文档
- 中英文文档尽量保持一致
- 不引入隐藏环境依赖
- 提升而不是降低本地可复现性
