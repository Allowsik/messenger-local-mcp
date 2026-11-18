"""Check the public source set for accidentally tracked private installation data."""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = {".gitignore", ".gitattributes", "README.md", "LICENSE", "SECURITY.md", "THIRD_PARTY.md", "CONTRIBUTING.md",
         "pyproject.toml", "MANIFEST.in", "requirements.txt", "config.example.json", "compose.yaml", "setup_stack.py", "launch_mcp.py", "run-mcp.ps1"}
DIRECTORIES = {"messenger_mcp", "tests", "scripts", "docs", "examples", ".github"}
PRIVATE_NAMES = {"config.json", "session.json", "cookies.json", "homeserver.yaml", "registration.yaml", "security-audit-summary.json"}


def candidates():
    git = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True)
    if git.returncode == 0 and git.stdout:
        return [Path(name) for name in git.stdout.decode().split("\0") if name]
    paths = [Path(name) for name in FILES if (ROOT / name).is_file()]
    for directory in DIRECTORIES:
        paths.extend(path.relative_to(ROOT) for path in (ROOT / directory).rglob("*")
                     if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc")
    return paths


def main():
    failures = []
    paths = candidates()
    for relative in paths:
        parts = relative.parts
        name = relative.name
        if parts[0] not in DIRECTORIES and relative.as_posix() not in FILES:
            failures.append((str(relative), "unexpected public path"))
        if name in PRIVATE_NAMES or name.startswith(".env") or ".db" in name or ".sqlite" in name:
            failures.append((str(relative), "private runtime/configuration filename"))
        data = (ROOT / relative).read_bytes()
        if b"\x00" in data:
            failures.append((str(relative), "unexpected binary file"))
            continue
        value = data.decode("utf-8-sig")
        rules = [
            (r"(?i)BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY", "private key"),
            (r"(?i)(?:ghp_|github_pat_|sk-proj-)[A-Za-z0-9_]{20,}", "credential-shaped value"),
            (r"(?i)[A-Z]:[/\\]Users[/\\](?!example(?:[/\\]|$)|YOUR_USER(?:[/\\]|$))[^/\\\s]+[/\\]", "personal absolute path"),
            (r"(?i)(?:access_token|as_token|hs_token|password)\s*[\"']?\s*[:=]\s*[\"'][A-Za-z0-9_+/=-]{32,}[\"']", "hardcoded credential-shaped value"),
            (r"\b\d{14,18}\b", "possible personal platform identifier"),
        ]
        for pattern, label in rules:
            if re.search(pattern, value):
                failures.append((str(relative), label))
    if failures:
        for path, reason in sorted(set(failures)):
            print(f"FAIL: {path}: {reason}")
        raise SystemExit(1)
    print(f"Public source check passed: {len(paths)} text files; no matching private paths, databases or credential patterns.")
    print("This pattern check supplements human review; it is not proof that all possible secrets are absent.")


if __name__ == "__main__":
    main()
