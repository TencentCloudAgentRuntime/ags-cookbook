from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

AFFINITY_HEADER = "X-Tencent-Agr-Affinity-Id"
TOKEN_ENV = "MCP_DEPLOYMENT_TOKEN"
Transport = Literal["local", "proxy", "direct"]


def fingerprint(value: str | None) -> str | None:
    if value is None:
        return None
    return hashlib.sha256(value.encode()).hexdigest()[:12]


def emit(event: str, **fields: Any) -> None:
    print(json.dumps({"event": event, **fields}, sort_keys=True), flush=True)


@dataclass
class AffinityState:
    path: Path | None = None
    value: str | None = None

    @classmethod
    def load(cls, path: Path | None, *, required: bool = False) -> AffinityState:
        if path is None:
            if required:
                raise ValueError("--state-file is required")
            return cls()
        if not path.exists():
            if required:
                raise ValueError("the affinity state file does not exist")
            return cls(path=path)
        payload = json.loads(path.read_text())
        value = payload.get("affinity")
        if not isinstance(value, str) or not value:
            raise ValueError("the affinity state file is invalid")
        return cls(path=path, value=value)

    def save(self) -> None:
        if self.path is None or self.value is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.{os.getpid()}.tmp")
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            stat.S_IRUSR | stat.S_IWUSR,
        )
        try:
            with os.fdopen(descriptor, "w") as stream:
                json.dump({"affinity": self.value}, stream)
                stream.write("\n")
            os.replace(temporary, self.path)
            self.path.chmod(stat.S_IRUSR | stat.S_IWUSR)
        finally:
            if temporary.exists():
                temporary.unlink()

    async def on_request(self, request: httpx2.Request) -> None:
        if self.value is not None:
            request.headers[AFFINITY_HEADER] = self.value

    async def on_response(self, response: httpx2.Response) -> None:
        returned = response.headers.get(AFFINITY_HEADER)
        previous = self.value
        if returned:
            self.value = returned
            self.save()
        emit(
            "http_response",
            method=response.request.method,
            path=response.request.url.path,
            status=response.status_code,
            affinity=fingerprint(returned),
            affinity_changed=returned is not None and returned != previous,
            mcp_session_present=response.headers.get("MCP-Session-Id") is not None,
            content_type=response.headers.get("content-type"),
        )


def text_result(result: Any) -> str:
    if result.is_error:
        raise RuntimeError("the MCP tool reported an error")
    for content in result.content:
        text = getattr(content, "text", None)
        if isinstance(text, str):
            return text
    raise RuntimeError("the tool result did not contain text")


def state_for_worker(
    *,
    transport: Transport,
    state_file: Path | None,
    require_existing: bool,
) -> AffinityState:
    if transport != "direct":
        if state_file is not None:
            raise ValueError("affinity state is only valid with --transport direct")
        return AffinityState()
    return AffinityState.load(state_file, required=require_existing)


