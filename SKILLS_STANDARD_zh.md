# AGS Skills 接入标准

本文档定义向 AGS Cookbook 添加 Skills 示例的**规范标准**。所有新增 Skills 示例**必须**遵循这些约定。

---

## 1. 什么是 Skill？

**Skill** 是一个普通的 Python 可调用对象，Agent 将其注册为具名工具。
可调用对象接收来自 Agent tool-call payload 的结构化参数，执行工作（可在 AGS 沙箱内），并返回可 JSON 序列化的 `dict`。

```
Agent  ──tool-call──▶  Skill 函数  ──沙箱执行──▶  AGS
                                ◀──结构化结果──────
```

---

## 2. 必须声明的依赖

每个 Skills 示例**必须**声明以下两个运行时依赖（最低版本随生态演进可更新）：

| 包名 | 最低版本 | 用途 |
|---|---|---|
| `e2b-code-interpreter` | `>=2.4.1` | 在 AGS 内进行沙箱代码执行 |
| `tencentcloud-sdk-python` | `>=3.0.0` | 腾讯云控制面调用 |

可按需添加其他库，但上述两个不可缺少。

---

## 3. Python 版本

所有 Skills 示例**必须**使用 **Python 3.13**：

```toml
# pyproject.toml
[project]
requires-python = ">=3.13"
```

使用 `uv` 管理解释器和虚拟环境，不得假设系统已安装对应版本的 Python。

---

## 4. 依赖管理：uv

- 使用 `pyproject.toml` + `uv.lock` 声明所有依赖。
- **不得**使用 `requirements.txt` 或裸 `pip`。
- `Makefile` 目标必须使用 `uv sync` / `uv run`：

```makefile
.PHONY: setup run

setup:
	uv sync

run:
	uv run main.py
```

---

## 5. 目录结构

每个 Skills 示例位于 `examples/<skill-name>/`，必须包含：

```
examples/<skill-name>/
├── main.py            # 入口；每个 Skill 是一个普通可调用对象
├── pyproject.toml     # 项目元数据与依赖
├── uv.lock            # 提交到仓库的锁文件
├── Makefile           # 至少含 setup 和 run 目标
├── .env.example       # 占位符环境变量；严禁提交真实密钥
├── README.md          # 英文主文档，见第 6 节
└── README_zh.md       # 中文翻译（Skills 示例必填）
```

---

## 6. README 要求

`README.md` **必须使用英文**。`README_zh.md` 对所有 Skills 示例**为必填项**。

每份 README 必须按以下顺序覆盖全部七个章节：

1. **示例展示了什么** — 一段摘要
2. **前置条件** — Python 版本、`uv`、其他外部工具
3. **必要环境变量** — 表格或代码块
4. **安装步骤** — `make setup`（或等效命令）
5. **运行命令** — `make run`（或等效命令）
6. **预期输出或产物** — 精确或具代表性的输出
7. **常见失败提示** — 至少包含下表三条

### 必须包含的三条标准失败提示

| 现象 | 可能原因 |
|---|---|
| `KeyError: 'E2B_API_KEY'` | 环境变量未导出 |
| 沙箱创建超时 | `E2B_DOMAIN` 与账号所在地域不匹配 |
| 凭据检查抛出 `TencentCloudSDKException` | `TENCENTCLOUD_SECRET_ID` / `SECRET_KEY` 无效或缺失 |

---

## 7. 环境变量

### AGS 沙箱（必填）

```bash
export E2B_API_KEY="your_ags_api_key"
export E2B_DOMAIN="ap-guangzhou.tencentags.com"   # 地域专属
```

### 腾讯云控制面（使用 tencentcloud-sdk-python 时必填）

```bash
export TENCENTCLOUD_SECRET_ID="your_secret_id"
export TENCENTCLOUD_SECRET_KEY="your_secret_key"
export TENCENTCLOUD_REGION="ap-guangzhou"
```

规则：
- 所有密钥从环境变量读取，**严禁硬编码凭据**。
- `.env.example` 只填占位符，不提交真实值。
- 通过 shell `export` 或 `python-dotenv` 加载 `.env`——`.env` 不提交到仓库。

---

## 8. Skill 接口契约

```python
def skill_name(arg1: SomeType, arg2: SomeType) -> dict:
    """一句话描述该 Skill 的功能。"""
    ...
    return {
        "field": value,   # 必须可 JSON 序列化
    }
```

- 每个 Skill 对密钥而言是**纯函数**（从环境变量读取，而非通过参数传入）。
- 返回值**必须**可 JSON 序列化。
- Skill 函数体内使用 `logging` 输出诊断信息，不用 `print`。
- `print` 仅在 `__main__` 块中用于最终的人类可读输出。

---

## 9. 日志规范

```python
import logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)
```

- `log.info`：沙箱创建、Skill 调用、沙箱关闭等关键里程碑。
- `log.error`：可恢复错误；不可恢复错误直接抛出异常。

---

## 10. 提交与 PR 规范

继承自 [CONTRIBUTING.md](./CONTRIBUTING.md)，Skills 专项补充：

- 提交前缀：新 Skill 用 `feat(skills):`，修复用 `fix(skills):`
- PR **必须**同步更新 `examples/README.md`（示例列表表格）和根目录 `README.md`（示例概览表格）
- 英文和中文 README 必须在同一次提交中一起更新
- `uv.lock` 必须与 `pyproject.toml` 一起提交

---

## 11. 参考示例

`examples/skills-hello-world` 是实现了本文档所有规则的标准参考示例。
请以它为模板新建 Skills 示例。

```bash
make example-setup EXAMPLE=skills-hello-world
make example-run   EXAMPLE=skills-hello-world
```
