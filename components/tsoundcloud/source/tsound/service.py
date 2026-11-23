import base64
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import os
import secrets
import threading
import time
import webbrowser
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen

from . import state


API = "https://api.soundcloud.com"
AUTH = "https://secure.soundcloud.com"
USER_AGENT = "tsound/0.1"


class ServiceError(RuntimeError):
    pass


class NetworkError(ServiceError):
    pass


@dataclass(frozen=True)
class Entry:
    kind: str
    key: str
    title: str
    artist: str = ""
    artist_key: str = ""
    duration: float = 0
    art: str = ""
    release: str = ""
    waveform: str = ""
    access: str = ""
    permalink: str = ""

    @classmethod
    def from_api(cls, item, kind=None):
        if not isinstance(item, dict):
            return None
        kind = kind or item.get("kind") or "track"
        if kind == "playlist" and item.get("is_album"):
            kind = "album"
        user = item.get("user") or {}
        key = item.get("urn") or item.get("id")
        title = item.get("title") or item.get("username")
        if not key or not title:
            return None
        release = (item.get("publisher_metadata") or {}).get("album_title") or ""
        return cls(kind, str(key), title, user.get("username", ""),
                   str(user.get("urn") or user.get("id") or ""),
                   (item.get("duration") or 0) / 1000,
                   item.get("artwork_url") or item.get("avatar_url") or user.get("avatar_url") or "",
                   release, item.get("waveform_url") or "", item.get("access") or "",
                   item.get("permalink_url") or "")


@dataclass(frozen=True, order=True)
class Comment:
    seconds: float
    author: str
    body: str


def unique(entries):
    result = {}
    for item in entries:
        if item:
            result.setdefault((item.kind, item.key), item)
    return list(result.values())


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def request(url, fields=None, token=None, method=None, redirect=False, basic=None, timeout=8):
    headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
    if token:
        headers["Authorization"] = "OAuth " + token
    elif basic:
        headers["Authorization"] = "Basic " + base64.b64encode(basic.encode()).decode()
    data = urlencode(fields).encode() if fields is not None else None
    req = Request(url, data, headers, method=method)
    try:
        with build_opener(NoRedirect()).open(req, timeout=timeout) as response:
            data = response.read(8_000_001)
            if len(data) > 8_000_000:
                raise ServiceError("Ответ SoundCloud слишком большой")
            return json.loads(data) if data else {}
    except HTTPError as error:
        if redirect and error.code in (302, 303, 307, 308):
            return error.headers.get("Location", "")
        if error.code == 429:
            raise ServiceError("SoundCloud ограничил частоту запросов") from None
        raise ServiceError(f"SoundCloud: HTTP {error.code}") from None
    except (TimeoutError, URLError, ConnectionError) as error:
        reason = error.reason if isinstance(error, URLError) else error
        if isinstance(reason, TimeoutError):
            raise NetworkError("SoundCloud не ответил вовремя") from None
        raise NetworkError("Нет ответа от SoundCloud. Проверьте подключение") from None


