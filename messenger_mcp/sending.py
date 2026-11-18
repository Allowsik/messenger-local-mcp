"""Durable, idempotent text sends shared by concurrent MCP clients."""
import hashlib
import re
import sqlite3
import time
from urllib.parse import quote
from .core import MatrixError


def public_record(app, row):
    return {"request_id": row["request_id"], "room_id": row["room"], "chat_name": app.rooms[row["room"]],
            "text": row["body"], "status": row["status"], "event_id": row["event"],
            "updated_at": row["updated"], "error": row["error"], "recipient_read_status": "not checked"}


def send_status(app, request_id):
    with app.db() as db:
        row = db.execute("SELECT * FROM outbox WHERE request_id=?", (request_id,)).fetchone()
        if row is None:
            raise ValueError("Unknown request_id.")
        app.check_room(row["room"])
        if row["event"] and row["status"] != "bridged":
            path = app.base / app.config.get("bridge_database", "runtime/meta/bridge.db")
            if path.is_file():
                try:
                    bridge = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=2)
                    try:
                        mapped = bridge.execute("SELECT id FROM message WHERE mxid=?", (row["event"],)).fetchone()
                    finally:
                        bridge.close()
                    if mapped and mapped[0]:
                        db.execute("UPDATE outbox SET status='bridged',updated=?,error=NULL WHERE request_id=?", (time.time(), request_id))
                except sqlite3.Error:
                    pass
        result = public_record(app, db.execute("SELECT * FROM outbox WHERE request_id=?", (request_id,)).fetchone())
    if result["status"] in ("submitting", "uncertain", "accepted"):
        result["next_action"] = "Check get_send_status with this request_id. Never generate a new ID merely because confirmation is delayed."
    return result


def send_text(app, room, text, request_id):
    app.check_room(room)
    mode = app.config.get("send_mode", "disabled")
    if mode == "disabled":
        raise ValueError("Sending is disabled locally. Enable it with messenger-mcp sending direct.")
    if not isinstance(text, str) or not text.strip() or len(text) > 10000:
        raise ValueError("Message text must contain 1–10000 characters.")
    if not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,128}", request_id):
        raise ValueError("request_id must contain 8–128 ASCII letters, digits, underscores or hyphens.")
    client = app.matrix()
    token_hash = hashlib.sha256(client.token.encode()).hexdigest()
    now = time.time()
    with app.db() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT * FROM outbox WHERE request_id=?", (request_id,)).fetchone()
        if row:
            if row["room"] != room or row["body"] != text:
                raise ValueError("This request_id already belongs to a different recipient or message.")
            if row["status"] in ("accepted", "bridged", "submitting", "rejected"):
                return public_record(app, row)
            if row["token_hash"] != token_hash:
                raise ValueError("Matrix session changed. Reconcile this send before retrying; a new request may duplicate it.")
        else:
            initial = "pending_approval" if mode == "local_approval" else "prepared"
            db.execute("INSERT INTO outbox VALUES (?,?,?,?,?,?,NULL,?,NULL)", (request_id, room, text, initial, now, now, token_hash))
            row = db.execute("SELECT * FROM outbox WHERE request_id=?", (request_id,)).fetchone()
        if row["status"] == "pending_approval":
            return public_record(app, row)
        if mode == "local_approval" and row["status"] != "approved":
            db.execute("UPDATE outbox SET status='pending_approval',updated=? WHERE request_id=?", (now, request_id))
            return public_record(app, db.execute("SELECT * FROM outbox WHERE request_id=?", (request_id,)).fetchone())
        db.execute("UPDATE outbox SET status='submitting',updated=?,error=NULL WHERE request_id=?", (now, request_id))
    # Matrix transaction IDs are scoped to the access token. Forbid replay after
    # a new login changes that scope, rather than risking a duplicate message.
    transaction = "mcp-" + hashlib.sha256(request_id.encode()).hexdigest()
    try:
        response = client.request("PUT", f"/rooms/{quote(room,safe='')}/send/m.room.message/{transaction}", {"msgtype": "m.text", "body": text})
        event = response["event_id"]
    except (MatrixError, KeyError):
        with app.db() as db:
            db.execute("UPDATE outbox SET status='uncertain',updated=?,error=? WHERE request_id=?",
                       (time.time(), "Matrix did not confirm. Reuse this request_id if explicitly retrying.", request_id))
        return send_status(app, request_id)
    with app.db() as db:
        db.execute("UPDATE outbox SET status='accepted',updated=?,event=? WHERE request_id=?", (time.time(), event, request_id))
    return send_status(app, request_id)


def approve(app, request_id, accepted):
    with app.db() as db:
        row = db.execute("SELECT * FROM outbox WHERE request_id=?", (request_id,)).fetchone()
        if row is None:
            raise ValueError("Unknown request_id.")
        app.check_room(row["room"])
        if row["status"] != "pending_approval":
            raise ValueError("Only a pending draft can be approved or rejected.")
        db.execute("UPDATE outbox SET status=?,updated=? WHERE request_id=?", ("approved" if accepted else "rejected", time.time(), request_id))
