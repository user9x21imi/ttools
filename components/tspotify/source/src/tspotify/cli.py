"""Portable entry point, first-run login and lifecycle ownership."""

import argparse
import contextlib
import locale
import json
import os
import platform
import shutil
import signal
import sys
import time
import webbrowser
from urllib.parse import urlsplit
import httpx

from . import __version__, auth, paths
from .api import Spotify, SpotifyError
from .backend import Backend, engine_path


@contextlib.contextmanager
def single_instance():
    path = paths.DATA / "client.lock"
    stream = path.open("a+b")
    try:
        if os.name == "nt":
            import msvcrt

            stream.seek(0)
            stream.write(b"0")
            stream.flush()
            stream.seek(0)
            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                raise RuntimeError("tspotify уже открыт. Вернитесь в существующее окно.") from None
        else:
            import fcntl

            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                raise RuntimeError("tspotify уже открыт. Вернитесь в существующее окно.") from None
        yield
    finally:
        stream.close()


def engine_authorize(url, qr=False, ready=None, *, quiet=False, status=None):
    if not quiet:
        print("\nSpotify просит отдельно разрешить встроенное воспроизведение.", flush=True)
    if qr:
        import httpx
        import qrcode

        image = qrcode.QRCode(border=2)
        image.add_data(url)
        image.make(fit=True)
        image.print_ascii(invert=True)
        pasted = input(
            "Вставьте адрес возврата с телефона, или Enter после входа в браузере компьютера: "
        ).strip()
        if not pasted or (ready and ready()):
            return
        parsed = urlsplit(pasted)
        if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or parsed.port != 8989:
            raise ValueError("Ожидается адрес возврата http://127.0.0.1:8989/…")
        httpx.get(pasted, timeout=5)
    else:
        if status:
            status("Откройте окно авторизации Spotify в браузере")
        if not quiet:
            print("Если браузер не открылся, перейдите по этой ссылке:\n" + url, flush=True)
        webbrowser.open(url, new=2)


def doctor():
    print("+-- tspotify doctor -----------------------------------------+")
    print("Version:", __version__)
    print("OS:", platform.system(), platform.machine())
    print("Python:", platform.python_version())
    print("Terminal:", os.environ.get("TERM", "Windows console"))
    print("Encoding:", sys.stdout.encoding)
    print("Engine:", engine_path(install=False) or "not installed; first launch downloads it")
    print("Data:", paths.DATA)
    print("Config:", paths.CONFIG)
    print("Login:", "saved" if paths.TOKEN_FILE.exists() else "required")
    print(
        "Spectrum:",
        "Spotify-only PulseAudio/PipeWire stream"
        if platform.system() == "Linux" and shutil.which("parec")
        else "dedicated Spotify channel: TSPOTIFY_SPOTIFY_LOOPBACK",
    )
    print("Fonts: use your normal monospace font; --ascii disables Unicode artwork.")


def parser():
    value = argparse.ArgumentParser(prog="tspotify", description="Spotify in your terminal, drawn with dots.")
    value.add_argument("--version", action="version", version="tspotify " + __version__)
    value.add_argument("--demo", action="store_true", help="offline UI preview without account or audio")
    value.add_argument("--qr", action="store_true", help="use QR/manual callback for first-run sign-in")
    value.add_argument("--ascii", action="store_true", help="portable ASCII artwork and borders")
    value.add_argument("--no-splash", action="store_true", help="skip the startup system-info screen")
    value.add_argument("--no-motion", action="store_true", help="disable startup and interface transitions")
    value.add_argument("--low-power", action="store_true", help="reduce UI refresh rate and skip transitions")
    value.add_argument("--muted", action="store_true", help="start the integrated engine at zero volume")
    value.add_argument(
        "--device", default="auto", help="auto, integrated, or a Spotify Connect device name/ID"
    )
    sub = value.add_subparsers(dest="command")
    login_parser = sub.add_parser("login", help="authorize Spotify in a browser or via QR")
    login_parser.add_argument(
        "--qr", dest="login_qr", action="store_true", help="show QR; paste the callback URL from your phone"
    )
    shortcuts_parser = sub.add_parser(
        "install-shortcuts", help="enable KDE F7-F12 controls while the client runs"
    )
    shortcuts_parser.add_argument("--remove", action="store_true", help="disable desktop shortcuts")
    control_parser = sub.add_parser(
        "control", help="control the running client without focusing its terminal"
    )
    control_parser.add_argument(
        "action", choices=("previous", "play-pause", "next", "mute", "volume-down", "volume-up")
    )
    stop_parser = sub.add_parser("stop", help="save session, exit normally and wait for the owned engine")
    stop_parser.add_argument("--timeout", type=float, default=15)
    sub.add_parser("verify-runtime", help="headless dependency check without OAuth, network or audio")
    sub.add_parser("status", help="report running instance status without exposing control credentials")
    sub.add_parser("update", help="check and install a release update after confirmation")
    sub.add_parser("doctor", help="show diagnostics without printing tokens")
    sub.add_parser("devices", help="list available Spotify Connect devices")
    sub.add_parser("install-engine", help="download and verify the pinned streaming engine")
    return value


