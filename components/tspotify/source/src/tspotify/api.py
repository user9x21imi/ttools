"""Pooled Spotify requests, explicit failures, cached libraries and verified playback."""

import json
import concurrent.futures
from collections import OrderedDict
import math
import threading
import time
from urllib.parse import quote

import httpx

from . import auth, paths, session


class SpotifyError(RuntimeError):
    def __init__(self, message, status=None):
        self.status = status
        super().__init__(message)


class RateLimited(SpotifyError):
    def __init__(self, seconds):
        self.seconds = seconds
        super().__init__(f"Spotify ограничил запросы. Повторите через {seconds} сек.")


def track_from_entry(entry):
    if not isinstance(entry, dict):
        return None
    nested = entry.get("track") or entry.get("item")
    track = nested if isinstance(nested, dict) else entry
    return track if track.get("id") and not track.get("is_local", False) else None


class Spotify:
    def __init__(self):
        self.http = httpx.Client(
            http2=True,
            timeout=httpx.Timeout(12, connect=8),
            limits=httpx.Limits(max_connections=8, max_keepalive_connections=8),
        )
        self.rate_until = 0.0
        self.backend = None
        self.device_id = None
        self.external = False
        self.backend_factory = None
        self.resume_data = session.load()
        self.session_muted = False
        self._runtime_volume = None
        self._volume_until = 0.0
        self._volume_lock = threading.RLock()
        self._volume_revision = 0
        self._restore_gate = time.monotonic()
        self._start_cancel = threading.Event()
        self.idle = True
        self.last_playback = {
            "item": self.resume_data.get("track"),
            "is_playing": False,
            "progress_ms": self.resume_data.get("position_ms", 0),
            "device": {"name": "tspotify", "volume_percent": self.resume_data["volume"]},
        }
        self._remote_future = None
        self._remote_started = 0.0
        self._remote_pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self._metadata_pool = concurrent.futures.ThreadPoolExecutor(max_workers=2)
        self._metadata_jobs = {}
        self._metadata_retry = {}
        self._tracks = OrderedDict()
        self._tracks_lock = threading.RLock()
        self._last_remote_poll = 0.0
        self._lock = threading.Lock()
        self.on_status = lambda message: None
        self.on_volume_retry = lambda target, seconds, applied: None

    def close(self):
        self._remote_pool.shutdown(wait=False, cancel_futures=True)
        self._metadata_pool.shutdown(wait=False, cancel_futures=True)
        self.http.close()

    def remember_tracks(self, value):
        if isinstance(value, list):
            for entry in value:
                self.remember_tracks(entry)
        elif isinstance(value, dict):
            if value.get("id") and (
                value.get("type") == "track"
                or "duration_ms" in value
                or isinstance(value.get("duration"), dict)
            ):
                with self._tracks_lock:
                    self._tracks[value["id"]] = value
                    self._tracks.move_to_end(value["id"])
                    while len(self._tracks) > 1024:
                        self._tracks.popitem(last=False)
            for key in ("items", "tracks", "track", "item"):
                if key in value:
                    self.remember_tracks(value[key])

    def track_metadata(self, identity):
        with self._tracks_lock:
            known = self._tracks.get(identity)
        if known:
            return known
        for key, job in list(self._metadata_jobs.items()):
            if job.done():
                try:
                    result = job.result()
                    if result:
                        self.remember_tracks(result)
                except (SpotifyError, httpx.HTTPError, RuntimeError) as error:
                    self._metadata_retry[key] = time.monotonic() + 5
                    self.on_status("Данные трека: " + str(error)[:120])
                self._metadata_jobs.pop(key, None)
        with self._tracks_lock:
            known = self._tracks.get(identity)
        if known:
            return known
        if (
            identity not in self._metadata_jobs
            and len(self._metadata_jobs) < 2
            and time.monotonic() >= self._metadata_retry.get(identity, 0)
        ):
            self._metadata_jobs[identity] = self._metadata_pool.submit(
                self.request, "GET", "tracks/" + quote(identity, safe="")
            )
        return {"id": identity, "name": "Загружаются данные трека…", "_metadata_pending": True}

    @property
    def local_controls(self):
        return bool(self.backend and not self.external and getattr(self.backend, "local_enabled", False))

    def activate_output_volume(self):
        if (
            not self.local_controls
            or self.current_volume <= 0
            or getattr(self.backend, "_volume_active", False)
        ):
            return
        with self._volume_lock:
            self.backend.local_control("volume", self.current_volume)
            self.backend.confirmed_volume = self.current_volume
            self.backend._volume_active = True
            if not getattr(self.backend, "_audio_output_ready", False):
                self.backend.unmute_after_user_volume(self.current_volume)
                self.backend._audio_output_ready = True

    @property
    def current_volume(self):
        if self._runtime_volume is not None:
            return self._runtime_volume
        return (
            0 if self.session_muted or getattr(self.backend, "muted", False) else self.resume_data["volume"]
        )

    def save_session(self, playback=None, volume=None, view=None):
        if self.session_muted or getattr(self.backend, "muted", False):
            return
        changes = {}
        if volume is not None:
            changes["volume"] = max(0, min(100, int(volume)))
            if changes["volume"]:
                changes["unmuted_volume"] = changes["volume"]
        if playback and isinstance(playback.get("item"), dict) and playback["item"].get("id"):
            changes["track"] = playback["item"]
            changes["position_ms"] = max(0, int(playback.get("progress_ms") or 0))
        if view is not None:
            changes["view"] = view
        self.resume_data = session.save(**changes)

    def request(self, method, path, body=None, _retry=0):
        remaining = self.rate_until - time.monotonic()
        if remaining > 0:
            raise RateLimited(max(1, math.ceil(remaining)))
        if path.startswith("https://api.spotify.com/v1/"):
            url = path
        elif not path.startswith(("http:", "https:")):
            url = "https://api.spotify.com/v1/" + path.lstrip("/")
        else:
            raise ValueError("Недопустимый адрес API")
        try:
            response = self.http.request(
                method, url, json=body, headers={"Authorization": "Bearer " + auth.access_token()}
            )
        except httpx.TimeoutException:
            raise SpotifyError(
                "Spotify не ответил вовремя. Проверьте соединение; команда не подтверждена."
            ) from None
        except httpx.HTTPError:
            raise SpotifyError("Соединение со Spotify прервано; команда не подтверждена.") from None
        if response.status_code == 429:
            try:
                seconds = min(86400, max(1, math.ceil(float(response.headers.get("Retry-After", "30")))))
            except ValueError:
                seconds = 30
            self.rate_until = max(self.rate_until, time.monotonic() + seconds)
            if method == "GET" and _retry == 0 and seconds <= 3:
                time.sleep(seconds + 0.05)
                return self.request(method, path, body, _retry=1)
            raise RateLimited(seconds)
        if response.status_code in (502, 503, 504) and _retry == 0 and method in ("GET", "PUT"):
            return self.request(method, path, body, _retry=1)
        if response.status_code == 401:
            raise auth.LoginRequired("Spotify запросил повторный вход: tspotify login")
        if response.status_code >= 400:
            try:
                message = response.json().get("error", {}).get("message", "")
            except (ValueError, AttributeError):
                message = ""
            if response.status_code == 403:
                message = message or "Нужен Spotify Premium и разрешение на управление воспроизведением"
            raise SpotifyError(
                f"Spotify {response.status_code}: {message or 'запрос отклонён'}", status=response.status_code
            )
        if response.status_code == 204:
            return None
        # Player commands acknowledge success with an empty or plain-text body.
        # Their result is confirmed separately from playback state/events.
        if method != "GET":
            return None
        try:
            if not response.content.strip():
                raise ValueError("empty response")
            result = response.json()
            self.remember_tracks(result)
            return result
        except ValueError:
            if _retry == 0:
                time.sleep(0.2)
                return self.request(method, path, body, _retry=1)
            endpoint = url.split("?", 1)[0].removeprefix("https://api.spotify.com/v1/")
            raise SpotifyError(
                f"Spotify вернул некорректный ответ ({endpoint}). Повторите действие; команда не подтверждена."
            ) from None

    def devices(self):
        return (self.request("GET", "me/player/devices") or {}).get("devices", [])

    def select_device(self, preference="auto"):
        if preference == "integrated":
            self.external = False
            self.device_id = None
            return None
        devices = self.devices()
        choices = [x for x in devices if not x.get("is_restricted")]
        if preference not in ("auto", "integrated"):
            match = next((x for x in choices if preference in (x["id"], x["name"])), None)
            if not match:
                raise SpotifyError("Устройство не найдено: " + preference)
        elif preference == "integrated":
            match = None
        else:
            external = [x for x in choices if x.get("name") not in ("tspotify", "spotify-player")]
            match = next((x for x in external if x.get("is_active")), None)
        if match:
            self.device_id = match["id"]
            self.external = True
            self.idle = False
            self.last_playback = {}
        return match

    def playback(self, force=False):
        saved = self.last_playback
        remote_ready = None
        observed_start = time.monotonic()
        if self._remote_future is not None and self._remote_future.done():
            try:
                remote_ready = self._remote_future.result() or {}
                observed_start = self._remote_started
            except (SpotifyError, httpx.HTTPError):
                remote_ready = {}
            self._remote_future = None
        if (
            self.backend
            and getattr(self.backend, "observe_connect", False)
            and (remote_ready is not None or force or time.monotonic() - self._last_remote_poll > 4)
        ):
            self._last_remote_poll = time.monotonic()
            try:
                if remote_ready is not None:
                    remote = remote_ready
                elif self.local_controls and not force:
                    if self._remote_future is None:
                        self._remote_started = time.monotonic()
                        self._remote_future = self._remote_pool.submit(self.request, "GET", "me/player")
                    remote = {}
                else:
                    remote = self.request("GET", "me/player") or {}
                event = getattr(self.backend, "event", {})
                if event.get("at", 0) > observed_start:
                    remote = {}  # An older Web response cannot undo a newer native event.
                device = remote.get("device") or {}
                own = getattr(self.backend, "device_id", None)
                stale_own_device = (
                    device.get("name") in ("tspotify", "spotify-player") and device.get("id") != own
                )
                if (
                    remote.get("item")
                    and device.get("id")
                    and device.get("is_active", True)
                    and not stale_own_device
                ):
                    self.external = device["id"] != own
                    self.device_id = device["id"]
                    if not self.external:
                        remote["device"] = {**device, "volume_percent": self.current_volume}
                    remote["_observed_at"] = observed_start
                    remote["_observed_progress_at"] = time.monotonic()
                    remote["_observed_progress_ms"] = remote.get("progress_ms") or 0
                    if self.external or remote.get("is_playing"):
                        self.idle = False
                        self.last_playback = remote
                        saved = remote
            except (SpotifyError, httpx.HTTPError):
                pass
        if self.idle and not self.external and not hasattr(self.backend, "playback") and saved.get("item"):
            return {
                **saved,
                "is_playing": False,
                "device": {"name": "tspotify", "volume_percent": self.current_volume},
            }
        if not self.external and self.backend:
            try:
                value = self.backend.playback(self.last_playback)
                if value:
                    event = getattr(self.backend, "event", {})
                    if (
                        self.idle
                        and event.get("at", 0) > self._restore_gate
                        and (
                            event.get("playing")
                            or event.get("track_id") != (saved.get("item") or {}).get("id")
                        )
                    ):
                        self.idle = False
                    pending = value.pop("_pending_track_id", None)
                    if not pending and (value.get("item") or {}).get("_metadata_pending"):
                        pending = value["item"]["id"]
                    if pending:
                        value["item"] = self.track_metadata(pending)
                    next_id = value.get("next_track_id")
                    value["next_item"] = self.track_metadata(next_id) if next_id else None
                    old_item = self.last_playback.get("item") or {}
                    new_item = value.get("item") or {}
                    if old_item.get("id") == new_item.get("id") and not new_item.get("duration_ms"):
                        value["item"] = {
                            **old_item,
                            **new_item,
                            "duration_ms": old_item.get("duration_ms", 0),
                        }
                    if self.idle:
                        value = {
                            **value,
                            "item": saved.get("item") or value.get("item"),
                            "progress_ms": saved.get("progress_ms", 0),
                        }
                        value = {
                            **value,
                            "is_playing": False,
                            "device": {**(value.get("device") or {}), "volume_percent": self.current_volume},
                        }
                    if not self.external:
                        value["device"] = {
                            **(value.get("device") or {}),
                            "volume_percent": self.current_volume,
                        }
                    if self._runtime_volume is not None and time.monotonic() < self._volume_until:
                        value = {
                            **value,
                            "device": {**(value.get("device") or {}), "volume_percent": self._runtime_volume},
                        }
                    if value.get("is_playing"):
                        self.activate_output_volume()
                    self.last_playback = value
                    return value
            except (OSError, TimeoutError):
                pass
        if force or time.monotonic() - self._last_remote_poll > 4:
            self.last_playback = self.request("GET", "me/player") or {}
            self._last_remote_poll = time.monotonic()
        if self._runtime_volume is not None and time.monotonic() < self._volume_until:
            return {
                **self.last_playback,
                "device": {
                    **(self.last_playback.get("device") or {}),
                    "volume_percent": self._runtime_volume,
                },
            }
        return self.last_playback

    def device_query(self):
        if not self.external and self.backend and getattr(self.backend, "device_id", None):
            self.device_id = self.backend.device_id
        if not self.device_id and self.backend:
            device = self.backend.playback({}).get("device") or {}
            if device.get("name") == "tspotify":
                self.device_id = device.get("id")
        if not self.device_id:
            devices = self.devices()
            match = next((x for x in devices if x.get("name") == "tspotify"), None)
            if not match:
                match = next((x for x in devices if x.get("is_active")), None)
            if match:
                self.device_id = match["id"]
        if not self.device_id:
            raise SpotifyError(
                "Нет устройства воспроизведения. Откройте Spotify или выберите встроенный плеер."
            )
        return "device_id=" + quote(self.device_id, safe="")

    def recover_device(self, force=False):
        self.on_status("Spotify потерял устройство. Проверяю регистрацию…")
        devices = self.devices()
        current = next((d for d in devices if d["id"] == self.device_id), None)
        if current and not force:
            try:
                self.request("PUT", "me/player", {"device_ids": [current["id"]], "play": False})
                return
            except SpotifyError as error:
                if error.status != 404:
                    raise
        if self.external:
            if not self.backend_factory:
                raise SpotifyError(
                    "Выбранное устройство отключилось. Откройте Spotify на нём или выберите встроенный плеер."
                )
            self.on_status("Внешний Spotify отключился. Подключаю встроенный плеер без звука…")
            self.backend = self.backend_factory()
            self.external = False
        for attempt in range(2):
            self.on_status(f"Переподключаю встроенный Spotify ({attempt + 1}/2)…")
            self.backend.restart()
            self.device_id = self.backend.device_id
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                devices = self.devices()
                current = next((d for d in devices if d["id"] == self.backend.device_id), None)
                if current:
                    self.device_id = current["id"]
                    try:
                        self.request("PUT", "me/player", {"device_ids": [current["id"]], "play": False})
                    except SpotifyError as error:
                        if error.status != 404:
                            raise
                        time.sleep(1)
                        continue
                    self.on_status("Устройство зарегистрировано и активировано. Выполняю команду…")
                    return
                time.sleep(1)
        raise SpotifyError(
            "Spotify не зарегистрировал устройство после переподключения. Проверьте сеть и повторите."
        )

    def ensure_engine(self):
        if self.backend and not self.external and hasattr(self.backend, "alive") and not self.backend.alive():
            self.on_status("Движок остановился. Восстанавливаю соединение без звука…")
            self.recover_device(force=True)

    def cancel_start(self):
        self._start_cancel.set()

    def start(self, item, context_uri=None, position_ms=0):
        cancel = threading.Event()
        self._start_cancel = cancel
        volume_revision = self._volume_revision
        self.ensure_engine()
        item = dict(item)
        self.remember_tracks(item)
        if not item.get("duration_ms") and isinstance(item.get("duration"), dict):
            item["duration_ms"] = (
                item["duration"].get("secs", 0) * 1000 + item["duration"].get("nanos", 0) // 1000000
            )
        track_id = item.get("id")
        if not track_id:
            raise SpotifyError("У трека нет Spotify ID")
        uri = "spotify:track:" + track_id
        album = item.get("album") or {}
        context_uri = context_uri or item.get("_context_uri")
        if context_uri and context_uri.startswith("spotify:artist:"):
            context_uri = None  # Artist contexts do not support a track offset.
        if not context_uri and album.get("id"):
            context_uri = "spotify:album:" + album["id"]
        if context_uri:
            item["_context_uri"] = context_uri
        body = {"context_uri": context_uri, "offset": {"uri": uri}} if context_uri else {"uris": [uri]}
        position_ms = max(0, min(int(position_ms), max(0, (item.get("duration_ms") or 86400000) - 1)))
        if position_ms:
            body["position_ms"] = position_ms
        # The backend's CLI starts tasks asynchronously and acknowledges them too early.
        # Send directly and require a real Playing event / remote state for this track.
        if self.backend and not self.external:
            self.backend._events()
        started = time.monotonic()
        if self.local_controls and getattr(self.backend, "local_load", False):
            queue = item.get("_queue_uris") if getattr(self.backend, "local_queue", False) else None
            if not queue and getattr(self.backend, "local_queue", False):
                if context_uri:
                    parts = context_uri.split(":")
                    if (
                        len(parts) == 3
                        and parts[1] in ("album", "playlist")
                        and len(parts[2]) == 22
                        and parts[2].isalnum()
                    ):
                        try:
                            context = json.loads(
                                (paths.CACHE / (parts[1] + "-" + parts[2] + ".json")).read_text()
                            )
                            entries = [track_from_entry(entry) for entry in context.get("tracks", [])]
                            entries = [entry for entry in entries if entry]
                            index = next(
                                (i for i, entry in enumerate(entries) if entry["id"] == track_id), None
                            )
                            if index is not None:
                                first = max(0, index - 20) if len(entries) > 100 else 0
                                queue = [
                                    "spotify:track:" + entry["id"] for entry in entries[first : first + 100]
                                ]
                        except (OSError, ValueError, TypeError, AttributeError):
                            pass
                queue = queue or (None if context_uri else [uri])
                item["_queue_uris"] = queue
            if queue:
                self.backend.load_track(uri, context_uri, position_ms, queue)
            else:
                self.backend.load_track(uri, context_uri, position_ms)
            self.device_id = getattr(self.backend, "device_id", self.device_id)
        else:
            for attempt in range(3):
                try:
                    if self.backend and not self.external:
                        self.backend._events()
                    started = time.monotonic()
                    self.request("PUT", "me/player/play?" + self.device_query(), body)
                    break
                except SpotifyError as error:
                    restricted = error.status == 403 and "Restriction violated" in str(error)
                    if restricted and attempt < 2 and self.backend and not self.external:
                        self.on_status("Spotify ещё не активировал устройство. Подключаю без звука…")
                        self.request(
                            "PUT", "me/player", {"device_ids": [self.backend.device_id], "play": False}
                        )
                        time.sleep(1)
                        continue
                    if error.status != 404:
                        raise
                    if attempt == 2:
                        raise SpotifyError(
                            "Устройство Spotify отключилось. Переподключение не подтвердилось; трек не запущен.",
                            status=404,
                        ) from None
                    if self.external and not self.backend_factory:
                        raise SpotifyError(
                            "Выбранное устройство Spotify отключилось. Откройте Spotify на нём и повторите запуск.",
                            status=404,
                        ) from None
                    if not self.backend and not self.backend_factory:
                        raise
                    self.recover_device(force=attempt > 0)
                    time.sleep(1.5)  # Connect discovery may lag the local control socket.
        if self.backend and not self.external:
            self.backend.wait_playing(
                track_id, since=started, timeout=25, cancelled=cancel.is_set, position_ms=position_ms
            )
            if cancel.is_set():
                return ""
            event = getattr(self.backend, "event", {})
            if event.get("at", 0) >= started and event.get("track_id") not in (None, track_id):
                return ""  # A phone or newer command already selected another track.
            self.backend._snapshot_time = 0
            self.last_playback = {
                "item": item,
                "is_playing": True,
                "progress_ms": position_ms,
                "device": {"id": self.device_id, "name": "tspotify", "volume_percent": self.current_volume},
            }
            self.idle = False
            self.activate_output_volume()
            with self._volume_lock:
                volume = getattr(self.backend, "preferred_volume", self.current_volume)
                if (
                    self._volume_revision == volume_revision
                    and volume > 0
                    and not getattr(self.backend, "muted", True)
                    and getattr(self.backend, "confirmed_volume", None) != volume
                ):
                    try:
                        self.control("volume", volume)
                    except RateLimited as error:
                        self.on_volume_retry(
                            volume, error.seconds, getattr(self.backend, "confirmed_volume", 0)
                        )
                self.last_playback["device"]["volume_percent"] = self.current_volume
            self.save_session(self.last_playback, volume=self.current_volume)
            return "Воспроизводится: " + item.get("name", "трек")
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            value = self.playback(force=True)
            if value.get("is_playing") and (value.get("item") or {}).get("id") == track_id:
                self.idle = False
                self.save_session(value, volume=(value.get("device") or {}).get("volume_percent"))
                return "Воспроизводится: " + item.get("name", "трек")
            time.sleep(0.5)
        raise SpotifyError("Spotify принял запрос, но запуск выбранного трека не подтверждён.")

    def start_jam(self):
        """Create/retrieve a real Jam using native session credentials, never a track link."""
        self.ensure_engine()
        if not self.local_controls or not getattr(self.backend, "native_jam", False):
            raise SpotifyError("Для Jam нужен обновлённый встроенный движок tspotify")
        self.backend.local_control("jam-start")
        deadline = time.monotonic() + 22
        while time.monotonic() < deadline:
            state = self.backend.request({"Local": {"command": "state", "value": 0}}, timeout=0.5)
            jam = (state or {}).get("jam") or {}
            if jam.get("status") == "error":
                raise SpotifyError(
                    "Spotify не создал Jam: " + str(jam.get("message", "неизвестная ошибка"))[:240]
                )
            if jam.get("status") == "ready":
                from .sharing import jam_invite_url

                try:
                    url = jam_invite_url(jam.get("url", ""))
                except ValueError as error:
                    raise SpotifyError(str(error)) from None
                return {"url": url, "members": jam.get("members") or []}
            time.sleep(0.15)
        raise SpotifyError("Spotify не подтвердил создание Jam за 22 секунды")

    def control(self, command, value=None, _retry=False):
        if command == "volume":
            with self._volume_lock:
                return self._checked_control(command, value, _retry)
        return self._checked_control(command, value, _retry)

    def _checked_control(self, command, value=None, _retry=False):
        try:
            return self._control(command, value)
        except SpotifyError as error:
            if error.status != 404 or _retry:
                raise
            if not self.backend and not self.backend_factory:
                raise SpotifyError(
                    "Выбранное устройство Spotify отключилось. Откройте его и повторите команду.", status=404
                ) from None
            self.recover_device(force=False)
            return self.control(command, value, _retry=True)

    def _control(self, command, value=None):
        if command in ("next", "previous", "pause", "play-pause"):
            self.cancel_start()
        self.ensure_engine()
        if command in ("play", "play-pause", "next", "previous") and self.idle and not self.external:
            snapshot = self.playback()
            item = snapshot.get("item") or {}
            if item.get("id") and self.idle:
                position = snapshot.get("progress_ms") or 0
                duration = item.get("duration_ms") or 0
                if not duration and isinstance(item.get("duration"), dict):
                    duration = (
                        item["duration"].get("secs", 0) * 1000 + item["duration"].get("nanos", 0) // 1000000
                    )
                if duration and position >= duration - 1000:
                    position = 0
                if command in ("next", "previous"):
                    queue = item.get("_queue_uris") or []
                    context_uri = item.get("_context_uri") or ""
                    if not context_uri and (item.get("album") or {}).get("id"):
                        context_uri = "spotify:album:" + item["album"]["id"]
                    if not queue and context_uri:
                        parts = context_uri.split(":")
                        if len(parts) == 3 and parts[1] in ("album", "playlist"):
                            context = self.context(parts[1], parts[2], "")
                            entries = [track_from_entry(t) for t in context.get("tracks", [])]
                            entries = [t for t in entries if t]
                            self.remember_tracks(entries)
                            queue = ["spotify:track:" + t["id"] for t in entries]
                    uri = "spotify:track:" + item["id"]
                    if queue and uri in queue:
                        index = (queue.index(uri) + (1 if command == "next" else -1)) % len(queue)
                        identity = queue[index].removeprefix("spotify:track:")
                        first = max(0, index - 20) if len(queue) > 100 else 0
                        item = {**self.track_metadata(identity), "_queue_uris": queue[first : first + 100]}
                        if context_uri:
                            item["_context_uri"] = context_uri
                    position = 0
                return self.start(item, position_ms=position)
            if item.get("id"):
                # A phone/Connect event superseded the saved session during observation.
                return self._control(
                    command
                    if command in ("next", "previous")
                    else "pause"
                    if snapshot.get("is_playing")
                    else "play"
                )
            if command in ("play", "play-pause"):
                raise SpotifyError("Выберите трек в библиотеке, чтобы начать воспроизведение")
        local = self.local_controls
        device = "" if local else self.device_query()
        if command == "play-pause":
            snapshot = self.backend.playback(self.last_playback) if local else self.playback()
            command = "pause" if snapshot.get("is_playing") else "play"
        if command == "volume":
            self._volume_revision += 1
            value = max(0, min(100, int(value)))
            if local:
                self.backend.local_control("volume", value)
            else:
                self.request("PUT", f"me/player/volume?volume_percent={value}&{device}")
            if self.backend:
                self.backend.preferred_volume = value
                self.backend.confirmed_volume = value
                self.backend._volume_set_at = time.monotonic()
                self.backend._snapshot_time = 0
                if value > 0:
                    self.backend.muted = False
                if not local:
                    self.backend.unmute_after_user_volume(value)
                elif value > 0 and not getattr(self.backend, "_audio_output_ready", False):
                    self.backend.unmute_after_user_volume(value)
                    self.backend._audio_output_ready = True
            self._runtime_volume = value
            self._volume_until = time.monotonic() + 12
            self.save_session(volume=value)
            return f"Громкость: {value}%"
        if command == "seek":
            position = max(0, int(value))
            if local:
                self.backend.local_control("seek", position)
                if self.backend.event:
                    self.backend.event = {**self.backend.event, "position": position, "at": time.monotonic()}
                self.last_playback = {**self.last_playback, "progress_ms": position}
            else:
                self.request("PUT", f"me/player/seek?position_ms={position}&{device}")
            if self.backend:
                self.backend._snapshot_time = 0
            self._last_remote_poll = 0
            return "Позиция воспроизведения изменена"
        if local and command in ("shuffle", "repeat"):
            if not getattr(self.backend, "local_modes", False):
                raise SpotifyError("Нужно обновление встроенного движка для shuffle/repeat")
            state = self.backend.playback(self.last_playback)
            if command == "shuffle":
                target = not state.get("shuffle_state", False)
                self.backend.local_control("shuffle", int(target))
                message = "Перемешивание: " + ("включено" if target else "выключено")
            else:
                modes = ["off", "context", "track"]
                target = modes[(modes.index(state.get("repeat_state", "off")) + 1) % len(modes)]
                self.backend.local_control("repeat", modes.index(target))
                message = "Повтор: " + {"off": "выключен", "context": "список", "track": "один трек"}[target]
            self.last_playback = self.backend.playback(state)
            if not getattr(self.backend, "atomic_modes", False) and getattr(
                self.backend, "native_snapshot", {}
            ).get("queue_current_uri"):
                deadline = time.monotonic() + 0.4
                field = "shuffle_state" if command == "shuffle" else "repeat_state"
                while (
                    self.last_playback.get("modes_pending") or self.last_playback.get(field) != target
                ) and time.monotonic() < deadline:
                    time.sleep(0.005)
                    self.last_playback = self.backend.playback(self.last_playback)
            if (
                self.last_playback.get("modes_pending")
                or self.last_playback.get("shuffle_state" if command == "shuffle" else "repeat_state")
                != target
            ):
                message += " · ожидает применения"
            return message
        if local and command in ("next", "previous", "play", "pause"):
            self.backend.local_control(command)
            if command in ("play", "pause"):
                state = self.backend.playback(self.last_playback)
                self.last_playback = {**state, "is_playing": command == "play"}
                if self.backend.event:
                    self.backend.event = {
                        **self.backend.event,
                        "playing": command == "play",
                        "position": state.get("progress_ms", 0),
                        "at": time.monotonic(),
                    }
            return "Пауза" if command == "pause" else "Продолжено" if command == "play" else ""
        if command in ("next", "previous"):
            self.request("POST", f"me/player/{command}?{device}")
        elif command in ("play", "pause"):
            self.request("PUT", f"me/player/{command}?{device}")
        elif command == "shuffle":
            value = not self.playback().get("shuffle_state", False)
            self.request("PUT", f"me/player/shuffle?state={str(value).lower()}&{device}")
        elif command == "repeat":
            modes = ["off", "context", "track"]
            current = self.playback().get("repeat_state", "off")
            value = modes[(modes.index(current) + 1) % len(modes)]
            self.request("PUT", f"me/player/repeat?state={value}&{device}")
        else:
            raise ValueError("Неизвестная команда воспроизведения")
        self._last_remote_poll = 0
        return "Команда выполнена"

    def favorite(self, track_id, unlike=False):
        self.request("DELETE" if unlike else "PUT", "me/tracks", {"ids": [track_id]})

    def toggle_favorite(self, track_id):
        saved = self.request("GET", "me/tracks/contains?ids=" + quote(track_id, safe=""))
        unlike = bool(saved and saved[0])
        self.favorite(track_id, unlike=unlike)
        return not unlike

    def library(self, section):
        if section not in ("Плейлисты", "Альбомы", "Любимые"):
            return self.discover(section)
        mapping = {
            "Плейлисты": ("playlist", "me/playlists?limit=50"),
            "Альбомы": ("album", "me/albums?limit=50"),
            "Любимые": ("track", "me/tracks?limit=50"),
        }
        kind, endpoint = mapping[section]
        target = paths.CACHE / f"library-{kind}.json"
        try:
            if target.exists() and time.time() - target.stat().st_mtime < 600:
                cached = json.loads(target.read_text(encoding="utf-8"))
                if isinstance(cached, list):
                    return section, cached
        except (OSError, ValueError):
            pass
        result = []
        page = self.request("GET", endpoint)
        while page:
            for entry in page.get("items", []):
                if not entry:
                    continue
                item = (
                    entry.get("album", entry)
                    if kind == "album"
                    else track_from_entry(entry)
                    if kind == "track"
                    else entry
                )
                if isinstance(item, dict) and item.get("id"):
                    result.append((kind, item))
            page = self.request("GET", page["next"]) if page.get("next") else None
        paths.private_json(target, result)
        return section, result

    def discover(self, section):
        """Read real Spotify data lazily; never substitute invented recommendations."""
        if section == "Новые релизы":
            raise SpotifyError(
                "Spotify удалил каталог новых релизов из Web API для Dev Mode. "
                "Найдите релиз через поиск Spotify."
            )
        names = {
            "Недавние": "recent",
            "Ваши миксы": "mixes",
            "Новые релизы": "releases",
            "Рекомендации": "recommendations",
            "Миксы дня": "daily",
        }
        if section not in names:
            raise SpotifyError("Неизвестный раздел библиотеки")
        target = paths.CACHE / ("discover-" + names[section] + ".json")
        ttl = 60 if section == "Недавние" else 600
        try:
            if time.time() - target.stat().st_mtime < ttl:
                result = json.loads(target.read_text(encoding="utf-8"))
                if isinstance(result, list):
                    return section, result
        except (OSError, ValueError):
            pass
        result = []
        try:
            if section == "Недавние":
                data = self.request("GET", "me/player/recently-played?limit=50") or {}
                playlists = dict((item["id"], item) for _, item in self.library("Плейлисты")[1])
                seen = set()
                for entry in data.get("items", []):
                    track = track_from_entry(entry)
                    context = entry.get("context") or {}
                    uri = context.get("uri", "").split(":")
                    if len(uri) == 3 and uri[1] in ("playlist", "album"):
                        kind, identity = uri[1:]
                        item = playlists.get(identity) if kind == "playlist" else (track or {}).get("album")
                        if item and item.get("id") == identity and (kind, identity) not in seen:
                            seen.add((kind, identity))
                            result.append((kind, item))
                    if track and ("track", track["id"]) not in seen:
                        seen.add(("track", track["id"]))
                        result.append(("track", track))
            elif section in ("Ваши миксы", "Миксы дня"):
                for kind, item in self.library("Плейлисты")[1]:
                    name = item.get("name", "").casefold()
                    owner = item.get("owner") or {}
                    spotify = isinstance(owner, dict) and owner.get("id") == "spotify"
                    daily = any(word in name for word in ("daily mix", "daylist", "микс дня", "микс на день"))
                    mixed = daily or any(
                        word in name
                        for word in (
                            "mix",
                            "микс",
                            "discover weekly",
                            "release radar",
                            "радар новинок",
                            "открытия недели",
                        )
                    )
                    if (daily if section == "Миксы дня" else mixed) and spotify:
                        result.append((kind, item))
            elif section == "Рекомендации":
                top = self.request("GET", "me/top/tracks?limit=5&time_range=short_term") or {}
                seeds = ",".join(item["id"] for item in top.get("items", []) if item and item.get("id"))
                if seeds:
                    data = self.request("GET", "recommendations?limit=50&seed_tracks=" + seeds) or {}
                    result = [("track", item) for item in data.get("tracks", []) if item and item.get("id")]
        except SpotifyError as error:
            if error.status in (403, 404):
                raise SpotifyError(
                    f"Раздел «{section}» недоступен для этого входа Spotify. Остальная библиотека работает.",
                    status=error.status,
                ) from None
            raise
        paths.private_json(target, result)
        return section, result

    def start_context(self, kind, item):
        value = self.context(kind, item["id"], item.get("name", ""))
        tracks = value["tracks"]
        if not tracks:
            raise SpotifyError("В этом плейлисте нет доступных треков")
        return self.start(tracks[0], value["context_uri"])

    def context(self, kind, item_id, name):
        target = paths.CACHE / f"{kind}-{item_id}.json"
        try:
            if target.exists() and time.time() - target.stat().st_mtime < 3600:
                value = json.loads(target.read_text(encoding="utf-8"))
                if isinstance(value, dict) and isinstance(value.get("tracks"), list):
                    value["context_uri"] = f"spotify:{kind}:{item_id}"
                    self.remember_tracks(value)
                    return value
        except (OSError, ValueError):
            pass
        if kind == "playlist":
            page = self.request("GET", f"playlists/{item_id}/items?limit=50")
        elif kind == "album":
            page = self.request("GET", f"albums/{item_id}/tracks?limit=50")
        elif kind == "artist":
            raise SpotifyError(
                "Рейтинг популярных треков артиста удалён из Spotify Web API. "
                "Откройте страницу артиста, чтобы просмотреть каталог релизов."
            )
        else:
            raise SpotifyError("Этот раздел пока не поддерживает список треков")
        tracks = []
        while page:
            for entry in page.get("items", []):
                track = track_from_entry(entry)
                if track:
                    tracks.append(track)
            page = self.request("GET", page["next"]) if page.get("next") else None
        value = {"name": name, "tracks": tracks, "context_uri": f"spotify:{kind}:{item_id}"}
        paths.private_json(target, value)
        return value

    def artist_profile(self, item_id, name=""):
        target = paths.CACHE / f"artist-profile-{item_id}.json"
        try:
            if target.exists() and time.time() - target.stat().st_mtime < 3600:
                value = json.loads(target.read_text(encoding="utf-8"))
                if isinstance(value, dict) and isinstance(value.get("artist"), dict):
                    return value
        except (OSError, ValueError):
            pass

        identity = quote(item_id, safe="")
        artist = self.request("GET", f"artists/{identity}") or {}
        if not artist.get("id"):
            artist = {"id": item_id, "name": name or "Artist", "images": []}
        releases = {"album": [], "single": [], "appears_on": [], "compilation": []}
        unavailable_groups = {}
        for group in releases:
            try:
                page = self.request(
                    "GET", f"artists/{identity}/albums?include_groups={group}&limit=10"
                ) or {}
                seen = set()
                while page:
                    for release in page.get("items", []):
                        if not isinstance(release, dict) or not release.get("id") or release["id"] in seen:
                            continue
                        seen.add(release["id"])
                        release.setdefault("_artist_group", group)
                        releases[group].append(release)
                    page = self.request("GET", page["next"]) if page.get("next") else None
            except SpotifyError as error:
                if error.status not in (403, 404):
                    raise
                unavailable_groups[group] = error.status

        value = {
            "artist": artist,
            "releases": releases,
            "unavailable_groups": unavailable_groups,
            "context_uri": f"spotify:artist:{item_id}",
            "catalog_label": "Доступный каталог релизов",
        }
        paths.private_json(target, value)
        return value

    def search(self, query, category="all", offset=0):
        type_map = {
            "all": "track,artist,album,playlist",
            "track": "track",
            "artist": "artist",
            "album": "album",
            "playlist": "playlist",
        }
        if category not in type_map:
            raise SpotifyError("Неизвестная категория поиска")
        offset = max(0, int(offset))
        data = self.request(
            "GET",
            "search?q=" + quote(query) + "&type=" + type_map[category] + f"&limit=10&offset={offset}",
        )
        names = {"tracks": "track", "artists": "artist", "albums": "album", "playlists": "playlist"}
        results = {}
        paging = {}
        for plural, singular in names.items():
            page = data.get(plural)
            if not isinstance(page, dict):
                continue
            results[plural] = page.get("items", [])
            paging[singular] = {
                "offset": page.get("offset", offset),
                "total": page.get("total", len(results[plural])),
                "next": page.get("next"),
            }
        results["_paging"] = paging
        return results
