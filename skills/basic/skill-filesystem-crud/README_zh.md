# Skill: File Ops Extended（文件操作扩展）

本示例补充 `skill-file-sandbox`（上传/变换/下载）所缺的**独立文件系统原语**，对应 e2e 套件 `e2e/basic/sandbox_operations_test.go` "File Operations" 章节：存在性检查、目录创建、删除、重命名、详细列表。

每个 Skill 各自开启一个新沙箱，便于 Agent 的 tool-call 循环调用。若需多步操作共用沙箱，使用 `run_batch`。

## 它展示了什么

- **`file_exists(path)`** — 存在性检查
- **`make_dir(path)`** — `mkdir -p` 语义
- **`remove_path(path)`** — 递归删除
- **`list_dir_detailed(path)`** — 列举 `{name, type, size}`
- **`rename_path(src, dst)`** — 移动/重命名
- **`run_batch(ops)`** — 同一沙箱内批量执行 `exists` / `mkdir` / `remove` / `list` / `rename` / `write` / `read` 操作

当 e2b SDK 老版本缺少对应方法时（如没有 `files.exists`），Skill 会透明降级到沙箱内的 shell 命令。

## 前置条件

- Python 3.13（由 `uv` 管理）
- 已安装 `uv`
- AGS API Key **或** 腾讯云 AKSK 凭据（二选一）

## 必要环境变量

```bash
# 方式 A —— APIKey 模式
export E2B_API_KEY="your_ags_api_key"
export E2B_DOMAIN="ap-guangzhou.tencentags.com"
```

```bash
# 方式 B —— AKSK 模式
export TENCENTCLOUD_SECRET_ID="your_secret_id"
export TENCENTCLOUD_SECRET_KEY="your_secret_key"
export TENCENTCLOUD_REGION="ap-guangzhou"
```

## 安装与运行

```bash
make setup
make run
```

## 预期输出

```
=== Skill Result: run_batch ===
{"results": [...], "ok": true}
```

## 常见失败提示

| 现象 | 可能原因 |
|---|---|
| `KeyError: 'E2B_API_KEY'` | 环境变量未导出 |
| 沙箱创建超时 | `E2B_DOMAIN` 与账号所在地域不匹配 |
| `TencentCloudSDKException` | `TENCENTCLOUD_SECRET_ID` / `SECRET_KEY` 无效或缺失 |
| `PermissionError` | 目标路径属于其它用户；改用可写路径或 root |

## Skill 接口

```python
file_exists(path: str) -> dict
make_dir(path: str) -> dict
remove_path(path: str) -> dict
list_dir_detailed(path: str = "/tmp") -> dict
rename_path(src: str, dst: str) -> dict
run_batch(ops: list[dict]) -> dict
```
