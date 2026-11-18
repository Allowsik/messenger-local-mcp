$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
& "$PSScriptRoot\.venv\Scripts\python.exe" -X utf8 -m messenger_mcp.server
exit $LASTEXITCODE
