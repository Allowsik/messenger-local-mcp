import argparse
import getpass
import json
import sys
import time
import uuid
import sqlite3
from pathlib import Path
from urllib.parse import quote
from .core import App, Matrix, ROOT, MatrixError, default_config_path
from .admin import DEFAULT_CONFIG, doctor, client_configs
from .files import write_json, private_directory


def room_info(client, room):
    state = client.request("GET", f"/rooms/{quote(room, safe='')}/state")
    name, members, portal, encrypted = None, [], False, False
    for event in state:
        c = event.get("content", {})
        if event["type"] == "m.room.name":
            name = c.get("name")
        if event["type"] in ("m.bridge", "uk.half-shot.bridge"):
            portal = True
        if event["type"] == "m.room.encryption":
            encrypted = True
        if event["type"] == "m.room.member" and c.get("membership") == "join":
            members.append({"id": event["state_key"], "name": c.get("displayname")})
    return {"room_id": room, "name": name, "members": members, "bridge": portal, "encrypted_matrix": encrypted}


def redact_input(client, room, event_id):
    client.request("PUT", f"/rooms/{quote(room, safe='')}/redact/{quote(event_id, safe='')}/{uuid.uuid4().hex}",
                   {"reason": "Remove local management input after processing"})


class BotReplies:
    def __init__(self, client, room, bot):
        self.client = client
        self.filter = json.dumps({"presence": {"types": []}, "account_data": {"types": []},
            "room": {"rooms": [room], "state": {"types": []}, "ephemeral": {"types": []},
                     "account_data": {"types": []}, "timeline": {"types": ["m.room.message"], "senders": [bot], "limit": 100}}})
        self.room = room
        self.cursor = None
        # Establish a stream boundary before sending anything; historical prompts
        # must never be mistaken for the response to a new credential.
        self.poll(0, discard=True)
        # Initial /sync responses may be cached. Drain their incremental backlog
        # before sending a command so an older bot reply cannot answer it.
        for _ in range(10):
            if not self.poll(0):
                break
        else:
            raise ValueError("Pokój zarządzania nadal ma zaległe odpowiedzi; spróbuj ponownie za chwilę.")

    def poll(self, timeout=1500, discard=False):
        query = {"timeout": timeout, "filter": self.filter, "set_presence": "offline"}
        if self.cursor:
            query["since"] = self.cursor
        result = self.client.request("GET", "/sync", query=query)
        self.cursor = result["next_batch"]
        events = result.get("rooms", {}).get("join", {}).get(self.room, {}).get("timeline", {}).get("events", [])
        if discard:
            return []
        return [e["content"]["body"] for e in events
                if isinstance(e.get("content", {}).get("body"), str)]

    def wait(self, seconds=45):
        deadline = time.monotonic() + seconds
        found = False
        while time.monotonic() < deadline:
            replies = self.poll()
            for body in replies:
                print(body, flush=True)
                # Room setup messages are not answers to login or credentials.
                if not body.startswith(("Hello, I'm a", "This room has been marked")):
                    found = True
            if found and not replies:
                return True
        return found


def bridge_login(app):
    client = app.matrix()
    bot = "@facebookbot:" + app.config["user_id"].split(":", 1)[1]
    session = json.loads(app.session_path.read_text(encoding="utf-8"))
    room = session.get("management_room")
    if not room:
        room = client.request("POST", "/createRoom", {"is_direct": True, "invite": [bot], "preset": "private_chat", "name": "Messenger bridge login"})["room_id"]
        session["management_room"] = room
        write_json(app.session_path, session)
    path = f"/rooms/{quote(room, safe='')}/send/m.room.message/"
    replies = BotReplies(client, room, bot)
    print("Pokój logowania:", room)
    print("Wpisz /restart, aby rozpocząć logowanie od nowa; /wait czeka na odpowiedź; /quit kończy.")
    print("Odpowiedzi i dane logowania wpisujesz lokalnie, bez echa. Nie wklejaj ich do czatu z asystentem.")
    while True:
        command = getpass.getpass("Odpowiedź dla mostu: ")
        if command == "/quit":
            break
        if not command:
            continue
        if command == "/wait":
            replies.wait()
            continue
        if command == "/restart":
            client.request("PUT", path + uuid.uuid4().hex, {"msgtype": "m.text", "body": "!fb cancel"})
            if not replies.wait():
                print("Brak potwierdzenia anulowania. Użyj /wait; nie wpisuj jeszcze danych logowania.")
                continue
            command = "login messenger-lite"
        sent = client.request("PUT", path + uuid.uuid4().hex, {"msgtype": "m.text", "body": command})
        command = ""
        try:
            if not replies.wait():
                print("Brak odpowiedzi po 45 s. Wpisz /wait; nie ponawiaj hasła ani polecenia logowania.")
        finally:
            # The owner can redact their own input even when the bot lacks
            # permission to redact another sender's credential message.
            try:
                redact_input(client, room, sent["event_id"])
            except MatrixError:
                print("UWAGA: nie udało się usunąć wpisu z lokalnego pokoju zarządzania.")


