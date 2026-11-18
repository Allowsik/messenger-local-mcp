"""Local administration; these operations are deliberately not exposed to AI tools."""
import importlib.metadata
import json
import sys
import sqlite3
from pathlib import Path
from .core import App, MatrixError

DEFAULT_CONFIG = {"homeserver": "http://127.0.0.1:18008", "user_id": "@owner:messenger.localhost",
                  "allowed_rooms": {}, "database": "runtime/messages.sqlite3",
                  "bridge_database": "runtime/meta/bridge.db", "send_mode": "disabled"}


def doctor(app):
    result = {"python": sys.version.split()[0], "mcp_sdk": importlib.metadata.version("mcp"),
              "config": str(app.path), "allowed_chats": len(app.rooms),
              "send_mode": app.config.get("send_mode", "disabled"), "session_saved": app.session_path.is_file(),
              "automatic_facebook_login": False}
    try:
        app.matrix().request("GET", "/account/whoami")
        result["matrix_connected"] = True
    except (ValueError, MatrixError) as exc:
        result.update(matrix_connected=False, error=str(exc))
    try:
        with app.db() as db:
            db.execute("SELECT COUNT(*) FROM updates").fetchone()
        result["index_writable"] = True
    except (OSError, sqlite3.Error):
        result["index_writable"] = False
    return result


def client_configs(app, output=None):
    command = str(Path(sys.executable).resolve())
    args = ["-X", "utf8", "-m", "messenger_mcp.server", "--config", str(app.path)]
    entry = {"type": "stdio", "command": command, "args": args}
    desktop_entry = {"command": command, "args": args}
    codex = ("[mcp_servers.messenger]\ncommand = " + json.dumps(command) + "\nargs = " + json.dumps(args) +
             "\nstartup_timeout_sec = 30\ntool_timeout_sec = 120\n")
    values = {"codex.toml": codex,
              "claude-code.mcp.json": json.dumps({"mcpServers": {"messenger": entry}}, indent=2) + "\n",
              "claude-desktop.json": json.dumps({"mcpServers": {"messenger": desktop_entry}}, indent=2) + "\n"}
    if output:
        directory = Path(output).expanduser().resolve()
        directory.mkdir(parents=True, exist_ok=True)
        for name, value in values.items():
            path = directory / name
            path.write_text(value, encoding="utf-8")
        return {"directory": str(directory), "files": list(values), "contains_credentials": False}
    return {"codex_toml": codex, "claude_code": {"mcpServers": {"messenger": entry}},
            "claude_desktop": {"mcpServers": {"messenger": desktop_entry}}}
