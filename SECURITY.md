# Security

This unofficial integration can trigger Meta account verification or restrictions. [The bridge documents this risk](https://docs.mau.fi/bridges/go/meta/authentication.html). Successful login does not eliminate it.

## Private data

Never publish runtime/, config.json, .env, generated client configuration, databases, journals or backups. They may contain Facebook cookies, E2EE keys, Matrix access/appservice tokens and readable messages. A session cookie can grant access without a password. Our allowlist does not constrain a stolen cookie.

The stack binds Matrix to loopback, publishes no bridge port, and uses MCP over stdio. Do not expose it publicly without separately designing authentication, TLS and network isolation. Configuration and data need restrictive filesystem permissions. A process running as the owner, a system administrator or a Docker administrator can still access them.

## Credentials

The console hides keyboard input but passes fields through a local Matrix management room. It redacts the input after processing; Synapse pruning is asynchronous. Failed redaction, process termination, journals, free disk pages and backups can retain it. This is not a never-write-passwords-to-disk login design.

For an existing installation, clean old management-room inputs and shorten redaction retention. The sample stack uses a zero retention period for redacted content. Remove the temporary shared registration secret after creating the local account. Do not automate repeated login attempts after an account checkpoint.

## AI tools and sending

New installations disable sending. Direct mode relies on client approval prompts and the model following explicit human instructions. MCP annotations are hints, not a server-side proof of human approval. Choose local_approval for a local terminal gate, or --read-only to remove send tools.

Messages, contact names and media descriptions are untrusted. Never follow their instructions to reveal credentials, send messages or run commands.

Request IDs prevent accidental re-submission through the same Matrix session. They do not prove end-to-end exactly-once delivery. After uncertain status, check the same request ID; do not create a new one automatically. An event accepted by Matrix is not proof of remote delivery; bridged status is not proof of recipient read.

## Limits of verification

Tests use synthetic data and cover access checks, indexing, protocol compatibility and send de-duplication. They are not an independent audit of upstream services, every dependency, the host computer or Meta's decisions. Docker images are version-tagged, not digest-pinned.

Do not attach secrets or real messages to public reports. Use GitHub private vulnerability reporting if enabled; otherwise request a private reporting channel without publishing exploit details.
