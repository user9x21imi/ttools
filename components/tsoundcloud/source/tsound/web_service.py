"""SoundCloud web-session integration for accounts using the browser sign-in."""

from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import re
import time
from urllib.parse import parse_qsl, quote, urlencode, urlsplit
from urllib.request import Request, urlopen

from . import state
from .service import Entry, NetworkError, ServiceError, SoundCloud, USER_AGENT, request, timed_comments, unique
from .web_session import browser_profile, default_profile, open_default_browser, session_token, start_browser


PROFILE_FILE = "web-login.json"
CLIENT_CACHE = "web-client.json"
WEB_API = "https://api-v2.soundcloud.com"
WEB_HOST = "api-v2.soundcloud.com"
WEB_PAGE = "https://soundcloud.com/"
CLIENT = re.compile(rb'\bclient_id\s*[:=]\s*["\']([A-Za-z0-9]{32})["\']')


def public_asset(url, limit):
    with urlopen(Request(url, headers={"User-Agent": USER_AGENT}), timeout=6) as response:
        return response.read(limit)


def web_client_id():
    page = public_asset(WEB_PAGE, 2_000_000)
    assets = re.findall(rb'<script\b[^>]*\bsrc=["\'](https://a-v2\.sndcdn\.com/[^"\']+\.js)["\']', page)
    for asset in reversed(dict.fromkeys(assets)):
        try:
            data = public_asset(asset.decode(), 6_000_000)
        except OSError:
            continue
        if matched := CLIENT.search(data):
            return matched[1].decode()
    raise ServiceError("Не удалось подключиться к веб-версии SoundCloud.")


def numeric(key):
    return str(key).rsplit(":", 1)[-1]


