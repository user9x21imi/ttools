"""Authenticated localhost commands for desktop shortcuts; only forwards explicit user actions."""

import hmac
import json
import os
import secrets
import socket
import socketserver
import threading
import time

from . import paths

ACTIONS = ("previous", "play-pause", "next", "mute", "volume-down", "volume-up", "quit")


class ControlServer:
    def __init__(self, callback, engine_pid=None):
        self.engine_pid = engine_pid
        self.token = secrets.token_hex(32)
        owner = self

        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                self.connection.settimeout(1)
                accepted = False
                try:
                    data = json.loads(self.rfile.readline(4097))
                    action = data.get("action")
                    token = data.get("token")
                    if (
                        isinstance(token, str)
                        and hmac.compare_digest(token, owner.token)
                        and action in (*ACTIONS, "status")
                    ):
                        if action != "status":
                            callback(action)
                        accepted = True
                except (OSError, ValueError, AttributeError, TypeError):
                    pass
                try:
                    self.wfile.write(
                        json.dumps(
                            {"ok": accepted, "pid": os.getpid(), "engine_pid": owner.engine_pid}
                        ).encode()
                        + b"\n"
                    )
                except OSError:
                    pass

        class Server(socketserver.ThreadingTCPServer):
            daemon_threads = True

        self.server = Server(("127.0.0.1", 0), Handler)
        paths.prepare()
        self.metadata = paths.DATA / "control.json"
        from .managed import prefix

        install_prefix = prefix()
        paths.private_json(
            self.metadata,
            {
                "port": self.server.server_address[1],
                "pid": os.getpid(),
                "token": self.token,
                "actions": list(ACTIONS),
                "managed_prefix": str(install_prefix) if install_prefix else None,
                "engine_pid": engine_pid,
            },
        )
        self.thread = threading.Thread(
            target=lambda: self.server.serve_forever(poll_interval=0.1),
            daemon=True,
            name="tspotify-desktop-controls",
        )
        self.thread.start()
        self.shortcuts_active = False
        self.shortcut_error = ""
        from . import shortcuts

        if shortcuts.enabled():
            try:
                self.shortcuts_active = shortcuts.set_active(True)
            except (RuntimeError, OSError) as error:
                self.shortcut_error = str(error)

    def close(self):
        if self.shortcuts_active:
            from . import shortcuts

            try:
                shortcuts.set_active(False)
            except (OSError, RuntimeError):
                pass
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        try:
            data = json.loads(self.metadata.read_text(encoding="utf-8"))
            if data.get("token") == self.token:
                self.metadata.unlink(missing_ok=True)
        except (OSError, ValueError):
            pass


def send(action):
    if action not in (*ACTIONS, "status"):
        raise ValueError("Неизвестная команда управления")
    try:
        data = json.loads((paths.DATA / "control.json").read_text(encoding="utf-8"))
        port = data["port"]
        if type(port) is not int or not 1024 <= port <= 65535:
            raise ValueError("port")
        with socket.create_connection(("127.0.0.1", port), timeout=2) as connection:
            connection.sendall(json.dumps({"action": action, "token": data["token"]}).encode() + b"\n")
            result = json.loads(connection.makefile("rb").readline(4097))
        if not result.get("ok"):
            raise ValueError("rejected")
        return result
    except (OSError, ValueError, KeyError, TypeError):
        raise RuntimeError("tspotify не запущен или ещё не готов к управлению") from None


def process_alive(pid):
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        if os.name == "posix" and os.path.exists(f"/proc/{pid}/stat"):
            state = open(f"/proc/{pid}/stat", encoding="utf-8").read().rsplit(")", 1)[1].split()[0]
            if state == "Z":
                return False
        os.kill(pid, 0)
        return True
    except (OSError, ValueError):
        return False


def stop_client(timeout=15):
    from .managed import prefix

    try:
        data = json.loads((paths.DATA / "control.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"stopped": True, "running": False}
    expected = prefix()
    if expected and data.get("managed_prefix") != str(expected):
        return {"stopped": True, "running": False, "reason": "different_installation"}
    pid, engine = data.get("pid"), data.get("engine_pid")
    if not process_alive(pid):
        return {"stopped": True, "running": False}
    send("quit")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not process_alive(pid) and not process_alive(engine):
            return {"stopped": True, "pid": pid, "engine_pid": engine}
        time.sleep(0.05)
    raise RuntimeError("Штатный выход ещё не завершён; обновление не выполняйте")
