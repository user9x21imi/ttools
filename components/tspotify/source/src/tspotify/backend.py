"""Pinned, verified streaming engine and a foreground-owned cross-platform PTY."""

import hashlib
from datetime import datetime
import io
import json
import os
import platform
import re
import shutil
import signal
import socket
import subprocess
import sys
import tarfile
import threading
import time
import zipfile
from pathlib import Path

import httpx

from . import paths, session

VERSION = "0.25.2"
ASSETS = {
    ("Linux", "x86_64"): (
        "x86_64-unknown-linux-gnu.tar.gz",
        "08b572e0ec4b93418ade1d99703dbd0d2bdd14061babd36ea001153d749a1f4c",
    ),
    ("Linux", "aarch64"): (
        "aarch64-unknown-linux-gnu.tar.gz",
        "05fc52a25ecdf12c554f3fd567f3caef9e3604df2e49538fff7598b2003a26bb",
    ),
    ("Darwin", "arm64"): (
        "aarch64-apple-darwin.tar.gz",
        "082de0ed83120804b3e1c2b91b9c21e37dfa111c51593847f52e1a40b6fb9b55",
    ),
    ("Darwin", "x86_64"): (
        "x86_64-apple-darwin.tar.gz",
        "9b7c6fde406c9caa341e1b6f5041627b941f8f7f9f8733b004af8470a2f83937",
    ),
    ("Windows", "AMD64"): (
        "x86_64-pc-windows-msvc.zip",
        "5ddd441c1572c09c84a253b6fb2a63beb64627a785a88328d2e438a5c29432c9",
    ),
}


def asset_for(system=None, machine=None):
    system, machine = system or platform.system(), machine or platform.machine()
    if system == "Windows" and machine.lower() in ("x86_64", "amd64"):
        machine = "AMD64"
    if system == "Linux" and machine == "arm64":
        machine = "aarch64"
    try:
        return ASSETS[system, machine]
    except KeyError:
        raise RuntimeError(f"Нет проверенной сборки Spotify engine для {system}/{machine}") from None


def unpack_engine(data, suffix):
    """Extract exactly one regular executable, never archive paths or symlinks."""
    name = "spotify_player.exe" if suffix.endswith(".zip") else "spotify_player"
    if suffix.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = [x for x in archive.infolist() if Path(x.filename).name == name and not x.is_dir()]
            if len(entries) != 1 or entries[0].file_size > 600_000_000:
                raise RuntimeError("Неверный архив движка")
            return archive.read(entries[0])
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        entries = [x for x in archive.getmembers() if Path(x.name).name == name and x.isfile()]
        if len(entries) != 1 or entries[0].size > 600_000_000:
            raise RuntimeError("Неверный архив движка")
        return archive.extractfile(entries[0]).read()


def engine_path(install=True, announce=True):
    configured = os.environ.get("TSPOTIFY_ENGINE")
    if configured:
        value = Path(configured).expanduser().resolve()
        if not value.is_file():
            raise RuntimeError("TSPOTIFY_ENGINE не указывает на исполняемый файл")
        return value
    name = "spotify_player.exe" if os.name == "nt" else "spotify_player"
    if getattr(sys, "frozen", False):
        bundled = Path(sys.executable).parent / "engine" / name
        if bundled.is_file():
            return bundled
    target = paths.DATA / "bin" / name
    if target.exists():
        return target
    existing = shutil.which(name)
    if existing:
        version = subprocess.run([existing, "--version"], capture_output=True, text=True, timeout=5)
        if version.returncode == 0 and VERSION in version.stdout:
            return Path(existing)
    if not install:
        return None
    suffix, expected = asset_for()
    if announce:
        print(f"Downloading verified Spotify engine {VERSION} ({suffix})...", flush=True)
    url = f"https://github.com/aome510/spotify-player/releases/download/v{VERSION}/spotify_player-{suffix}"
    with httpx.stream("GET", url, follow_redirects=True, timeout=120) as response:
        response.raise_for_status()
        data = bytearray()
        for chunk in response.iter_bytes(131072):
            data.extend(chunk)
            if len(data) > 150_000_000:
                raise RuntimeError("Архив превышает допустимый размер")
    if hashlib.sha256(data).hexdigest() != expected:
        raise RuntimeError("Контрольная сумма Spotify engine не совпала; установка остановлена")
    binary = unpack_engine(data, suffix)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(".download")
    temp.write_bytes(binary)
    temp.chmod(0o755)
    temp.replace(target)
    return target


