# Contributing

Use Python 3.11+ and install with python -m pip install -e .

Run python -m unittest discover -s tests -v, python tests/smoke_mcp.py and python scripts/check_release.py. Tests must use synthetic data, never a personal account or real message send. Optional Docker verification: python scripts/test_stack_prepare.py generates a separate temporary stack without logging into Facebook.

Server stdout is exclusively for MCP messages. Do not log credentials or raw upstream error bodies. Enforce allowlists in code, retain uncertain send states and preserve request IDs across retries.

Runtime data and personal development transcripts must not enter Git, wheels, source archives or issue attachments. The release scanner supplements human review; it cannot prove absence of every possible secret.
