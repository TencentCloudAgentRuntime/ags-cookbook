# WAA Tool 管理 CLI

`waa_tool.py` 是一个零依赖的小工具，直接通过 CloudAPI 管理腾讯云
[AGS](https://cloud.tencent.com/document/product/1899) 中的
**WAA Sandbox Tool**（即 *template*）。

之所以提供这个脚本，是因为 AGS 控制台目前**还没有创建 WAA Tool 的页面**。
在前端上线之前，[.env.example](../.env.example) 里的 `AGS_TEMPLATE` 字段
（形如 `sdt-xxxx` 的 ToolId）需要靠这个脚本拿到。

> English version: [README.md](./README.md).

---

## 这个脚本是 / 不是什么

它**是**：

- 控制台暂时无法完成的四种操作的命令行替代：WAA tool 的
  `list` / `get` / `create` / `delete`。
- 100% 自包含：只用 Python 3 标准库，不依赖 `e2b`、`openssl`、`jq`，
  不需要 `pip install`。
- 安全：不会写入 `examples/waa-ags/.env` 或任何配置文件。

它**不是**：

- `make run` 流程的一部分。属于偶发性的手动操作，
  通常每个项目只跑一次。
- 管理 **API key** 的工具——API key 仍需在 AGS 控制台获取。
- 管理 **sandbox 实例** 的工具——实例由 `make run` 使用的 e2b
  SDK 自动创建与销毁，`make run` 退出时会被自动清理。

---

## 前置条件

- Python 3.8+（macOS / 多数 Linux 发行版自带）。
- 一个开通了 AGS 服务的腾讯云账号，并在你计划使用的 region 启用 AGS。
- 该账号的 `SecretId` / `SecretKey`。在
  <https://console.cloud.tencent.com/cam/capi> 创建。

仅此而已——无需 `pip install`、无需虚拟环境。

---

## 配置

凭据和 region 有三种提供方式，**优先级从高到低**：

1. 命令行参数：`--secret-id`、`--secret-key`、`--region`。
2. 环境变量：

   ```bash
   export TENCENTCLOUD_SECRET_ID=AKIDxxxxxxxxxxxxxxxx
   export TENCENTCLOUD_SECRET_KEY=xxxxxxxxxxxxxxxxxxxxxxxx
   export AGS_REGION=ap-guangzhou
   ```

3. `.env` 文件，按下列顺序回退查找：
   - `examples/waa-ags/scripts/.env`
   - `examples/waa-ags/.env`

   …**仅当 (1)、(2) 没提供该 key 时**才会从 `.env` 读。脚本不会写入这两个文件。

> **region 没有默认值**，必须显式指定。取值是 AGS region 编码，例如
> `ap-guangzhou`。如果脚本拿不到 region，会直接报错退出，避免误打到错误的 region。

---

## 命令

下面的示例都假设你在仓库根目录或 `examples/waa-ags/` 下执行
`python3 scripts/waa_tool.py …`。

### `list` — 列出当前账号下的所有 WAA tool

```bash
python3 scripts/waa_tool.py list
```

输出示例（表格走 stdout，日志走 stderr）：

```text
TOOL_ID         NAME                STATUS  TYPE  CREATE_TIME
sdt-6h8pj4cl    waa-20260620-101530 ACTIVE  waa   2026-06-20T10:15:31Z
sdt-abcd1234    dev-tool            ACTIVE  waa   2026-06-25T03:42:11Z
```

加 `--json` 可以打印原始 API 对象，方便用 `jq` 处理：

```bash
python3 scripts/waa_tool.py list --json | jq '.[] | {ToolId, Status}'
```

### `get` — 查看单个 tool 的详情

```bash
python3 scripts/waa_tool.py get --tool-id sdt-6h8pj4cl
```

打印完整的 `SandboxTool` 对象（格式化后的 JSON）。

### `create` — 创建一个新的 WAA tool 并等待 ACTIVE

```bash
# 自动生成名字（waa-YYYYMMDD-HHMMSS）：
python3 scripts/waa_tool.py create

# 自定义名字：
python3 scripts/waa_tool.py create --name my-waa-tool

# 私网模式 + 更长的等待：
python3 scripts/waa_tool.py create \
  --name internal-waa \
  --network-mode PRIVATE \
  --wait-seconds 240
```

行为说明：

- 调用 `CreateSandboxTool`，固定 `ToolType=waa`，`NetworkConfiguration.NetworkMode`
  按参数走。
- 每 2 秒轮询一次 `DescribeSandboxToolList`，状态变化时打日志到 **stderr**。
- 成功后，**只把 `ToolId` 单独打印到 stdout 的最后一行**，方便 shell 替换捕获：

  ```bash
  TOOL_ID=$(python3 scripts/waa_tool.py create --name my-waa-tool | tail -n1)
  echo "$TOOL_ID"   # sdt-xxxxxxxx
  ```

- 如果状态变成 `FAILED`，或者在 `--wait-seconds`（默认 120s）内未达 `ACTIVE`，
  脚本以非零退出。但 tool 本身可能已经创建出来了，可以再用 `get` 查一下。

| 参数 | 默认值 | 说明 |
|---|---|---|
| `--name` | `waa-YYYYMMDD-HHMMSS` | 自由命名，账号下唯一 |
| `--network-mode` | `PUBLIC` | `PUBLIC` 或 `PRIVATE` |
| `--wait-seconds` | `120` | 等待 `ACTIVE` 的最大秒数 |

### `delete` — 删除一个 WAA tool

```bash
python3 scripts/waa_tool.py delete --tool-id sdt-6h8pj4cl
```

注意它**只删除模板**，不会动从这个 tool 派生出来的 **sandbox 实例**。
实例由 `make run` 使用的 e2b SDK 管理，`make run` 退出时会被自动清理。

---

## 典型流程：为新的 `examples/waa-ags/.env` 准备 ToolId

```bash
# 1. 提供凭据（一次性的，脚本不会写入 .env）。
export TENCENTCLOUD_SECRET_ID=AKIDxxxxxxxxxxxxxxxx
export TENCENTCLOUD_SECRET_KEY=xxxxxxxxxxxxxxxxxxxxxxxx
export AGS_REGION=ap-guangzhou

cd examples/waa-ags

# 2. 看看是否已有可用的 tool。
python3 scripts/waa_tool.py list

# 3. 没有就创建一个，并捕获 ToolId。
TOOL_ID=$(python3 scripts/waa_tool.py create --name dev-waa | tail -n1)
echo "AGS_TEMPLATE=$TOOL_ID"

# 4. 把 TOOL_ID 填进 examples/waa-ags/.env 的 AGS_TEMPLATE，
#    然后照常执行 make run。
```

---

## 退出码

| Code | 含义 |
|---|---|
| `0` | 成功 |
| `1` | 通用失败（缺凭据、AGS 接口报错、状态 FAILED、超时等） |
| `130` | 被 Ctrl-C 中断 |

所有错误都写到 **stderr**，前缀 `[error]`；普通日志用 `[info]` / `[warn]`。
如需写入文件：

```bash
python3 scripts/waa_tool.py create 2> create.log
```

---

## 常见问题

**`missing credentials/config: TENCENTCLOUD_SECRET_ID …`**
脚本没拿到凭据。请设置环境变量，或通过 `--secret-id` / `--secret-key`
传入。`.env` 中的值仅在环境变量未设置时才会被使用。

**`missing credentials/config: AGS_REGION …`**
必须显式指定 region，脚本不设默认。一般使用 `ap-guangzhou`，或换成你
账号实际开通 AGS 的那个 region。

**`CreateSandboxTool failed: code=AuthFailure.SignatureFailure …`**
检查系统时钟。TC3 签名对时间敏感，`date -u` 应当与真实 UTC 误差在几分钟内。

**`CreateSandboxTool failed: code=LimitExceeded.* …`**
账号下命中了某个配额。先用 `list` 看一下，把不再使用的 tool 删掉。
注意 `APIKeyQuota` 这类配额是按子账号 (SubAccountUIN) **跨 region 全局共享**的，
换 region 重新创建 API key 并不能绕过。

**`tool sdt-xxxx did not become ACTIVE within 120s`**
再用 `get --tool-id sdt-xxxx` 查一下，tool 可能稍后才完成。如果你的账号
通常需要更长时间，下次创建时加 `--wait-seconds 240`（或更大）。

---

## 实现原理（一段话）

脚本用 **TC3-HMAC-SHA256** 给每个请求签名（被签名的规范请求只包含
`content-type` 和 `host` 这两个 header，与官方 SDK 行为一致），然后 POST
到 `https://ags.tencentcloudapi.com/`，配合标准的
`X-TC-Action` / `X-TC-Region` / `X-TC-Version` 头部。一共用到三个 CloudAPI
action：`CreateSandboxTool`、`DescribeSandboxToolList`、`DeleteSandboxTool`。
不依赖任何 SDK 或第三方库。完整实现见 [`waa_tool.py`](./waa_tool.py)。
