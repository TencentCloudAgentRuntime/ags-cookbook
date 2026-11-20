import asyncio
import json
import os
from urllib.parse import urlsplit

import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.types import PaginatedRequestParams


async def run(
    url: str, token: str, tool_name: str | None, arguments: dict
) -> str | None:
    async with httpx2.AsyncClient(
        headers={"Authorization": f"Bearer {token}"},
        timeout=30.0,
    ) as http:
        async with streamable_http_client(
            url, http_client=http, terminate_on_close=True
        ) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                tools = []
                cursor = None
                while True:
                    params = PaginatedRequestParams(cursor=cursor) if cursor else None
                    page = await session.list_tools(params=params)
                    tools.extend(page.tools)
                    cursor = page.next_cursor
                    if cursor is None:
                        break
                print(
                    json.dumps(
                        {
                            "tools": [
                                tool.model_dump(
                                    mode="json",
                                    by_alias=True,
                                    exclude_none=True,
                                    include={"name", "input_schema", "meta"},
                                )
                                for tool in tools
                            ]
                        },
                        ensure_ascii=False,
                    )
                )

                if tool_name is None:
                    return None
                if tool_name not in {tool.name for tool in tools}:
                    return "MCP_TOOL_NAME must match a name returned by tools/list."
                result = await session.call_tool(tool_name, arguments=arguments)
                print(result.model_dump_json(by_alias=True, exclude_none=True))
                return "The MCP tool reported an error." if result.is_error else None


def main() -> None:
    url = os.environ.get("ENDPOINT_MCP_URL", "")
    token = os.environ.get("ENDPOINT_TOKEN", "")
    tool_name = os.environ.get("MCP_TOOL_NAME") or None
    address = urlsplit(url)
    if address.scheme != "https" or not address.hostname or address.username is not None:
        raise SystemExit("Set ENDPOINT_MCP_URL to the HTTPS MCPURL returned by agr.")
    if not token:
        raise SystemExit("Set ENDPOINT_TOKEN to the bearer token returned by agr.")

    try:
        arguments = json.loads(os.environ.get("MCP_TOOL_ARGS", "{}"))
    except json.JSONDecodeError:
        raise SystemExit("MCP_TOOL_ARGS must be a JSON object.") from None
    if not isinstance(arguments, dict):
        raise SystemExit("MCP_TOOL_ARGS must be a JSON object.")

    error = asyncio.run(run(url, token, tool_name, arguments))
    if error:
        raise SystemExit(error)


if __name__ == "__main__":
    main()