class WebSoundCloud(SoundCloud):
    def __init__(self, source):
        self.lock = source.lock
        self.command, self.profile = browser_profile()
        remembered = state.read(PROFILE_FILE)
        remembered = remembered.get("profile") if isinstance(remembered, dict) else None
        self.remembered_profile = Path(remembered) if isinstance(remembered, str) and remembered else None
        if self.remembered_profile and not self.remembered_profile.is_absolute():
            self.remembered_profile = None
        self.session = session_token(self.remembered_profile or self.profile)
        cached_id = state.read(CLIENT_CACHE)
        self.web_id = None
        if isinstance(cached_id, dict) and isinstance(cached_id.get("expires"), (int, float)):
            value = cached_id.get("id")
            if cached_id["expires"] > time.time() and isinstance(value, str) and re.fullmatch("[A-Za-z0-9]{32}", value):
                self.web_id = value
        self.track_metadata = OrderedDict()
        self.account = None
        self.browser = None

    @property
    def signed_in(self):
        return bool(self.session)

    def verify_session(self, token, profile):
        previous = self.session
        with self.lock:
            self.session = token
        try:
            account = self.get("/me")
            if not isinstance(account, dict) or not account.get("id"):
                raise ServiceError("SoundCloud не подтвердил вход в аккаунт.")
        except (OSError, ValueError, ServiceError):
            with self.lock:
                self.session = previous
            raise
        self.account = account
        if self.remembered_profile != profile:
            state.write(PROFILE_FILE, {"profile": str(profile)})
            self.remembered_profile = profile

    def default_browser_login(self, cancelled, launched=lambda opened: None):
        profile = default_profile()
        if not profile:
            raise ServiceError("Профиль Zen или Firefox не найден. Откройте SoundCloud в этом браузере "
                               "и проверьте, что он выбран по умолчанию.")
        previous = session_token(profile)
        if cancelled.is_set():
            return
        if previous:
            try:
                self.verify_session(previous, profile)
                return
            except ServiceError as error:
                if not str(error).endswith(("401", "403")):
                    raise
        opened = open_default_browser()
        if not cancelled.is_set():
            launched(opened)
        self.wait_for_profile(profile, cancelled, previous)

    def wait_for_profile(self, profile, cancelled, previous, browser=None):
        deadline = time.monotonic() + 180
        while not cancelled.wait(.3) and time.monotonic() < deadline:
            token = session_token(profile)
            if token and token != previous:
                self.verify_session(token, profile)
                return
            if browser and browser.poll() not in (None, 0):
                raise ServiceError("Не удалось запустить отдельное окно браузера.")
        if not cancelled.is_set():
            raise ServiceError("Вход не завершён. Нажмите Enter, чтобы попробовать снова.")

    def browser_login(self, cancelled, redirect=None):
        if not self.command:
            raise ServiceError("Для входа установите Firefox или Zen Browser.")
        previous = session_token(self.profile)
        if previous:
            try:
                self.verify_session(previous, self.profile)
                return
            except ServiceError as error:
                if not str(error).endswith(("401", "403")):
                    raise
        if not self.browser or self.browser.poll() is not None:
            self.browser = start_browser(self.command, self.profile)
        self.wait_for_profile(self.profile, cancelled, previous, self.browser)

    def get(self, path, **params):
        return self.api_request(path, **params)

    def remember_tracks(self, result):
        if isinstance(result, dict):
            if (result.get("media") or {}).get("transcodings") and (key := result.get("id") or result.get("urn")):
                key = numeric(key)
                with self.lock:
                    self.track_metadata[key] = (time.monotonic(), result)
                    self.track_metadata.move_to_end(key)
                    while len(self.track_metadata) > 150:
                        self.track_metadata.popitem(last=False)
            else:
                for name in ("collection", "tracks", "track", "origin"):
                    if name in result:
                        self.remember_tracks(result[name])
        elif isinstance(result, list):
            for item in result:
                self.remember_tracks(item)

    def api_request(self, path, method=None, timeout=None, **params):
        url = WEB_API + path if path.startswith("/") else path
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.netloc != WEB_HOST:
            raise ServiceError("Некорректный адрес SoundCloud.")
        with self.lock:
            if not self.session:
                raise ServiceError("Войдите через браузер по F5.")
            if self.web_id is None:
                self.web_id = web_client_id()
                state.write(CLIENT_CACHE, {"id": self.web_id, "expires": time.time() + 12 * 3600})
            client_id = self.web_id
            token = self.session
        query = dict(parse_qsl(parsed.query))
        query.update(params)
        query["client_id"] = client_id
        target = parsed._replace(query=urlencode(query)).geturl()
        options = {"timeout": timeout} if timeout else {}
        result = request(target, token=token, method=method, **options)
        self.remember_tracks(result)
        return result

    def account_id(self):
        if self.account is None:
            self.account = self.get("/me")
        return quote(numeric(self.account["id"]), safe="")

    def favorites(self, first_page=None):
        def entries(items):
            return unique([Entry.from_api(row.get("track") or row, "track")
                           for row in items if row.get("track") or row.get("kind") == "track"])

        user = self.account_id()
        preview = (lambda rows: first_page(entries(rows))) if first_page else None
        try:
            rows = self.pages(f"/users/{user}/track_likes", maximum=None,
                              first_page=preview, page_size=40)
        except ServiceError as error:
            if str(error) != "SoundCloud: HTTP 404":
                raise
            rows = self.pages(f"/users/{user}/likes", maximum=None,
                              first_page=preview, page_size=40)
        return entries(rows)

    def section(self, section):
        if section == "artists":
            return super().section(section)
        if section == "recent":
            rows = self.pages("/me/play-history/tracks", maximum=30)[:25]
            return unique([Entry.from_api(row.get("track") or row, "track") for row in rows])
        if section == "mixes":
            rows = self.pages("/me/likes/system-playlists")
            return unique([Entry.from_api(row.get("system_playlist") or row, "station") for row in rows])
        if section == "likes":
            return self.favorites()
        return self.browse_section(section, lambda page: None)

    def browse_section(self, section, publish):
        def fetch(path, fields=(), kind=None, maximum=1000, page_size=30):
            def entries(rows):
                return unique([Entry.from_api(next((row[name] for name in fields if row.get(name)), row), kind)
                               for row in rows if isinstance(row, dict)])

            def progress(rows):
                if items := entries(rows):
                    publish(items)

            return entries(self.pages(path, maximum=maximum, page_size=page_size, progress=progress))

        if section == "feed":
            return fetch("/stream", ("track", "playlist", "origin"))
        user = self.account_id()
        if section == "uploads":
            return fetch(f"/users/{user}/tracks", kind="track")
        if section != "playlists":
            raise KeyError(section)

        def liked():
            url = f"/users/{user}"
            try:
                return fetch(f"{url}/playlist_likes", ("playlist",), "playlist")
            except ServiceError as error:
                if str(error) != "SoundCloud: HTTP 404":
                    raise
                def playlists(rows):
                    return unique([Entry.from_api(row.get("playlist"), "playlist")
                                   for row in rows if isinstance(row, dict)])

                return playlists(self.pages(f"{url}/likes", page_size=40,
                                            progress=lambda rows: publish(playlists(rows))))

        with ThreadPoolExecutor(max_workers=2) as executor:
            pending = [executor.submit(fetch, f"/users/{user}/playlists", (), "playlist"),
                       executor.submit(liked)]
            results = []
            errors = []
            for future in as_completed(pending):
                try:
                    results.extend(future.result())
                except ServiceError as error:
                    errors.append(error)
        if errors:
            raise errors[0]
        return unique(results)

    def search(self, query):
        tasks = (("tracks", "track"), ("playlists", "playlist"), ("users", "user"))
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = [(kind, pool.submit(self.pages, f"/search/{route}", maximum=30, q=query))
                       for route, kind in tasks]
            groups = [[entry for row in result.result() if (entry := Entry.from_api(row, kind))]
                      for kind, result in futures]
        return [group[index] for index in range(max(map(len, groups), default=0))
                for group in groups if index < len(group)]

    def collection(self, item):
        key = quote(numeric(item.key), safe="")
        if item.kind == "user":
            rows = self.pages(f"/users/{key}/tracks")
        elif item.kind == "station":
            rows = self.get(f"/system-playlists/{key}").get("tracks", [])
        else:
            rows = self.get(f"/playlists/{key}").get("tracks", [])
        missing = [numeric(row.get("id") or row.get("urn", "")) for row in rows if not row.get("title")]
        complete = {}
        for offset in range(0, len(missing), 50):
            ids = ",".join(missing[offset:offset + 50])
            complete.update({numeric(row["id"]): row for row in self.get("/tracks", ids=ids)})
        return [entry for row in rows
                if (entry := Entry.from_api(complete.get(numeric(row.get("id") or row.get("urn", "")), row), "track"))]

    def comments(self, track):
        key = quote(numeric(track.key), safe="")
        path = f"/tracks/{key}/comments"
        page = self.get(path, limit=20, offset=0, threaded=1, sort="track-timestamp")
        rows = []
        visited = set()
        while isinstance(page, dict):
            rows.extend(page.get("collection") or [])
            following = page.get("next_href")
            if not following or following in visited or len(rows) >= 2000:
                break
            visited.add(following)
            try:
                page = self.get(following)
            except (OSError, ValueError, ServiceError):
                if rows:
                    break
                raise
        if isinstance(page, list):
            rows.extend(page)
        return timed_comments(rows[:2000])

    def like(self, track, value):
        key = quote(numeric(track.key), safe="")
        user = self.account_id()
        self.api_request(f"/users/{user}/track_likes/{key}", method="PUT" if value else "DELETE")

    def stream(self, track):
        key = numeric(track.key)
        path = f"/tracks/{quote(key, safe='')}"
        with self.lock:
            cached = self.track_metadata.get(key)
        if cached and time.monotonic() - cached[0] < 120:
            try:
                return self.resolve_transcoding(cached[1], track)
            except ServiceError:
                pass
        try:
            data = self.api_request(path, timeout=3.0)
        except NetworkError:
            data = self.api_request(path, timeout=4.5)
        return self.resolve_transcoding(data, track)

    def resolve_transcoding(self, data, track):
        if data.get("policy") == "BLOCK" or track.access == "blocked":
            raise ServiceError("Трек недоступен для воспроизведения.")
        formats = (data.get("media") or {}).get("transcodings") or []
        formats = sorted(formats, key=lambda item: (
            bool(item.get("snipped")), (item.get("format") or {}).get("protocol") != "progressive",
            item.get("quality") != "hq"))
        network_error = None
        for item in formats:
            target = urlsplit(item.get("url") or "")
            if target.scheme != "https" or target.netloc != WEB_HOST:
                continue
            if (item.get("format") or {}).get("protocol") not in ("hls", "progressive"):
                continue
            params = {}
            if data.get("track_authorization"):
                params["track_authorization"] = data["track_authorization"]
            try:
                result = self.api_request(target.geturl(), timeout=3.0, **params)
            except NetworkError as error:
                network_error = error
                continue
            except ServiceError as error:
                if str(error).endswith(("403", "404")):
                    continue
                raise
            if isinstance(result.get("url"), str) and result["url"].startswith("https://"):
                return result["url"], bool(item.get("snipped"))
        if network_error:
            raise network_error
        raise ServiceError("SoundCloud не вернул доступный аудиопоток.")