class Backend:
    def __init__(self, muted=False, external=False, on_authorize=None):
        self.muted = muted
        self.external = external
        self.preferred_volume = 0 if muted else session.load()["volume"]
        self.local_enabled = False
        self.local_load = False
        self.local_queue = False
        self.native_state = False
        self.local_modes = False
        self.native_jam = False
        self.atomic_modes = False
        self.native_snapshot = {}
        self.confirmed_volume = 0
        self._volume_set_at = 0.0
        self.device_id = None
        self.on_authorize = on_authorize
        self.process = None
        self.pty = None
        self.job = None
        self.master = None
        self.stopped = threading.Event()
        self.changed = threading.Condition()
        self.event = {}
        self.failure = None
        self.failure_at = 0.0
        self.failure_signature = None
        self._base = {}
        self._snapshot_time = 0.0
        self.output_tail = ""
        self._query_tail = ""
        self.authorizing = threading.Event()
        self.authorization_error = None
        self._authorization_started = 0.0
        self.reader_thread = None
        self.observe_connect = True
        self.log_started = 0
        self.log_path = None

    def request(self, request, timeout=2):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024)
            sock.settimeout(timeout)
            sock.connect(("127.0.0.1", paths.PORT))
            payload = json.dumps(request).encode()
            if len(payload) > 60000:
                raise RuntimeError("Слишком большая команда очереди; сократите список")
            sock.send(payload)
            data = bytearray()
            while True:
                chunk = sock.recv(8192)
                if not chunk:
                    break
                data.extend(chunk)
                if len(data) > 16 * 1024 * 1024:
                    raise RuntimeError("Слишком большой ответ локального движка")
            try:
                result = json.loads(data)
            except ValueError:
                raise RuntimeError(
                    "Встроенный плеер вернул повреждённый ответ. Перезапустите клиент."
                ) from None
            if "Err" in result:
                raise RuntimeError(bytes(result["Err"]).decode(errors="replace"))
            payload = bytes(result["Ok"])
            try:
                return json.loads(payload) if payload.strip() else None
            except ValueError:
                raise RuntimeError("Встроенный плеер вернул повреждённые данные воспроизведения.") from None

    def local_control(self, command, value=0):
        result = self.request({"Local": {"command": command, "value": int(value or 0)}}, timeout=0.3)
        if not isinstance(result, dict) or not result.get("accepted"):
            raise RuntimeError("Локальный движок не подтвердил команду")
        return result

    def load_track(self, uri, context_uri=None, position_ms=0, uris=None):
        payload = {"uri": uri, "context_uri": context_uri}
        if uris:
            payload["uris"] = uris[:100]
        command = "load:" + json.dumps(payload, separators=(",", ":"))
        self.local_control(command, position_ms)

    def alive(self):
        return self.pty.isalive() if self.pty else bool(self.process and self.process.poll() is None)

    def ready(self):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.settimeout(0.2)
                sock.connect(("127.0.0.1", paths.PORT))
                sock.send(b"")
                return sock.recv(1) == b""
        except OSError:
            return False

    def start(self, *, quiet=False):
        if self.stopped.is_set():
            raise RuntimeError("Запуск встроенного плеера отменён")
        if self.ready():
            raise RuntimeError(
                "Порт встроенного плеера уже занят другим экземпляром tspotify. Закройте его перед запуском."
            )
        self.confirmed_volume = 0
        self._volume_active = False
        self._audio_output_ready = False
        paths.prepare()
        binary = engine_path(announce=False) if quiet else engine_path()
        if self.stopped.is_set():
            raise RuntimeError("Запуск встроенного плеера отменён")
        self.log_started = time.time()
        self.log_path = None
        # This folder belongs to tspotify; never overwrite a user's other client settings.
        config = f'''client_id = "d420a117a32841c2b3474932e49fb54b"
login_redirect_uri = "http://127.0.0.1:8989/login"
client_port = {paths.PORT}
ap_port = 443
app_refresh_duration_in_ms = 1000
playback_refresh_duration_in_ms = 0
enable_streaming = "{"Never" if self.external else "Always"}"
enable_media_control = false
pause_on_startup = false
custom_queue = false
[device]
name = "tspotify"
device_type = "speaker"
volume = 0
bitrate = 160
audio_cache = true
'''
        (paths.BACKEND_CONFIG / "app.toml").write_text(config, encoding="utf-8")
        args = [
            str(binary),
            "--config-folder",
            str(paths.BACKEND_CONFIG),
            "--cache-folder",
            str(paths.BACKEND_CACHE),
        ]
        env = os.environ.copy()
        # The frontend handles authorization URLs once, instead of racing xdg-open/Firefox.
        env["BROWSER"] = "true" if os.name != "nt" else "cmd /c exit"
        if os.name == "nt":
            import subprocess as sp
            from winpty import PtyProcess

            # ConPTY wraps console output; keep first-run OAuth URLs on one line.
            self.pty = PtyProcess.spawn(sp.list2cmdline(args), dimensions=(30, 2000), env=env)
            from ._winjob import Job

            self.job = Job(self.pty.pid)
        else:
            import fcntl
            import pty
            import struct
            import termios

            master, slave = pty.openpty()
            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 30, 100, 0, 0))
            worker = (
                [sys.executable, "_engine_worker"]
                if getattr(sys, "frozen", False)
                else [sys.executable, "-m", "tspotify._worker"]
            )
            self.process = subprocess.Popen(
                worker + [str(os.getpid())] + args,
                stdin=slave,
                stdout=slave,
                stderr=slave,
                start_new_session=True,
                env=env,
            )
            os.close(slave)
            self.master = master
        self.reader_thread = threading.Thread(target=self._read, daemon=True, name="spotify-engine-output")
        self.reader_thread.start()
        deadline = time.monotonic() + 75
        while not self.ready() or self.authorizing.is_set():
            if self.stopped.is_set():
                raise RuntimeError("Запуск встроенного плеера отменён")
            if self.authorization_error:
                self.close()
                raise RuntimeError(self.authorization_error)
            if self.authorizing.is_set():
                deadline = max(deadline, self._authorization_started + 180)
            if time.monotonic() > deadline:
                self.close()
                raise RuntimeError(
                    "Встроенный плеер не подключился к Spotify за 75 секунд. Проверьте доступ к сети; сохранённый вход не сброшен."
                )
            if self.process and self.process.poll() is not None:
                raise RuntimeError("Spotify engine завершился при запуске. Выполните tspotify doctor")
            self.stopped.wait(0.15)
        try:
            capabilities = self.request({"Local": {"command": "capabilities", "value": 0}}, timeout=0.2)
            self.local_enabled = capabilities.get("protocol") == 1
            self.local_load = bool(capabilities.get("local_load"))
            self.local_queue = bool(capabilities.get("local_queue"))
            self.native_state = bool(capabilities.get("native_state"))
            self.local_modes = bool(capabilities.get("local_modes"))
            self.native_jam = bool(capabilities.get("native_jam"))
            self.atomic_modes = bool(capabilities.get("atomic_modes"))
        except (OSError, RuntimeError, AttributeError):
            self.local_enabled = False
        if self.local_enabled and not self.external:
            deadline = time.monotonic() + 5
            while True:
                try:
                    self.local_control("pause")
                    self.local_control("volume", self.preferred_volume)
                    self.confirmed_volume = self.preferred_volume
                    break
                except RuntimeError as error:
                    if "still connecting" not in str(error) or time.monotonic() >= deadline:
                        raise
                    if self.stopped.wait(0.03):
                        raise RuntimeError("Подключение плеера отменено") from error
        self._snapshot_time = 0
        if self.pty:
            try:
                self.pty.setwinsize(30, 100)
            except (AttributeError, OSError):
                pass
        self._events()

    def _read(self):
        buffer = ""
        while not self.stopped.is_set():
            try:
                chunk = (
                    self.pty.read(4096) if self.pty else os.read(self.master, 8192).decode(errors="replace")
                )
                if not chunk:
                    return
                self.respond_queries(chunk)
                self.output_tail = (self.output_tail + chunk)[-6000:]
                buffer += chunk
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    self._line(line)
                if len(buffer) > 200_000:
                    buffer = buffer[-4000:]
            except (OSError, EOFError):
                return

    def respond_queries(self, chunk):
        # A PTY supplies a terminal device, not an emulator. Crossterm asks for
        # cursor position during startup; ignoring CPR makes the engine exit
        # after briefly opening its socket, which looks like a successful start.
        data = self._query_tail + chunk
        for _ in range(data.count("\x1b[6n")):
            if self.pty:
                self.pty.write("\x1b[1;1R")
            elif self.master is not None:
                os.write(self.master, b"\x1b[1;1R")
        self._query_tail = data[-3:]

    def _line(self, line):
        match = re.search(r"Browse to: (https://accounts\.spotify\.com/authorize\?[^\s\x1b]+)", line)
        if match and self.on_authorize:
            self.authorizing.set()
            self._authorization_started = time.monotonic()
            try:
                self.on_authorize(match.group(1))
            except (OSError, ValueError, RuntimeError, httpx.HTTPError) as error:
                self.authorization_error = str(error)
            finally:
                self.authorizing.clear()
        # Runtime logs go to the engine cache, so stream the log too via playback().

    def read_native_state(self):
        value = self.request({"Local": {"command": "state", "value": 0}}, timeout=0.3) or {}
        self.native_snapshot = value
        identity = value.get("device_id")
        if identity and identity != self.device_id:
            self.device_id = identity
            self._volume_active = self._audio_output_ready = False
        uri = value.get("track_uri") or ""
        if uri.startswith("spotify:track:"):
            stamp = value.get("position_at_ms") or value.get("event_at_ms") or time.time() * 1000
            signature = (uri, stamp, value.get("is_playing"), value.get("is_loading"))
            if signature != self.event.get("signature"):
                self.event = {
                    "signature": signature,
                    "track_id": uri.removeprefix("spotify:track:"),
                    "playing": bool(value.get("is_playing")),
                    "position": int(value.get("position_ms") or 0),
                    "at": time.monotonic() - max(0, time.time() - stamp / 1000),
                }
        failure = value.get("failure_uri") or ""
        if failure.startswith("spotify:track:"):
            self.failure = failure.removeprefix("spotify:track:")
            self.failure_at = time.monotonic() - max(
                0, time.time() - (value.get("failure_at_ms") or 0) / 1000
            )
        return value

    def _events(self):
        if self.native_state:
            self.read_native_state()
            return
        files = list(paths.BACKEND_CACHE.glob("spotify-player-*.log"))
        if not files:
            return
        if self.log_path is None:
            candidates = []
            for path in files:
                try:
                    if path.stat().st_mtime < self.log_started - 1:
                        continue
                    with path.open("rb") as stream:
                        stream.seek(max(0, path.stat().st_size - 200000))
                        header = stream.read().decode(errors="replace")
                    for match in re.finditer(
                        r"(?m)^(\S+).*Initializing a new integrated player with device_id=([0-9a-f-]+)",
                        header,
                    ):
                        stamp = datetime.fromisoformat(match[1].replace("Z", "+00:00")).timestamp()
                        if stamp >= self.log_started:
                            candidates.append((stamp, path, match[2]))
                except (OSError, ValueError):
                    continue
            if candidates:
                _, self.log_path, identity = max(candidates, key=lambda entry: entry[0])
                if self.device_id is None:
                    self.device_id = identity
        latest = self.log_path or max(files, key=lambda p: p.stat().st_mtime)
        try:
            with latest.open("rb") as stream:
                stream.seek(max(0, latest.stat().st_size - 18000))
                text = stream.read().decode(errors="replace")
        except OSError:
            return
        identities = re.findall(r"Initializing a new integrated player with device_id=([0-9a-f-]+)", text)
        if identities and identities[-1] != self.device_id:
            self.device_id = identities[-1]
            self._volume_active = False
            self._audio_output_ready = False
        matches = list(
            re.finditer(
                r"Got a new player event: (Playing|Paused) \{ playable_id: Track\(TrackId\(\"([^\"]+)\"\)\), position_ms: (\d+)",
                text,
            )
        )
        if matches:
            match = matches[-1]
            signature = text[text.rfind("\n", 0, match.start()) + 1 : match.end()]
            if signature != self.event.get("signature"):
                stamp = signature.split(" ", 1)[0]
                age = 0
                try:
                    timestamp = datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp()
                    if timestamp < self.log_started:
                        return
                    age = max(0, time.time() - timestamp)
                except ValueError:
                    pass
                self.event = {
                    "signature": signature,
                    "track_id": match[2],
                    "playing": match[1] == "Playing",
                    "position": int(match[3]),
                    "at": time.monotonic() - age,
                }
        failures = list(re.finditer(r"unable to load track.*?spotify:track:([A-Za-z0-9]+)", text, re.I))
        if failures:
            match = failures[-1]
            signature = text[text.rfind("\n", 0, match.start()) + 1 : match.end()]
            if signature != self.failure_signature:
                self.failure_signature = signature
                self.failure = match[1]
                self.failure_at = time.monotonic()

    def wait_playing(self, track_id, since, timeout=25, cancelled=None, position_ms=None):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if cancelled and cancelled():
                return
            self._events()
            if (
                self.event.get("track_id") == track_id
                and self.event.get("playing")
                and self.event.get("at", 0) >= since
                and (position_ms is None or abs(self.event.get("position", 0) - position_ms) < 2000)
            ):
                return
            if self.failure == track_id and self.failure_at >= since:
                raise RuntimeError(
                    "Spotify не смог загрузить аудио этого трека. Повторите или выберите другое устройство."
                )
            if self.stopped.wait(0.02 if self.local_enabled else 0.25):
                break
        raise RuntimeError(
            "Запуск трека не подтверждён: проверьте сеть или выберите настольный Spotify как устройство."
        )

    def playback(self, fallback):
        self._events()
        if self.native_state:
            state = self.native_snapshot
            result = dict(fallback)
            if self.event:
                if (result.get("item") or {}).get("id") != self.event["track_id"]:
                    result["item"] = None
                    result["_pending_track_id"] = self.event["track_id"]
                elapsed = max(0, time.monotonic() - self.event["at"]) if self.event["playing"] else 0
                result.update(
                    is_playing=self.event["playing"], progress_ms=self.event["position"] + elapsed * 1000
                )
            else:
                result["is_playing"] = False
            result["is_loading"] = bool(state.get("is_loading"))
            result["shuffle_state"] = state.get("desired_shuffle", state.get("shuffle_state", False))
            result["repeat_state"] = state.get("desired_repeat", state.get("repeat_state", "off"))
            result["modes_pending"] = "desired_shuffle" in state or "desired_repeat" in state
            result["native_seek_revision"] = state.get("seek_revision", 0)
            result["queue_ended"] = bool(state.get("queue_ended"))
            next_uris = state.get("next_uris") or []
            next_uri = (
                state.get("queue_current_uri")
                if result["queue_ended"]
                else state.get("track_uri")
                if result["repeat_state"] == "track"
                else next_uris[0]
                if next_uris
                else ""
            ) or ""
            result["next_track_id"] = (
                next_uri.removeprefix("spotify:track:") if next_uri.startswith("spotify:track:") else None
            )
            result["native_context_uri"] = state.get("context_uri")
            result["device"] = {
                "id": self.device_id,
                "name": "tspotify",
                "volume_percent": state.get("volume_percent", self.preferred_volume),
            }
            return result
        changed = bool(self.event and (self._base.get("item") or {}).get("id") != self.event.get("track_id"))
        if time.monotonic() - self._snapshot_time > (0.1 if changed else 5):
            try:
                self._base = self.request({"Get": {"Key": "Playback"}}, timeout=0.7) or {}
                self._snapshot_time = time.monotonic()
            except (OSError, TimeoutError):
                pass
        result = dict(self._base or fallback)
        # A recently observed Connect selection wins over an older local event/cache.
        # Observation must never make us send the previous track back to Spotify.
        if fallback.get("_observed_at", 0) > self.event.get("at", 0):
            observed = dict(fallback)
            if observed.get("is_playing"):
                elapsed = max(
                    0, time.monotonic() - observed.get("_observed_progress_at", observed["_observed_at"])
                )
                observed["progress_ms"] = (
                    observed.get("_observed_progress_ms", observed.get("progress_ms", 0)) + elapsed * 1000
                )
            return observed
        if self.event and (fallback.get("item") or {}).get("id") == self.event.get("track_id"):
            base_item = self._base.get("item") or {}
            if base_item.get("id") != self.event.get("track_id") or not base_item.get("album"):
                result = dict(fallback)
        if self.event and (result.get("item") or {}).get("id") != self.event.get("track_id"):
            result["item"] = None
            result["_pending_track_id"] = self.event["track_id"]
        if self.event:
            elapsed = time.monotonic() - self.event["at"] if self.event["playing"] else 0
            result.update(
                is_playing=self.event["playing"], progress_ms=self.event["position"] + elapsed * 1000
            )
        if time.monotonic() - self._volume_set_at < 7:
            result["device"] = {**(result.get("device") or {}), "volume_percent": self.preferred_volume}
        return result

    def restart(self):
        self.close()
        self.stopped.clear()
        self.authorization_error = None
        self.authorizing.clear()
        self.event = {}
        self._base = {}
        self.failure = None
        self.device_id = None
        self.process = None
        self.pty = None
        self.start()
        return True

    def unmute_after_user_volume(self, volume):
        if platform.system() != "Linux" or not shutil.which("pactl"):
            return
        try:
            entries = json.loads(
                subprocess.check_output(
                    ["pactl", "--format=json", "list", "sink-inputs"], timeout=3, stderr=subprocess.DEVNULL
                )
            )
            for entry in entries:
                props = entry.get("properties", {})
                is_engine = (
                    props.get("application.process.binary", "").rsplit("/", 1)[-1] == "spotify_player"
                    or props.get("node.name") == "alsa_playback.spotify_player"
                    or props.get("application.name") == "PipeWire ALSA [spotify_player]"
                )
                if is_engine:
                    subprocess.run(
                        ["pactl", "set-sink-input-volume", str(entry["index"]), "100%"],
                        timeout=3,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    subprocess.run(
                        ["pactl", "set-sink-input-mute", str(entry["index"]), "0" if volume else "1"],
                        timeout=3,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
        except (OSError, ValueError, subprocess.SubprocessError):
            pass

    def close(self):
        self.stopped.set()
        if self.pty:
            try:
                self.pty.close(force=True)
            finally:
                if self.job:
                    self.job.close()
                    self.job = None
        if self.process and self.process.poll() is None:
            try:
                os.killpg(self.process.pid, signal.SIGTERM)
                self.process.wait(timeout=4)
            except (OSError, subprocess.TimeoutExpired):
                self.process.kill()
                self.process.wait(timeout=2)
        if self.master is not None:
            try:
                os.close(self.master)
            except OSError:
                pass
            self.master = None
        if self.reader_thread and self.reader_thread is not threading.current_thread():
            self.reader_thread.join(timeout=2)