def main():
    p = argparse.ArgumentParser(description="Lokalny Messenger / MCP — konfiguracja bez przekazywania sekretów asystentowi")
    p.add_argument("--config", type=Path, default=default_config_path())
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("init")
    sub.add_parser("login")
    sub.add_parser("rooms")
    sub.add_parser("invitations")
    j = sub.add_parser("join")
    j.add_argument("room_id")
    remote = sub.add_parser("select-chat")
    remote.add_argument("chat_id")
    sub.add_parser("bridge-login")
    sub.add_parser("status")
    sub.add_parser("doctor")
    clients = sub.add_parser("clients")
    clients.add_argument("--output", type=Path)
    sending = sub.add_parser("sending")
    sending.add_argument("mode", choices=["disabled", "direct", "local_approval"])
    outbox = sub.add_parser("outbox")
    outbox.add_argument("request_id", nargs="?")
    approve = sub.add_parser("approve")
    approve.add_argument("request_id")
    reject = sub.add_parser("reject")
    reject.add_argument("request_id")
    a = sub.add_parser("allow")
    a.add_argument("room_id")
    a.add_argument("name")
    r = sub.add_parser("revoke")
    r.add_argument("room_id")
    s = sub.add_parser("refresh")
    s.add_argument("room_id", nargs="?")
    s.add_argument("--pages", type=int, default=5)
    s.add_argument("--watch", action="store_true")
    args = p.parse_args()
    if args.command == "init":
        if args.config.exists():
            raise ValueError("Konfiguracja już istnieje; nie nadpisano jej.")
        write_json(args.config, DEFAULT_CONFIG)
        private_directory(args.config.resolve().parent / "runtime")
        print("Utworzono config.json. Lista dozwolonych rozmów jest pusta.")
        return
    app = App(args.config)
    if args.command == "doctor":
        print(json.dumps(doctor(app), ensure_ascii=False, indent=2))
    elif args.command == "clients":
        print(json.dumps(client_configs(app, args.output), ensure_ascii=False, indent=2))
    elif args.command == "sending":
        app.config["send_mode"] = args.mode
        write_json(app.path, app.config)
        print("Sending mode:", args.mode)
    elif args.command == "outbox":
        from .sending import send_status, public_record
        if args.request_id:
            result = send_status(app, args.request_id)
        else:
            with app.db() as db:
                result = [public_record(app, row) for row in db.execute("SELECT * FROM outbox ORDER BY created DESC LIMIT 20") if row["room"] in app.rooms]
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command in ("approve", "reject"):
        from .sending import approve, send_status
        print(json.dumps(send_status(app, args.request_id), ensure_ascii=False, indent=2))
        if input("Confirm this local decision? Type YES: ") == "YES":
            approve(app, args.request_id, args.command == "approve")
            print("Updated. The MCP client can now re-use the same request_id.")
    elif args.command == "login":
        private_directory(app.session_path.parent)
        password = getpass.getpass("Hasło lokalnego konta Matrix (nie hasło Facebooka): ")
        client = Matrix(app.config["homeserver"])
        result = client.request("POST", "/login", {"type": "m.login.password", "identifier": {"type": "m.id.user", "user": app.config["user_id"]}, "password": password, "initial_device_display_name": "Messenger local MCP"})
        write_json(app.session_path, {"homeserver": app.config["homeserver"], "user_id": result["user_id"], "access_token": result["access_token"], "device_id": result.get("device_id")})
        print("Sesja zapisana lokalnie. Token nie jest wyświetlany.")
    elif args.command == "bridge-login":
        bridge_login(app)
    elif args.command == "status":
        print(json.dumps({"homeserver": app.config["homeserver"], "allowed_rooms": len(app.rooms), "session_saved": app.session_path.exists(), "send_mode": app.config.get("send_mode", "disabled")}, indent=2))
        if app.session_path.exists():
            me = app.matrix().request("GET", "/account/whoami")
            print("Połączenie Matrix OK:", me["user_id"])
    elif args.command == "rooms":
        client = app.matrix()
        joined = client.request("GET", "/joined_rooms")["joined_rooms"]
        for room in joined:
            print(json.dumps(room_info(client, room), ensure_ascii=False))
        print("Pokazano metadane, bez treści rozmów. Zaproszenia muszą zostać zaakceptowane lokalnie.")
    elif args.command == "invitations":
        result = app.matrix().request("GET", "/sync", query={"timeout": 0, "filter": json.dumps({"presence": {"types": []}, "room": {"timeline": {"limit": 0}, "ephemeral": {"types": []}}})})
        for room, data in result.get("rooms", {}).get("invite", {}).items():
            names = [e.get("content", {}).get("name") for e in data.get("invite_state", {}).get("events", []) if e.get("type") == "m.room.name"]
            print(json.dumps({"room_id": room, "names": names}, ensure_ascii=False))
    elif args.command == "join":
        if input(f"Dołączyć lokalnie do {args.room_id}? Wpisz TAK: ") == "TAK":
            app.matrix().request("POST", f"/join/{quote(args.room_id, safe='')}", {})
            print("Dołączono. Dostęp MCP wymaga jeszcze polecenia allow.")
    elif args.command == "select-chat":
        import yaml
        path = ROOT / "runtime/meta/config.yaml"
        if not path.exists():
            raise ValueError("Najpierw przygotuj lokalną konfigurację mostu przez setup_stack.py prepare.")
        config = yaml.safe_load(path.read_text(encoding="utf-8"))
        config["bridge"]["portal_create_filter"] = {"mode": "allow", "list": [args.chat_id], "always_deny_from_login": []}
        path.write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=False), encoding="utf-8")
        print("Most dopuści automatyczne utworzenie tylko wybranego portalu. Uruchom: docker compose restart meta")
        print("Zmiana filtra nie usuwa wcześniej utworzonych portali. Lista dostępu MCP pozostaje osobna.")
    elif args.command == "allow":
        info = room_info(app.matrix(), args.room_id)
        if not info["bridge"] or info["encrypted_matrix"]:
            raise ValueError("Wymagany jest pokój mostu bez szyfrowania Matrix.")
        print(json.dumps(info, ensure_ascii=False, indent=2))
        if input("Udostępnić tę rozmowę przez MCP? Wpisz TAK: ") != "TAK":
            print("Anulowano.")
            return
        app.rooms[args.room_id] = args.name
        app.config["allowed_rooms"] = app.rooms
        write_json(app.path, app.config)
        print("Dodano rozmowę do listy MCP.")
    elif args.command == "revoke":
        app.rooms.pop(args.room_id, None)
        app.config["allowed_rooms"] = app.rooms
        write_json(app.path, app.config)
        with app.db() as db:
            db.execute("DELETE FROM messages WHERE room=?", (args.room_id,))
            db.execute("DELETE FROM updates WHERE room=?", (args.room_id,))
            db.execute("DELETE FROM edits WHERE room=?", (args.room_id,))
            db.execute("DELETE FROM redactions WHERE room=?", (args.room_id,))
        print("Cofnięto dostęp i usunięto wpisy z indeksu. Kopie Matrix/mostu pozostają.")
    elif args.command == "refresh":
        room = args.room_id
        if room is None:
            if len(app.rooms) != 1:
                raise ValueError("Podaj room_id lub skonfiguruj dokładnie jedną dozwoloną rozmowę.")
            room = next(iter(app.rooms))
        while True:
            try:
                print(json.dumps(App(args.config).refresh(room, args.pages), ensure_ascii=False), flush=True)
            except MatrixError as exc:
                print(str(exc), file=sys.stderr, flush=True)
                if not args.watch or exc.status in (401, 403):
                    raise
                print("Matrix unavailable; retrying in 30 seconds. No Facebook login will be attempted.", file=sys.stderr)
            if not args.watch:
                break
            time.sleep(30)


def entrypoint():
    try:
        main()
    except (ValueError, MatrixError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
    except (OSError, sqlite3.Error) as exc:
        print(f"Local data is unavailable ({type(exc).__name__}). Check file permissions and run messenger-mcp doctor.", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    entrypoint()
