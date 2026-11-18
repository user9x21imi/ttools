"""PKCE browser authorization. No password collection or desktop-token scraping."""

import base64
import hashlib
import secrets
import threading
import time
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx

from . import paths

CLIENT_ID = "d420a117a32841c2b3474932e49fb54b"
REDIRECT = "http://127.0.0.1:8989/ncspot_login"
SCOPES = " ".join(
    [
        "user-read-playback-state",
        "user-modify-playback-state",
        "user-read-currently-playing",
        "user-library-read",
        "user-library-modify",
        "playlist-read-private",
        "playlist-read-collaborative",
        "user-follow-read",
        "user-top-read",
        "user-read-recently-played",
        "streaming",
    ]
)


class LoginRequired(RuntimeError):
    pass


def parse_callback(url, expected_state):
    parsed = urlsplit(url)
    if parsed.path != "/ncspot_login":
        raise ValueError("Неизвестный адрес возврата")
    query = parse_qs(parsed.query)
    state = query.get("state", [""])[0]
    if not secrets.compare_digest(state, expected_state):
        raise ValueError("Код входа относится к другой сессии. Повторите вход.")
    if "error" in query:
        raise ValueError("Доступ к Spotify не подтверждён")
    code = query.get("code", [""])[0]
    if not code:
        raise ValueError("В адресе отсутствует код входа")
    return code


def save_token(data, previous=None):
    data = dict(data)
    data.setdefault("scope", (previous or {}).get("scope", SCOPES))
    if previous and not data.get("refresh_token"):
        data["refresh_token"] = previous.get("refresh_token")
    data["expires_at"] = datetime.fromtimestamp(
        time.time() + int(data.get("expires_in", 3600)), timezone.utc
    ).isoformat()
    paths.private_json(paths.TOKEN_FILE, data)
    return data


def read_token():
    import json

    try:
        return json.loads(paths.TOKEN_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise LoginRequired("Нужен вход: tspotify login") from None


_refresh_lock = threading.Lock()


def access_token():
    with _refresh_lock:
        data = read_token()
        try:
            expires = datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00")).timestamp()
        except (KeyError, ValueError):
            expires = 0
        if expires > time.time() + 90:
            return data["access_token"]
        if not data.get("refresh_token"):
            raise LoginRequired("Сессия истекла: tspotify login")
        response = httpx.post(
            "https://accounts.spotify.com/api/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": data["refresh_token"],
                "client_id": CLIENT_ID,
            },
            timeout=15,
        )
        if response.status_code != 200:
            raise LoginRequired("Spotify запросил повторный вход: tspotify login")
        return save_token(response.json(), data)["access_token"]


def login(qr=False, timeout=180):
    paths.prepare()
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    state = secrets.token_urlsafe(24)
    url = "https://accounts.spotify.com/authorize?" + urlencode(
        {
            "client_id": CLIENT_ID,
            "response_type": "code",
            "redirect_uri": REDIRECT,
            "scope": SCOPES,
            "code_challenge_method": "S256",
            "code_challenge": challenge,
            "state": state,
        }
    )
    done = threading.Event()
    result = {}

    class Callback(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            try:
                code = parse_callback(self.path, state)
            except ValueError:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"Invalid callback. Please return to the terminal and retry.")
                return
            result["code"] = code
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                b"<body style='background:#121519;color:#56d98a;font:18px monospace;padding:8vh'>"
                b"+-- tspotify --+<br><br>Signed in. Return to your terminal.</body>"
            )
            done.set()

    try:
        server = HTTPServer(("127.0.0.1", 8989), Callback)
    except OSError:
        raise RuntimeError("Порт входа 8989 занят. Закройте другой вход Spotify и повторите.") from None
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        print("\n+-- tspotify / Spotify login ----------------------------------+")
        print("Один раз подтвердите доступ к библиотеке. Пароль вводится только у Spotify.")
        if qr:
            import qrcode

            image = qrcode.QRCode(border=2)
            image.add_data(url)
            image.make(fit=True)
            image.print_ascii(invert=True)
            print("На телефоне localhost не откроется — это нормально.")
            print("После подтверждения скопируйте полный адрес возврата с телефона сюда.")
            pasted = input("Адрес возврата (или Enter, если вход выполнен на компьютере): ").strip()
            if pasted:
                result["code"] = parse_callback(pasted, state)
                done.set()
        else:
            print("Открываю браузер. Если вкладка не появилась, откройте ссылку:")
            print(url)
            webbrowser.open(url, new=2)
        if not done.wait(timeout):
            raise RuntimeError("Время входа истекло. Повторите: tspotify login")
        response = httpx.post(
            "https://accounts.spotify.com/api/token",
            data={
                "grant_type": "authorization_code",
                "code": result["code"],
                "redirect_uri": REDIRECT,
                "client_id": CLIENT_ID,
                "code_verifier": verifier,
            },
            timeout=20,
        )
        if response.status_code != 200:
            raise RuntimeError("Spotify отклонил код входа. Повторите вход.")
        save_token(response.json())
        print("Вход выполнен. Учётные данные сохранены только на этом компьютере.\n")
    finally:
        server.shutdown()
        server.server_close()