def run(args):
    paths.prepare()
    if args.command == "stop":
        from .control import stop_client

        print(json.dumps(stop_client(timeout=max(0.1, args.timeout))))
        return
    if args.command == "status":
        from .control import send

        try:
            print(json.dumps({"running": True, **send("status")}))
        except RuntimeError:
            print(json.dumps({"running": False}))
        return
    if args.command == "verify-runtime":
        import curses
        import numpy
        import PIL
        import qrcode

        print(
            json.dumps(
                {
                    "ok": True,
                    "version": __version__,
                    "platform": platform.system(),
                    "numpy": numpy.__version__,
                    "pillow": PIL.__version__,
                    "curses": bool(curses),
                    "qrcode": bool(qrcode),
                }
            )
        )
        return
    if args.command == "install-shortcuts":
        from .shortcuts import install

        install(remove=args.remove)
        print(
            "Системные сочетания отключены."
            if args.remove
            else "F7–F12 будут работать глобально при следующем запуске tspotify."
        )
        return
    if args.command == "control":
        from .control import send

        send(args.action)
        return
    if args.command == "update":
        from .updates import offer

        offer(force=True)
        return
    if args.demo:
        from .demo import run as demo_run

        demo_run(args)
        return
    if args.command == "doctor":
        doctor()
        return
    if args.command == "install-engine":
        print(engine_path())
        return
    if args.command == "login":
        auth.login(qr=args.qr or args.login_qr)
        return
    if args.command is None:
        from .updates import offer

        if offer():
            return
    try:
        auth.access_token()
    except auth.LoginRequired:
        auth.login(qr=args.qr)
    api = Spotify()
    api.session_muted = args.muted
    backend = None
    try:
        if args.command == "devices":
            for device in api.devices():
                print(("* " if device.get("is_active") else "  ") + device["name"] + "  " + device["id"])
            return
        with single_instance():
            try:
                selected = api.select_device(args.device)
            except (SpotifyError, OSError):
                if args.device not in ("auto", "integrated"):
                    raise
                selected = None
            if selected:
                print("Spotify Connect:", selected["name"], flush=True)

            show_startup = not args.no_splash and not args.qr
            startup_status = ["Загружаем клиент Spotify…"]

            def update_startup_status(message):
                startup_status[0] = message

            def create_backend():
                return Backend(
                    muted=args.muted,
                    on_authorize=lambda url: engine_authorize(
                        url,
                        qr=args.qr,
                        ready=lambda: api.backend.ready(),
                        quiet=show_startup,
                        status=update_startup_status,
                    ),
                )

            if args.device == "auto":
                api.backend_factory = create_backend
            if not api.external:
                backend = Backend(
                    muted=args.muted,
                    on_authorize=lambda url: engine_authorize(
                        url,
                        qr=args.qr,
                        ready=lambda: backend.ready(),
                        quiet=show_startup,
                        status=update_startup_status,
                    ),
                )
                api.backend = backend

            def start_spotify():
                if backend:
                    if not show_startup:
                        print("Подключаю Spotify. Первый запуск может занять несколько секунд…", flush=True)
                    backend.start(quiet=show_startup)
                    # Start silent, pause locally, then restore the preference while paused.
                    # The boot mute is not the user's saved volume.
                    if not getattr(backend, "local_enabled", False):
                        try:
                            if getattr(backend, "device_id", None):
                                api.request("PUT", "me/player/pause?" + api.device_query())
                        except SpotifyError:
                            pass
                api._restore_gate = time.monotonic()
            # Import curses only for the UI: doctor, installation and OAuth work without a TTY.
            # On Windows use the direct-VT backend so the terminal background
            # (including transparency/acrylic) remains visible.
            from . import _vt
            curses = _vt.select()
            from . import ui

            ui.API = api
            ui.ASCII_ONLY = args.ascii
            ui.NO_SPLASH = not show_startup
            ui.NO_MOTION = args.no_motion or os.environ.get("TSPOTIFY_REDUCED_MOTION", "").lower() in (
                "1",
                "true",
                "yes",
            )
            ui.LOW_POWER = args.low_power or os.environ.get("TSPOTIFY_LOW_POWER", "").lower() in (
                "1",
                "true",
                "yes",
            )
            if show_startup:
                startup_error = []

                def launch(screen):
                    error = ui.startup_screen(
                        screen,
                        start_spotify,
                        status=lambda: startup_status[0],
                        cancel=backend.close if backend else None,
                    )
                    if error:
                        startup_error.append(error)
                        return
                    ui.NO_SPLASH = True
                    ui.App(screen).run()

                curses.wrapper(launch)
                if startup_error:
                    raise startup_error[0]
            else:
                start_spotify()
                curses.wrapper(lambda screen: ui.App(screen).run())
    finally:
        # Stop our own stream even when an exception or Ctrl+C closes the interface.
        # An already-running desktop Spotify is a separate, user-owned device.
        owned_backend = getattr(api, "backend", None) or backend
        if owned_backend:
            owned_backend.close()
        api.close()


def main(argv=None):
    os.umask(0o077)
    candidates = (".UTF-8", "", "C") if os.name == "nt" else ("", "C.UTF-8", "en_US.UTF-8", "C")
    for candidate in candidates:
        try:
            locale.setlocale(locale.LC_ALL, candidate)
            break
        except locale.Error:
            continue
    if os.name == "nt":
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="replace")
    args = parser().parse_args(argv)
    previous = {}

    def interrupted(signum, frame):
        raise KeyboardInterrupt

    for name in ("SIGTERM", "SIGHUP"):
        if hasattr(signal, name):
            sig = getattr(signal, name)
            previous[sig] = signal.signal(sig, interrupted)
    try:
        if args.command is None:
            from .managed import runtime_lock

            with runtime_lock():
                run(args)
        else:
            run(args)
    except KeyboardInterrupt:
        print("\ntspotify закрыт.")
    except (RuntimeError, OSError, ValueError, httpx.HTTPError) as error:
        print("\ntspotify: " + str(error), file=sys.stderr)
        print("Диагностика: tspotify doctor", file=sys.stderr)
        raise SystemExit(1) from None
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