class SoundCloud:
    sections = {
        "recent": [("/me/recently-played/tracks", "track")],
        "mixes": [("/me/likes/system-playlists", "station")],
        "likes": [("/me/likes/tracks", "track")],
        "uploads": [("/me/tracks", "track")],
        "playlists": [("/me/playlists", "playlist"), ("/me/likes/playlists", "playlist")],
    }

    def __init__(self):
        self.credentials = state.read("credentials.json")
        self.token = state.read("token.json")
        self.lock = threading.Lock()
        self.client_id = os.getenv("SOUNDCLOUD_CLIENT_ID") or self.credentials.get("client_id")
        self.secret = os.getenv("SOUNDCLOUD_CLIENT_SECRET") or self.credentials.get("client_secret")
        self.external_token = os.getenv("SOUNDCLOUD_ACCESS_TOKEN")

    def exchange(self, **fields):
        if not self.client_id or not self.secret:
            raise ServiceError("Укажите client ID и secret зарегистрированного приложения")
        if fields["grant_type"] == "client_credentials":
            token = request(AUTH + "/oauth/token", fields, basic=f"{self.client_id}:{self.secret}")
        else:
            token = request(AUTH + "/oauth/token", {
                "client_id": self.client_id, "client_secret": self.secret, **fields,
            })
        token["expires_at"] = time.time() + float(token.get("expires_in", 3600))
        self.token = token
        state.write("token.json", token)
        return token["access_token"]

    @property
    def signed_in(self):
        return bool(self.external_token or self.token.get("refresh_token"))

    def browser_login(self, cancelled, redirect=None):
        redirect = (redirect or os.getenv("SOUNDCLOUD_REDIRECT_URI")
                    or self.credentials.get("redirect_uri", ""))
        if not self.client_id or not self.secret or not redirect:
            raise ServiceError("Вход недоступен: для tsoundcloud ещё не настроен доступ к SoundCloud.")
        local = urlsplit(redirect)
        if (local.scheme != "http" or local.hostname not in ("127.0.0.1", "localhost")
                or not local.port or local.username or local.password or local.query or local.fragment):
            raise ServiceError("Для входа требуется настроить локальный адрес возврата приложения.")

        verifier = secrets.token_urlsafe(48)
        nonce = secrets.token_urlsafe(24)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
        authorize_url = AUTH + "/authorize?" + urlencode({
            "client_id": self.client_id, "redirect_uri": redirect, "response_type": "code",
            "code_challenge": challenge, "code_challenge_method": "S256", "state": nonce,
        })
        callback = []
        arrived = threading.Event()

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                target = urlsplit(self.path)
                fields = parse_qs(target.query)
                valid = (self.headers.get("Host") == local.netloc and not target.netloc
                         and target.path == (local.path or "/") and fields.get("state") == [nonce]
                         and bool(fields.get("code") or fields.get("error")))
                self.send_response(200 if valid else 404)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                if valid and not arrived.is_set() and not cancelled.is_set():
                    callback.append(fields)
                    arrived.set()
                message = "Вернитесь в tsoundcloud." if valid else "Страница не найдена."
                self.wfile.write(message.encode())

        try:
            server = ThreadingHTTPServer(("127.0.0.1", local.port), Handler)
        except OSError:
            raise ServiceError("Не удалось открыть локальный адрес входа. Проверьте, открыт ли второй клиент.") from None

        with server:
            listener = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .1}, daemon=True)
            listener.start()
            try:
                if cancelled.is_set():
                    return
                if not webbrowser.open(authorize_url):
                    raise ServiceError("Не удалось открыть браузер.")
                deadline = time.monotonic() + 180
                while not cancelled.is_set() and not arrived.wait(.15):
                    if time.monotonic() >= deadline:
                        raise ServiceError("Время входа истекло. Попробуйте ещё раз.")
            finally:
                server.shutdown()
                listener.join()

        if cancelled.is_set():
            return
        codes = callback[0].get("code", [])
        if len(codes) != 1 or callback[0].get("error"):
            raise ServiceError("Вход отменён в браузере.")
        with self.lock:
            if not cancelled.is_set():
                self.exchange(grant_type="authorization_code", code=codes[0],
                              redirect_uri=redirect, code_verifier=verifier)

    def access_token(self):
        with self.lock:
            if self.external_token:
                return self.external_token
            if self.token.get("expires_at", 0) > time.time() + 30:
                return self.token["access_token"]
            if self.token.get("refresh_token"):
                return self.exchange(grant_type="refresh_token", refresh_token=self.token["refresh_token"])
            return self.exchange(grant_type="client_credentials")

    def get(self, path, **params):
        url = API + path if path.startswith("/") else path
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.netloc != "api.soundcloud.com":
            raise ServiceError("Некорректный адрес API")
        if params:
            url += ("&" if parsed.query else "?") + urlencode(params)
        return request(url, token=self.access_token())

    def pages(self, path, maximum=1000, with_limit=True, first_page=None, page_size=100, progress=None, **params):
        if maximum == 25:
            result = self.get(path)
        else:
            if with_limit:
                params["limit"] = min(page_size, maximum) if maximum is not None else page_size
            result = self.get(path, linked_partitioning="true", **params)
        if first_page:
            first_page(result.get("collection", []) if isinstance(result, dict) else result)
        items = []
        visited = set()
        while isinstance(result, dict):
            remaining = None if maximum is None else maximum - len(items)
            page = (result.get("collection") or result.get("tracks") or [])[:remaining]
            items.extend(page)
            if progress and page:
                progress(page)
            following = result.get("next_href")
            if not following or following in visited or (maximum is not None and len(items) >= maximum):
                return items[:maximum]
            visited.add(following)
            result = self.get(following)
        if progress and result:
            remaining = None if maximum is None else maximum - len(items)
            progress(result[:remaining])
        return (items + result)[:maximum]

    def favorites(self, first_page=None):
        def entries(items):
            return unique([Entry.from_api(item, "track") for item in items])

        preview = (lambda rows: first_page(entries(rows))) if first_page else None
        return entries(self.pages("/me/likes/tracks", maximum=None, first_page=preview, page_size=40))

    def section(self, section):
        if section == "artists":
            return unique([
                Entry("user", track.artist_key, track.artist)
                for track in self.section("recent") if track.artist_key
            ])
        if section == "feed":
            activities = self.pages("/me/feed/tracks")
            return unique([Entry.from_api(activity.get("origin") or activity.get("track") or activity)
                           for activity in activities])
        entries = []
        limit = {"recent": 25, "likes": None}.get(section, 1000)
        for path, kind in self.sections[section]:
            entries.extend(Entry.from_api(item, kind) for item in self.pages(path, maximum=limit))
        return unique(entries)

    def search(self, query):
        paths = [("tracks", "track"), ("playlists", "playlist"), ("users", "user")]
        with ThreadPoolExecutor(max_workers=3) as executor:
            pending = [(kind, executor.submit(self.pages, "/" + path, maximum=30, q=query))
                       for path, kind in paths]
            results = []
            errors = []
            for kind, future in pending:
                try:
                    results.append([entry for item in future.result() if (entry := Entry.from_api(item, kind))])
                except Exception as error:
                    errors.append(error)
            if not results and errors:
                raise errors[0]
        # Interleave so artists and collections are visible near the top.
        return [items[index] for index in range(max(map(len, results), default=0))
                for items in results if index < len(items)]

    def collection(self, item):
        key = quote(item.key, safe="")
        if item.kind == "user":
            results = self.pages(f"/users/{key}/tracks")
        elif item.kind == "station":
            data = self.get(f"/system-playlists/{key}")
            results = data.get("tracks", [])
        else:
            results = self.pages(f"/playlists/{key}/tracks", with_limit=False)
        return [entry for raw in results if (entry := Entry.from_api(raw, "track"))]

    def comments(self, track):
        rows = self.pages(f"/tracks/{quote(track.key, safe='')}/comments", maximum=2000)
        return timed_comments(rows)

    def like(self, track, value):
        request(API + f"/likes/tracks/{quote(track.key, safe='')}", token=self.access_token(),
                method="POST" if value else "DELETE")

    def stream(self, track):
        key = quote(track.key, safe="")
        if track.access == "blocked":
            raise ServiceError("Трек недоступен для воспроизведения")
        if track.access == "preview":
            url = request(API + f"/tracks/{key}/preview", token=self.access_token(), redirect=True)
        else:
            streams = self.get(f"/tracks/{key}/streams")
            formats = ("hls_aac_160_url", "hls_aac_96_url", "hls_mp3_128_url",
                       "hls_opus_64_url", "http_mp3_128_url")
            url = next((streams[name] for name in formats
                        if isinstance(streams.get(name), str)
                        and streams[name].startswith("https://")), "")
        if not isinstance(url, str) or urlsplit(url).scheme != "https":
            raise ServiceError("SoundCloud не вернул доступный аудиопоток")
        if urlsplit(url).netloc == "api.soundcloud.com":
            url = request(url, token=self.access_token(), redirect=True)
        if not isinstance(url, str) or urlsplit(url).scheme != "https":
            raise ServiceError("SoundCloud не вернул адрес воспроизведения")
        return url, track.access == "preview"


