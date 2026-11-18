"""Exercise the real stdio transport with synthetic data from an unrelated CWD."""
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def check(config, cwd, read_only=False):
    params = StdioServerParameters(command=sys.executable,
        args=["-X", "utf8", "-m", "messenger_mcp.server", "--config", str(config)] + (["--read-only"] if read_only else []),
        cwd=str(cwd))
    async with stdio_client(params) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            listed = await session.list_tools()
            names = {t.name for t in listed.tools}
            expected = {"get_status", "list_chats", "get_messages", "search_messages", "refresh_messages"}
            if not read_only:
                expected |= {"send_message", "get_send_status"}
            assert names == expected, names
            assert not (await session.call_tool("list_chats", {})).isError
            assert not (await session.call_tool("get_status", {"check_connection": False})).isError
            assert not (await session.call_tool("get_messages", {"chat": "Synthetic contact", "refresh": False})).isError
            assert (await session.call_tool("get_messages", {"chat": "!denied:invalid", "refresh": False})).isError
            if not read_only:
                assert (await session.call_tool("send_message", {"chat": "Synthetic contact", "text": "Synthetic only", "request_id": "synthetic-disabled"})).isError


async def main():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        config = root / "config.json"
        config.write_text(json.dumps({"homeserver": "http://127.0.0.1:9", "user_id": "@synthetic:test",
            "allowed_rooms": {"!allowed:test": "Synthetic contact"}, "send_mode": "disabled"}), encoding="utf-8")
        await check(config, root)
        await check(config, root, read_only=True)
    print("MCP stdio OK: normal/read-only schemas, fresh process in unrelated CWD, denied chat, disabled send; synthetic data only.")


if __name__ == "__main__":
    asyncio.run(main())
