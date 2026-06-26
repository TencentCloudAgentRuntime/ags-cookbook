#!/usr/bin/env python3
# waa_tool.py — 独立的 WAA Sandbox Tool 管理脚本
#
# 在 AGS 控制台还没上线 WAA Tool 创建页面之前，用这个脚本来手动管理
# WAA tool（template）。脚本零外部依赖：仅用 Python 3 标准库 +
# TC3-HMAC-SHA256 直接打 AGS CloudAPI（不依赖 e2b SDK / openssl / jq）。
#
# 用法（先准备好凭据，二选一即可）：
#
#   1) 环境变量：
#        export TENCENTCLOUD_SECRET_ID=AKIDxxxx
#        export TENCENTCLOUD_SECRET_KEY=xxxxxxxx
#        export AGS_REGION=ap-guangzhou
#
#   2) 命令行参数：
#        --secret-id / --secret-key / --region
#
# 子命令：
#   list                            列出当前账号下所有 WAA tool
#   get    --tool-id sdt-xxxx       查询单个 WAA tool 的详细信息
#   create [--name NAME]            创建一个新的 WAA tool 并等待 ACTIVE，
#                                   成功后把 ToolId 单独打印到 stdout 最后一行
#                                   （方便 shell 用 $(...) 捕获）。
#   delete --tool-id sdt-xxxx       删除指定 WAA tool
#
# 例子：
#   python3 scripts/waa_tool.py list
#   TOOL_ID=$(python3 scripts/waa_tool.py create --name my-waa-tool | tail -n1)
#   python3 scripts/waa_tool.py delete --tool-id sdt-xxxx
#
# 注意：本脚本只负责 WAA Tool 的增删查，不涉及 sandbox 实例本身，也不会
# 修改 examples/waa-ags/.env。

import argparse
import datetime
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.error
import urllib.request

# AGS CloudAPI 服务标识。region 必须由用户显式指定（环境变量或 --region），
# 不设默认值，避免之前在 chongqing / guangzhou 之间踩坑。
SERVICE = "ags"
HOST = "ags.tencentcloudapi.com"
ENDPOINT = f"https://{HOST}/"
API_VERSION = "2025-09-20"
ALGORITHM = "TC3-HMAC-SHA256"


# ---------------------------------------------------------------- 日志工具
def info(msg: str) -> None:
    print(f"[info] {msg}", file=sys.stderr)


def warn(msg: str) -> None:
    print(f"[warn] {msg}", file=sys.stderr)


def die(msg: str, code: int = 1) -> None:
    print(f"[error] {msg}", file=sys.stderr)
    sys.exit(code)


# ---------------------------------------------------------------- 凭据加载
def _maybe_load_dotenv(env: dict) -> None:
    """
    若同目录或 examples/waa-ags/.env 存在，则把里面的 KEY=VALUE 读进 env 字典
    （仅在 env 中尚未设置该 key 时填充，命令行参数和真实环境变量优先级更高）。
    我们刻意不依赖 python-dotenv，纯字符串解析即可。
    """
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(here, ".env"),                # scripts/.env（如果用户单独放）
        os.path.join(os.path.dirname(here), ".env"),  # examples/waa-ags/.env
    ]
    for path in candidates:
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                for raw in f:
                    line = raw.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, _, v = line.partition("=")
                    k = k.strip()
                    v = v.strip().strip('"').strip("'")
                    if k and k not in env:
                        env[k] = v
        except OSError:
            # .env 读取失败不致命：用户也可以走环境变量 / 命令行
            continue


def resolve_credentials(args) -> tuple:
    env = dict(os.environ)
    _maybe_load_dotenv(env)

    secret_id = args.secret_id or env.get("TENCENTCLOUD_SECRET_ID")
    secret_key = args.secret_key or env.get("TENCENTCLOUD_SECRET_KEY")
    region = args.region or env.get("AGS_REGION")

    missing = []
    if not secret_id:
        missing.append("TENCENTCLOUD_SECRET_ID (or --secret-id)")
    if not secret_key:
        missing.append("TENCENTCLOUD_SECRET_KEY (or --secret-key)")
    if not region:
        missing.append("AGS_REGION (or --region), e.g. ap-guangzhou")
    if missing:
        die("missing credentials/config: " + ", ".join(missing))

    return secret_id, secret_key, region


