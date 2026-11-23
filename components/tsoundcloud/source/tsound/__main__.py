import argparse
import curses
import locale
import sys
from threading import Event

from .demo import Demo
from .service import SoundCloud
from .ui import App
from .web_service import WebSoundCloud


def main():
    locale.setlocale(locale.LC_ALL, "")
    parser = argparse.ArgumentParser(prog="tsoundcloud")
    parser.add_argument("command", choices=("run", "login"), nargs="?", default="run")
    parser.add_argument("--demo", action="store_true", help="offline, silent UI preview")
    parser.add_argument("--no-splash", action="store_true", help="skip the startup logo")
    parser.add_argument("--ascii", action="store_true", help="ASCII frames, artwork and waveform")
    parser.add_argument("--separate-profile", action="store_true", help="connect the web library in a separate browser profile")
    parser.add_argument("--redirect-uri", help="registered OAuth callback URL")
    parser.add_argument("--version", action="version", version="tsound 0.1.0")
    args = parser.parse_args()
    service = Demo() if args.demo else SoundCloud()
    if not args.demo:
        configured = service.client_id and service.secret
        if not (args.redirect_uri or service.external_token or configured):
            service = WebSoundCloud(service)
    if args.command == "login":
        if args.demo:
            parser.error("login is unavailable in demo mode")
        cancelled = Event()
        try:
            if isinstance(service, WebSoundCloud) and not args.separate_profile:
                service.default_browser_login(cancelled, lambda opened: print(
                    "Войдите в браузере." if opened else
                    "Откройте https://soundcloud.com/signin в обычном браузере. Ожидаю вход…", flush=True))
            else:
                service.browser_login(cancelled, args.redirect_uri)
        except KeyboardInterrupt:
            cancelled.set()
            return 130
        except (OSError, RuntimeError, ValueError) as error:
            print(error, file=sys.stderr)
            return 1
        print("Вход выполнен.")
    else:
        splash = not args.no_splash
        curses.wrapper(lambda screen: App(screen, service, args.demo, args.ascii, splash).run())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
