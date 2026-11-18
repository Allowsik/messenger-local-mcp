"""Install only this MCP entry, preserving unrelated client configuration."""
import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from messenger_mcp.core import App
from messenger_mcp.files import write_json

p = argparse.ArgumentParser()
p.add_argument("client", choices=["codex", "claude-code", "claude-desktop"])
args = p.parse_args()
app = App()
command = str(Path(sys.executable).resolve())
launch_args = ["-X", "utf8", "-m", "messenger_mcp.server", "--config", str(app.path)]
if args.client == "codex":
    executable = shutil.which("codex")
    if not executable:
        raise SystemExit("Codex CLI not found. Use the generated configuration snippet.")
    before = subprocess.run([executable, "mcp", "list", "--json"], capture_output=True, text=True, encoding="utf-8", check=True)
    existing = json.loads(before.stdout)
    if any(row.get("name") == "messenger" for row in existing):
        raise SystemExit("An entry named messenger already exists; inspect it before replacing it.")
    subprocess.run([executable, "mcp", "add", "messenger", "--", command, *launch_args], check=True)
    print("Codex messenger entry installed. Other entries were preserved.")
else:
    home = Path.home()
    if args.client == "claude-code":
        path = home / ".claude.json"
        entry = {"type": "stdio", "command": command, "args": launch_args}
    else:
        import os
        path = Path(os.environ.get("APPDATA", home / "Library/Application Support")) / "Claude/claude_desktop_config.json"
        entry = {"command": command, "args": launch_args}
    current = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    servers = current.setdefault("mcpServers", {})
    if "messenger" in servers and servers["messenger"] != entry:
        raise SystemExit("A different messenger entry exists. No configuration was overwritten.")
    if path.exists():
        backup = app.base / "runtime/client-config-backups" / (args.client + "-" + str(time.time_ns()) + ".json")
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup)
    servers["messenger"] = entry
    write_json(path, current)
    print(args.client + " messenger entry installed. Other settings preserved; private backup retained locally.")
