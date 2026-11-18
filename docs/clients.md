# Client setup

First install this package into its virtual environment. Generated launch commands use absolute paths and work from unrelated working directories.

~~~powershell
.\.venv\Scripts\python.exe -m messenger_mcp clients --output runtime/clients
~~~

Merge only the messenger entry, preserving existing servers. Generated files are local installation data.

## Codex

Merge codex.toml into ~/.codex/config.toml, or use the real paths from the generator:

~~~powershell
codex mcp add messenger -- 'C:\path\to\repo\.venv\Scripts\python.exe' -X utf8 -m messenger_mcp.server --config 'C:\path\to\repo\config.json'
codex mcp get messenger
~~~

Restart/reload the client to discover tools. Keep sending approval prompts enabled. [Official documentation](https://developers.openai.com/codex/mcp)

## Claude Code

~~~powershell
claude mcp add --transport stdio --scope user messenger -- 'C:\path\to\repo\.venv\Scripts\python.exe' -X utf8 -m messenger_mcp.server --config 'C:\path\to\repo\config.json'
claude mcp get messenger
~~~

Or merge claude-code.mcp.json into the appropriate .mcp.json. Avoid committing personal absolute paths in project scope. Use /mcp to inspect status. [Official documentation](https://code.claude.com/docs/en/mcp)

## Claude Desktop

Use its developer settings to open the local MCP configuration and merge mcpServers.messenger from claude-desktop.json. Preserve other entries, then restart the app. A standard Windows installation uses %APPDATA%\Claude\claude_desktop_config.json; check the location in your version. [Local-server guide](https://modelcontextprotocol.io/docs/develop/connect-local-servers)

## Read-only instance

Append --read-only to the launch arguments. This removes send_message and get_send_status even when another client has sending enabled.

## Troubleshooting

Run messenger-mcp doctor. If Matrix is stopped, check Docker/Synapse rather than entering the Facebook password again. Empty allowlists need local configuration. Inspect sync.sync_error for stale reads. After an accepted send, check the same request ID. Facebook checkpoints require action in the official app.