def timed_comments(rows):
    result = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        timestamp = item.get("timestamp")
        try:
            if timestamp is not None and item.get("body"):
                result.append(Comment(float(timestamp) / 1000,
                                      (item.get("user") or {}).get("username", ""), item["body"]))
        except (TypeError, ValueError):
            continue
    return sorted(result)


def cdn_bytes(url, limit, hosts):
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not any(parsed.hostname == host or
                                           (parsed.hostname or "").endswith("." + host) for host in hosts):
        return b""
    with build_opener(NoRedirect()).open(Request(url, headers={"User-Agent": USER_AGENT}), timeout=6) as response:
        data = response.read(limit + 1)
    return data if len(data) <= limit else b""


def waveform(track):
    if not track.waveform:
        return []
    data = cdn_bytes(track.waveform, 512_000, ("sndcdn.com", "soundcloud.com"))
    if not data:
        return []
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        from .visual import png_waveform

        return png_waveform(data)
    try:
        samples = json.loads(data).get("samples", [])
        samples = [max(0., float(value)) if math.isfinite(float(value)) else 0.
                   for value in samples[:16000]]
    except (AttributeError, TypeError, ValueError, UnicodeError):
        return []
    peak = max(samples, default=0)
    return [value / peak for value in samples] if peak else []