# ---------------------------------------------------------------- TC3 签名
def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _build_authorization(
    secret_id: str,
    secret_key: str,
    payload: str,
    timestamp: int,
) -> str:
    """
    生成 TC3-HMAC-SHA256 Authorization 头。规范化请求只签 content-type + host，
    与官方 SDK / k6 demo 行为一致。
    """
    date = datetime.datetime.utcfromtimestamp(timestamp).strftime("%Y-%m-%d")
    credential_scope = f"{date}/{SERVICE}/tc3_request"

    # 1) canonical request
    canonical_headers = (
        f"content-type:application/json\n"
        f"host:{HOST}\n"
    )
    signed_headers = "content-type;host"
    hashed_payload = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    canonical_request = "\n".join([
        "POST",
        "/",
        "",
        canonical_headers,
        signed_headers,
        hashed_payload,
    ])

    # 2) string to sign
    hashed_canonical = hashlib.sha256(
        canonical_request.encode("utf-8")
    ).hexdigest()
    string_to_sign = "\n".join([
        ALGORITHM,
        str(timestamp),
        credential_scope,
        hashed_canonical,
    ])

    # 3) derive signing key
    k_date = _sign(("TC3" + secret_key).encode("utf-8"), date)
    k_service = _sign(k_date, SERVICE)
    k_signing = _sign(k_service, "tc3_request")

    # 4) sign
    signature = hmac.new(
        k_signing, string_to_sign.encode("utf-8"), hashlib.sha256
    ).hexdigest()

    return (
        f"{ALGORITHM} "
        f"Credential={secret_id}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, "
        f"Signature={signature}"
    )


def call_api(
    action: str,
    payload: dict,
    secret_id: str,
    secret_key: str,
    region: str,
    timeout: int = 30,
) -> dict:
    """
    调用一次 AGS CloudAPI。返回解析后的 Response 体（dict）。
    若 Response.Error 存在，抛 RuntimeError，由调用方决定是否继续。
    """
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    ts = int(time.time())
    auth = _build_authorization(secret_id, secret_key, body, ts)

    headers = {
        "Authorization": auth,
        "Content-Type": "application/json",
        "Host": HOST,
        "X-TC-Action": action,
        "X-TC-Timestamp": str(ts),
        "X-TC-Version": API_VERSION,
        "X-TC-Region": region,
    }

    req = urllib.request.Request(
        ENDPOINT, data=body.encode("utf-8"), headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"{action} HTTP {e.code}: {raw}"
        ) from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"{action} network error: {e}") from e

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"{action} returned non-JSON response: {raw!r}"
        ) from e

    response = data.get("Response", {})
    err = response.get("Error")
    if err:
        # 把整段 Error 直接抛出来，方便用户 grep RequestId
        raise RuntimeError(
            f"{action} failed: code={err.get('Code')} "
            f"message={err.get('Message')} "
            f"requestId={response.get('RequestId')}"
        )
    return response


# ---------------------------------------------------------------- 子命令
def _print_tool_table(tools: list) -> None:
    if not tools:
        print("(no waa tools)")
        return
    cols = ["TOOL_ID", "NAME", "STATUS", "TYPE", "CREATE_TIME"]
    rows = [
        [
            str(t.get("ToolId", "")),
            str(t.get("ToolName", "")),
            str(t.get("Status", "")),
            str(t.get("ToolType", "")),
            str(t.get("CreateTime", "")),
        ]
        for t in tools
    ]
    widths = [len(c) for c in cols]
    for r in rows:
        for i, v in enumerate(r):
            widths[i] = max(widths[i], len(v))
    fmt = "  ".join("{:<" + str(w) + "}" for w in widths)
    print(fmt.format(*cols))
    for r in rows:
        print(fmt.format(*r))


def cmd_list(args) -> None:
    secret_id, secret_key, region = resolve_credentials(args)
    payload = {
        "Limit": 100,
        "Filters": [{"Name": "ToolType", "Values": ["waa"]}],
    }
    resp = call_api(
        "DescribeSandboxToolList", payload, secret_id, secret_key, region
    )
    tools = resp.get("SandboxToolSet") or []
    if args.json:
        print(json.dumps(tools, ensure_ascii=False, indent=2))
    else:
        _print_tool_table(tools)


def cmd_get(args) -> None:
    if not args.tool_id:
        die("--tool-id is required")
    secret_id, secret_key, region = resolve_credentials(args)
    resp = call_api(
        "DescribeSandboxToolList",
        {"ToolIds": [args.tool_id]},
        secret_id, secret_key, region,
    )
    tools = resp.get("SandboxToolSet") or []
    if not tools:
        die(f"tool {args.tool_id} not found")
    print(json.dumps(tools[0], ensure_ascii=False, indent=2))


