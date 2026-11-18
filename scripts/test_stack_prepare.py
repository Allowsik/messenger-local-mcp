"""Optional Docker smoke test: isolated new configs, no account or Messenger login."""
import shutil
import sys
import tempfile
import uuid
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import setup_stack

runtime = ROOT / "runtime"
runtime.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(prefix="stack-check-", dir=runtime) as directory:
    fixture = Path(directory).resolve()
    fixture.relative_to(runtime.resolve())
    compose = yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))
    compose["name"] = "messenger-mcp-check-" + uuid.uuid4().hex[:8]
    (fixture / "compose.yaml").write_text(yaml.safe_dump(compose), encoding="utf-8")
    setup_stack.ROOT = fixture
    sys.argv = ["setup_stack.py", "prepare"]
    try:
        setup_stack.main()
        bridge = yaml.safe_load((fixture / "runtime/meta/config.yaml").read_text(encoding="utf-8"))
        registration = yaml.safe_load((fixture / "runtime/meta/registration.yaml").read_text(encoding="utf-8"))
        hs = yaml.safe_load((fixture / "runtime/synapse/homeserver.yaml").read_text(encoding="utf-8"))
        assert bridge["appservice"]["as_token"] == registration["as_token"]
        assert bridge["appservice"]["hs_token"] == registration["hs_token"]
        assert bridge["bridge"]["portal_create_filter"]["list"] == []
        assert hs["redaction_retention_period"] == "0s"
        assert hs["enable_registration"] is False
        print("Isolated stack preparation OK: generated upstream config, matching registration, empty allowlist; no login.")
    finally:
        setup_stack.compose("down")
