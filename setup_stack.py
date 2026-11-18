"""Generate isolated local bridge configuration. Requires a running Docker engine."""
import argparse
import secrets
import re
import shutil
import subprocess
import os
from pathlib import Path
import yaml
from messenger_mcp.files import private_directory

ROOT = Path(__file__).resolve().parent


def compose(*args):
    subprocess.run([docker_binary(), "compose", "-f", str(ROOT / "compose.yaml"), *args], cwd=ROOT, check=True, timeout=600)


def docker_binary():
    found = shutil.which("docker")
    if found:
        return found
    if os.name == "nt":
        for path in (Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/DockerDesktop/resources/bin/docker.exe",
                     Path("C:/Program Files/Docker/Docker/resources/bin/docker.exe")):
            if path.is_file():
                return str(path)
    raise SystemExit("Docker not found. Install Docker Desktop / Docker Compose first.")


def save(path, data):
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["prepare", "start", "stop", "status"])
    args = parser.parse_args()
    subprocess.run([docker_binary(), "info"], check=True, stdout=subprocess.DEVNULL, timeout=30)
    if args.action == "status":
        compose("ps")
        return
    if args.action == "stop":
        compose("stop")
        return
    if args.action == "start":
        if not (ROOT / "runtime/prepared").exists():
            raise SystemExit("Najpierw uruchom: python setup_stack.py prepare")
        compose("up", "-d")
        return
    synapse = ROOT / "runtime/synapse"
    meta = ROOT / "runtime/meta"
    if (synapse / "homeserver.yaml").exists() or (meta / "config.yaml").exists():
        raise SystemExit("Istnieje już konfiguracja. Nie nadpisano jej; sprawdź runtime/ i dokończ ręcznie według README.")
    private_directory(ROOT / "runtime")
    synapse.mkdir(parents=True, exist_ok=True)
    meta.mkdir(parents=True, exist_ok=True)
    # The mount target must exist as a file before Docker starts Synapse.
    (meta / "registration.yaml").touch(exist_ok=True)
    compose("run", "--rm", "--no-deps", "meta", "/usr/bin/mautrix-meta", "-e", "-c", "/data/config.yaml")
    template = yaml.safe_load((meta / "config.yaml").read_text(encoding="utf-8"))
    template["homeserver"].update(address="http://synapse:8008", domain="messenger.localhost")
    template["appservice"].update(address="http://meta:29319", public_address="", hostname="0.0.0.0")
    template["database"].update(type="sqlite3-fk-wal", uri="file:/data/bridge.db?_txlock=immediate")
    template["bridge"]["permissions"] = {"@owner:messenger.localhost": "admin"}
    template["bridge"]["portal_create_filter"] = {"mode": "allow", "list": [], "always_deny_from_login": []}
    template["network"]["thread_backfill"]["batch_count"] = 0
    template["matrix"]["federate_rooms"] = False
    template["encryption"].update(allow=False, default=False, require=False)
    template["double_puppet"]["secrets"] = {}
    template["double_puppet"]["servers"] = {}
    template["backfill"]["enabled"] = False
    template["provisioning"].update(shared_secret="disable", allow_matrix_auth=False, debug_endpoints=False)
    template["logging"] = {"min_level": "info", "writers": [{"type": "stdout", "format": "json"}]}
    save(meta / "config.yaml", template)
    compose("run", "--rm", "--no-deps", "synapse", "generate")
    config = yaml.safe_load((synapse / "homeserver.yaml").read_text(encoding="utf-8"))
    config.update(enable_registration=False, registration_shared_secret=secrets.token_hex(32),
                  trusted_key_servers=[], federation_domain_whitelist=[],
                  app_service_config_files=["/bridge/registration.yaml"], redaction_retention_period="0s")
    config["listeners"] = [{"port": 8008, "tls": False, "type": "http", "x_forwarded": False,
                            "bind_addresses": ["0.0.0.0"], "resources": [{"names": ["client"], "compress": False}]}]
    save(synapse / "homeserver.yaml", config)
    generate_registration(meta)
    (ROOT / "runtime/prepared").write_text("mautrix-meta v26.10\n", encoding="utf-8")
    print("Konfiguracja gotowa. Uruchom start, następnie utwórz lokalne konto Matrix zgodnie z README.")


def generate_registration(meta):
    config = yaml.safe_load((meta / "config.yaml").read_text(encoding="utf-8"))
    as_token, hs_token = secrets.token_hex(32), secrets.token_hex(32)
    config["appservice"].update(as_token=as_token, hs_token=hs_token)
    def resolve(value):
        if isinstance(value, dict):
            return {k: resolve(v) for k, v in value.items()}
        if isinstance(value, list):
            return [resolve(v) for v in value]
        return secrets.token_hex(32) if value == "generate" else value
    config = resolve(config)
    save(meta / "config.yaml", config)
    domain = re.escape(config["homeserver"]["domain"])
    save(meta / "registration.yaml", {
        "id": "facebook", "url": "http://meta:29319", "as_token": as_token, "hs_token": hs_token,
        "sender_localpart": secrets.token_hex(16), "rate_limited": False,
        "namespaces": {"users": [{"regex": "^@facebookbot:" + domain + "$", "exclusive": True},
                                  {"regex": "^@facebook_.*:" + domain + "$", "exclusive": True}]},
        "de.sorunome.msc2409.push_ephemeral": True, "receive_ephemeral": True})


if __name__ == "__main__":
    main()