async def run_worker(
    *,
    name: str,
    url: str,
    transport: Transport,
    state: AffinityState,
    operation: Literal["smoke", "hold"],
    duration: float,
) -> None:
    headers: dict[str, str] = {}
    hooks: dict[str, list[Any]] = {}
    if transport == "direct":
        token = os.environ.get(TOKEN_ENV)
        if not token:
            raise RuntimeError(f"{TOKEN_ENV} is required for direct transport")
        headers["X-Access-Token"] = token
        hooks = {
            "request": [state.on_request],
            "response": [state.on_response],
        }

    read_timeout = max(300.0, duration + 120.0)
    timeout = httpx2.Timeout(120.0, read=read_timeout)
    async with (
        httpx2.AsyncClient(
            headers=headers,
            timeout=timeout,
            event_hooks=hooks,
        ) as http_client,
        streamable_http_client(url, http_client=http_client) as (read, write),
        ClientSession(
            read,
            write,
            read_timeout_seconds=read_timeout,
        ) as session,
    ):
        initialized = await session.initialize()
        emit(
            "initialize",
            worker=name,
            protocol=initialized.protocol_version,
            server=initialized.server_info.name,
            server_version=initialized.server_info.version,
            affinity=fingerprint(state.value),
        )
        emit("worker_ready", worker=name)

        listed = await session.list_tools()
        names = {tool.name for tool in listed.tools}
        required = {"echo", "trigger-long-running-operation"}
        missing = sorted(required - names)
        if missing:
            raise RuntimeError(f"required MCP tools are missing: {missing}")
        emit(
            "tools_list",
            worker=name,
            tool_count=len(names),
            required_present=True,
        )

        if operation == "smoke":
            result = await session.call_tool("echo", {"message": "ags-cookbook"})
            actual = text_result(result)
            if actual != "Echo: ags-cookbook":
                raise RuntimeError("the echo result did not match the expected value")
            emit("tool_call", worker=name, tool="echo", result="ok")
        else:
            emit(
                "tool_call_started",
                worker=name,
                tool="trigger-long-running-operation",
                duration=duration,
            )
            result = await session.call_tool(
                "trigger-long-running-operation",
                {"duration": duration, "steps": 3},
                read_timeout_seconds=duration + 120.0,
            )
            text_result(result)
            emit(
                "tool_call",
                worker=name,
                tool="trigger-long-running-operation",
                result="ok",
            )

    state.save()
    emit("worker_done", worker=name, affinity=fingerprint(state.value))


def add_connection_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--url", required=True)
    parser.add_argument(
        "--transport",
        choices=("local", "proxy", "direct"),
        required=True,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate an MCP server through an AGS Deployment",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    smoke = commands.add_parser("smoke")
    add_connection_arguments(smoke)
    smoke.add_argument("--state-file", type=Path)

    resume = commands.add_parser("resume")
    add_connection_arguments(resume)
    resume.add_argument("--state-file", type=Path, required=True)

    hold = commands.add_parser("hold")
    add_connection_arguments(hold)
    hold.add_argument("--workers", type=int, default=1)
    hold.add_argument("--duration", type=float, default=90.0)
    hold.add_argument("--state-dir", type=Path)

    return parser.parse_args()


async def run(args: argparse.Namespace) -> None:
    if args.command in {"smoke", "resume"}:
        state = state_for_worker(
            transport=args.transport,
            state_file=args.state_file,
            require_existing=args.command == "resume",
        )
        await run_worker(
            name="worker-1",
            url=args.url,
            transport=args.transport,
            state=state,
            operation="smoke",
            duration=0,
        )
        emit("command_done", command=args.command, succeeded=1, failed=0)
        return

    if args.workers < 1:
        raise ValueError("--workers must be at least 1")
    if args.duration <= 0:
        raise ValueError("--duration must be positive")
    if args.transport == "direct" and args.state_dir is None:
        raise ValueError("--state-dir is required for direct hold mode")
    if args.transport != "direct" and args.state_dir is not None:
        raise ValueError("--state-dir is only valid with --transport direct")

    async def checked_worker(index: int) -> bool:
        name = f"worker-{index}"
        path = args.state_dir / f"{name}.json" if args.state_dir else None
        state = state_for_worker(
            transport=args.transport,
            state_file=path,
            require_existing=False,
        )
        try:
            await run_worker(
                name=name,
                url=args.url,
                transport=args.transport,
                state=state,
                operation="hold",
                duration=args.duration,
            )
            return True
        except Exception as error:  # noqa: BLE001 - isolate and redact worker failures.
            state.save()
            emit("worker_failed", worker=name, error_type=type(error).__name__)
            return False

    results = await asyncio.gather(
        *(checked_worker(index) for index in range(1, args.workers + 1)),
    )
    succeeded = sum(results)
    failed = len(results) - succeeded
    emit("command_done", command="hold", succeeded=succeeded, failed=failed)
    if failed:
        raise RuntimeError("one or more native MCP workers failed")


def main() -> None:
    args = parse_args()
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        emit("command_failed", error_type="KeyboardInterrupt")
        raise SystemExit(130) from None
    except Exception as error:  # noqa: BLE001 - CLI output must not expose request data.
        emit("command_failed", error_type=type(error).__name__)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
