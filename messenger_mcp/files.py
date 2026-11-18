"""Private runtime directories and atomic JSON writes."""
import json
import os
import subprocess
import tempfile
import csv
import re
from pathlib import Path


def private_directory(path):
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name == "nt":
        identity = subprocess.check_output(["whoami", "/user", "/fo", "csv", "/nh"]).decode("utf-8", errors="replace")
        sid = next(csv.reader(identity.splitlines()))[-1]
        if not re.fullmatch(r"S-[0-9-]+", sid):
            raise OSError("Cannot determine the current Windows account SID.")
        subprocess.run(["icacls", str(path), "/inheritance:r", "/grant:r",
                        "*" + sid + ":(OI)(CI)F", "*S-1-5-18:(OI)(CI)F", "*S-1-5-32-544:(OI)(CI)F"],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["icacls", str(path), "/remove:g", "*S-1-5-32-545", "*S-1-1-0", "*S-1-5-11"],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        path.chmod(0o700)


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, prefix=".mcp-", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
        temporary.replace(path)
        if os.name != "nt":
            path.chmod(0o600)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()