def cmd_create(args) -> None:
    secret_id, secret_key, region = resolve_credentials(args)

    name = args.name or f"waa-{time.strftime('%Y%m%d-%H%M%S')}"
    network_mode = args.network_mode

    info(
        f"creating waa tool name={name} region={region} "
        f"network_mode={network_mode}"
    )
    payload = {
        "ToolName": name,
        "ToolType": "waa",
        "NetworkConfiguration": {"NetworkMode": network_mode},
    }
    resp = call_api(
        "CreateSandboxTool", payload, secret_id, secret_key, region
    )
    tool_id = resp.get("ToolId")
    if not tool_id:
        die(f"CreateSandboxTool succeeded but no ToolId in response: {resp}")
    info(f"tool created: {tool_id}; polling for ACTIVE ...")

    deadline = time.time() + args.wait_seconds
    poll_interval = 2
    last_status = None
    attempt = 0
    while time.time() < deadline:
        attempt += 1
        list_resp = call_api(
            "DescribeSandboxToolList",
            {"ToolIds": [tool_id]},
            secret_id, secret_key, region,
        )
        tools = list_resp.get("SandboxToolSet") or []
        status = tools[0].get("Status") if tools else None
        if status != last_status:
            info(f"  attempt={attempt} status={status}")
            last_status = status
        if status == "ACTIVE":
            info(f"tool {tool_id} is ACTIVE")
            # 把 ToolId 单独打印到 stdout 末行，方便 $(... | tail -n1)
            print(tool_id)
            return
        if status == "FAILED":
            die(f"tool {tool_id} transitioned to FAILED")
        time.sleep(poll_interval)

    die(
        f"tool {tool_id} did not become ACTIVE within {args.wait_seconds}s "
        f"(last status={last_status}). you can re-check with: "
        f"waa_tool.py get --tool-id {tool_id}"
    )


def cmd_delete(args) -> None:
    if not args.tool_id:
        die("--tool-id is required")
    secret_id, secret_key, region = resolve_credentials(args)
    call_api(
        "DeleteSandboxTool",
        {"ToolId": args.tool_id},
        secret_id, secret_key, region,
    )
    info(f"tool {args.tool_id} deleted")


# ---------------------------------------------------------------- argparse
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="waa_tool.py",
        description="Manage WAA Sandbox Tools via AGS CloudAPI "
                    "(list / get / create / delete).",
    )
    # 全局参数（凭据）
    p.add_argument("--secret-id", default=None,
                   help="Tencent Cloud SecretId (overrides env "
                        "TENCENTCLOUD_SECRET_ID)")
    p.add_argument("--secret-key", default=None,
                   help="Tencent Cloud SecretKey (overrides env "
                        "TENCENTCLOUD_SECRET_KEY)")
    p.add_argument("--region", default=None,
                   help="AGS region, e.g. ap-guangzhou (overrides env "
                        "AGS_REGION)")

    sub = p.add_subparsers(dest="cmd", required=True)

    # list
    sp = sub.add_parser("list", help="list all WAA tools")
    sp.add_argument("--json", action="store_true",
                    help="print raw JSON instead of table")
    sp.set_defaults(func=cmd_list)

    # get
    sp = sub.add_parser("get", help="show details of a single WAA tool")
    sp.add_argument("--tool-id", required=True)
    sp.set_defaults(func=cmd_get)

    # create
    sp = sub.add_parser("create", help="create a new WAA tool and wait for ACTIVE")
    sp.add_argument("--name", default=None,
                    help="tool name; default: waa-YYYYMMDD-HHMMSS")
    sp.add_argument("--network-mode", default="PUBLIC",
                    choices=["PUBLIC", "PRIVATE"],
                    help="NetworkConfiguration.NetworkMode (default: PUBLIC)")
    sp.add_argument("--wait-seconds", type=int, default=120,
                    help="how long to wait for ACTIVE (default: 120)")
    sp.set_defaults(func=cmd_create)

    # delete
    sp = sub.add_parser("delete", help="delete a WAA tool")
    sp.add_argument("--tool-id", required=True)
    sp.set_defaults(func=cmd_delete)

    return p


def main() -> None:
    args = build_parser().parse_args()
    try:
        args.func(args)
    except RuntimeError as e:
        die(str(e))
    except KeyboardInterrupt:
        die("interrupted", code=130)


if __name__ == "__main__":
    main()
