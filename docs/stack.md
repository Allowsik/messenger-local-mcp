# Stack operations

The included Compose stack publishes only 127.0.0.1:18008. Private data lives in runtime/.

~~~powershell
python setup_stack.py prepare
python setup_stack.py start
python setup_stack.py status
python setup_stack.py stop
~~~

Preparation refuses to overwrite configuration. If interrupted, inspect existing files; do not delete an installation containing messages or device keys. Keep E2EE state across restarts.

Configuration disables mass backfill, unrestricted portal creation, public media, provisioning, room federation and additional Matrix-room encryption. SQLite suits a single local prototype; consider PostgreSQL for sustained larger deployments.

After creating the local Matrix account, remove registration_shared_secret from runtime/synapse/homeserver.yaml and restart Synapse. The MCP server never automatically logs into Facebook.

The bridge runs with --no-update. Review configuration changes before upgrading image tags. Starting/stopping preserves data; backups contain secrets and require equal protection.
