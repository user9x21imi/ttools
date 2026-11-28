import json
import os
from pathlib import Path
import select
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import wave

from tsound.audio import Playback
from tsound.demo import Demo
from tsound.service import Comment, SoundCloud, unique
from tsound.ui import App, configure_escape_delay
from tsound.visual import Timeline, column, decoded_waveform, peaks


class WindowsCursesCompatibilityTest(unittest.TestCase):
    class FakeError(Exception):
        pass

    def test_missing_set_escdelay_is_tolerated(self):
        fake = type("PDCurses", (), {"error": self.FakeError})()
        self.assertIsNone(configure_escape_delay(fake))

    def test_supported_set_escdelay_is_used(self):
        calls = []
        fake = type("Ncurses", (), {"error": self.FakeError,
                                    "set_escdelay": calls.append})()
        configure_escape_delay(fake)
        self.assertEqual(calls, [35])

    def test_escdelay_errors_are_ignored(self):
        def fail(value):
            raise self.FakeError(value)
        fake = type("Curses", (), {"error": self.FakeError,
                                   "set_escdelay": staticmethod(fail)})()
        self.assertIsNone(configure_escape_delay(fake))


class TimelineTest(unittest.TestCase):
    def test_crossing_pause_and_seek(self):
        timeline = Timeline()
        timeline.set_comments([Comment(2, "a", "one"), Comment(8, "b", "two")])
        self.assertFalse(timeline.advance(2.1, False, 0))
        self.assertEqual(timeline.advance(2.1, True, 1)[0].body, "one")
        self.assertEqual(timeline.advance(2.5, False, 2)[0].body, "one")
        timeline.reset(7)
        self.assertFalse(timeline.advance(7, True, 2))
        self.assertEqual(timeline.advance(8, True, 3)[0].body, "two")
        self.assertFalse(timeline.advance(8.5, True, 8))

    def test_full_duration_and_stable_append(self):
        tracks = Demo().tracks
        self.assertEqual(unique(tracks + tracks[:1]), tracks)
        first, second = peaks([0, .8, .2, .4], 2)
        self.assertGreater(first, second)
        self.assertLess(first, .8)
        self.assertEqual([column(x, 100, 21) for x in (0, 50, 100)], [0, 10, 20])

    def test_playlist_filter_preserves_queue(self):
        demo = Demo()
        app = App(None, demo, demo=True)
        try:
            app.context = demo.playlists[0]
            app.context_items = demo.tracks
            app.begin_search()
            app.query = "Soft"
            app.activate(0)
            self.assertEqual(app.track, demo.tracks[1])
            app.step(1)
            self.assertEqual(app.track, demo.tracks[2])
        finally:
            for pool in app.pools.values():
                pool.shutdown(wait=True, cancel_futures=True)


class QueueModesTest(unittest.TestCase):
    def test_shuffle_keeps_current_track_and_repeat_changes_automatic_next(self):
        from unittest.mock import patch

        demo = Demo()
        app = App(None, demo, demo=True)
        try:
            with patch("tsound.ui.random.shuffle", side_effect=lambda tail: tail.reverse()):
                app.toggle_shuffle()
            self.assertEqual(app.track, demo.tracks[0])
            self.assertEqual(app.queue[app.queue_index_at(1)], demo.tracks[-1])
            app.toggle_shuffle()
            self.assertEqual(app.queue, demo.tracks)
            app.cycle_repeat()
            self.assertEqual(app.queue_index_at(-1), len(demo.tracks) - 1)
            app.cycle_repeat()
            self.assertEqual(app.queue_index_at(1, automatic=True), app.queue_index)
            self.assertEqual(app.queue_index_at(1), 1)
        finally:
            for pool in app.pools.values():
                pool.shutdown(wait=True, cancel_futures=True)


class ExpandedPlayerLayoutTest(unittest.TestCase):
    def test_wide_window_uses_left_art_and_right_wave_and_spectrum(self):
        from unittest.mock import Mock, patch

        demo = Demo()
        screen = Mock()
        screen.getmaxyx.return_value = (36, 130)
        app = App(screen, demo, demo=True)
        app.full = True
        app.active_comments = []
        try:
            with (patch.object(app, "color", return_value=0),
                  patch.object(app, "put", side_effect=lambda y, x, label, *args: len(label)) as put,
                  patch.object(app, "cover") as cover,
                  patch.object(app, "render_spectrum") as spectrum):
                app.draw()
            _, art_y, art_x, art_width, art_height = cover.call_args.args
            wave_x, _, wave_top, wave_bottom = app.wave_hit
            self.assertEqual(art_x, 2)
            self.assertEqual(art_y, 4)
            self.assertEqual(art_height, 29)
            self.assertTrue(cover.call_args.kwargs["crop"])
            self.assertGreater(wave_x, art_x + art_width)
            self.assertLessEqual(art_y, wave_top)
            next_row = next(call.args[0] for call in put.call_args_list if call.args[2].startswith("Далее: "))
            self.assertGreater(next_row, wave_bottom)
            self.assertEqual(spectrum.call_args.kwargs["x"], wave_x)
            self.assertGreater(spectrum.call_args.args[0], next_row)
            self.assertEqual(spectrum.call_args.args[0] + spectrum.call_args.args[2],
                             art_y + art_height)
        finally:
            for pool in app.pools.values():
                pool.shutdown(wait=True, cancel_futures=True)


class TrackPresentationTest(unittest.TestCase):
    def test_web_comments_use_numeric_track_id_and_follow_pages(self):
        from unittest.mock import patch

        from tsound.service import Entry
        from tsound.web_service import WebSoundCloud

        next_page = "https://api-v2.soundcloud.com/tracks/123/comments?offset=20"
        pages = [
            {"collection": [{"timestamp": 5100, "body": "one", "user": {"username": "listener"}}],
             "next_href": next_page},
            {"collection": [{"timestamp": 24500, "body": "two"}]},
        ]
        track = Entry("track", "soundcloud:tracks:123", "Test")
        with patch("tsound.web_service.browser_profile", return_value=([], None)):
            service = WebSoundCloud(SoundCloud())
        with patch.object(service, "get", side_effect=pages) as get:
            self.assertEqual(service.comments(track),
                             [Comment(5.1, "listener", "one"), Comment(24.5, "", "two")])
        self.assertEqual(get.call_args_list[0].args, ("/tracks/123/comments",))
        self.assertEqual(get.call_args_list[1].args, (next_page,))

    def test_stream_reuses_library_metadata_and_recovers_from_transcoding_timeout(self):
        from unittest.mock import patch

        from tsound.service import Entry, NetworkError
        from tsound.web_service import WebSoundCloud

        root = "https://api-v2.soundcloud.com/media/"
        item = {"id": 12, "media": {"transcodings": [
            {"url": root + "audio-1", "format": {"protocol": "progressive"}},
            {"url": root + "audio-2", "format": {"protocol": "hls"}},
        ]}}
        with patch("tsound.web_service.browser_profile", return_value=([], None)):
            service = WebSoundCloud(SoundCloud())
        service.remember_tracks({"collection": [{"track": item}]})
        with patch.object(service, "api_request", side_effect=[
                NetworkError("timeout"), {"url": "https://audio.example/stream"},
        ]) as api:
            stream = service.stream(Entry("track", "soundcloud:tracks:12", "Test"))
        self.assertEqual(stream, ("https://audio.example/stream", False))
        self.assertEqual([call.args[0] for call in api.call_args_list],
                         [root + "audio-1", root + "audio-2"])

    def test_favorites_first_page_arrives_before_later_timeout(self):
        from unittest.mock import Mock, patch

        from tsound.service import NetworkError
        from tsound.web_service import WebSoundCloud

        with patch("tsound.web_service.browser_profile", return_value=([], None)):
            service = WebSoundCloud(SoundCloud())
        service.account = {"id": 100}
        page = {"collection": [{"track": {"id": 12, "title": "Favorite"}}],
                "next_href": "https://api-v2.soundcloud.com/users/100/track_likes?offset=40"}
        partial = Mock()
        with patch.object(service, "get", side_effect=[page, NetworkError("timeout")]):
            with self.assertRaises(NetworkError):
                service.favorites(partial)
        self.assertEqual(partial.call_args.args[0][0].title, "Favorite")

    @unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg")
    def test_png_waveform_preserves_shape(self):
        from tsound.visual import png_waveform

        width, height = 40, 24
        data = bytes(
            255 if abs(y - height // 2) < (3 if x < width // 2 else 8) else 0
            for y in range(height) for x in range(width)
        )
        source = f"P5\n{width} {height}\n255\n".encode() + data
        png = subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "image2pipe", "-vcodec",
                              "pgm", "-i", "pipe:0", "-frames:v", "1", "-f", "image2pipe",
                              "-vcodec", "png", "pipe:1"], input=source, capture_output=True,
                             check=True, timeout=5).stdout
        amplitudes = png_waveform(png)
        self.assertEqual(len(amplitudes), 1024)
        self.assertGreater(amplitudes[768], amplitudes[256] * 1.5)


class BrowserLoginTest(unittest.TestCase):
    def test_browser_redirect_returns_to_client(self):
        from io import BytesIO
        from threading import Event
        from unittest.mock import Mock, patch
        from urllib.parse import parse_qs, urlencode, urlsplit

        redirect = "http://127.0.0.1:18979/callback"
        service = SoundCloud()
        service.client_id, service.secret = "test-id", "test-secret"
        listener = Mock()
        listener.__enter__ = Mock(return_value=listener)
        listener.__exit__ = Mock(return_value=False)

        def browser(address):
            oauth = parse_qs(urlsplit(address).query)
            self.assertEqual(oauth["redirect_uri"], [redirect])
            self.assertEqual(oauth["code_challenge_method"], ["S256"])
            handler_class = server.call_args.args[1]
            handler = handler_class.__new__(handler_class)
            handler.headers = {"Host": "127.0.0.1:18979"}
            handler.send_response = Mock()
            handler.send_header = Mock()
            handler.end_headers = Mock()
            handler.wfile = BytesIO()
            handler.path = "/callback?state=wrong&code=test-code"
            handler.do_GET()
            handler.send_response.assert_called_once_with(404)
            params = urlencode({"state": oauth["state"][0], "code": "test-code"})
            handler.path = f"/callback?{params}"
            handler.do_GET()
            handler.send_response.assert_called_with(200)
            self.assertIn("Вернитесь", handler.wfile.getvalue().decode())
            return True

        with (patch("tsound.service.ThreadingHTTPServer", return_value=listener) as server,
              patch("tsound.service.webbrowser.open", side_effect=browser),
              patch.object(service, "exchange") as exchange):
            service.browser_login(Event(), redirect)
        server.assert_called_once()
        self.assertEqual(server.call_args.args[0], ("127.0.0.1", 18979))
        self.assertEqual(exchange.call_count, 1)
        self.assertEqual(exchange.call_args.kwargs["code"], "test-code")
        self.assertEqual(exchange.call_args.kwargs["redirect_uri"], redirect)


class WebSessionTest(unittest.TestCase):
    def test_zen_opens_new_window_in_normal_profile(self):
        from unittest.mock import patch

        from tsound.web_session import open_default_browser

        with (patch("tsound.web_session.shutil.which", side_effect=lambda name: f"/usr/bin/{name}"),
              patch("tsound.web_session.subprocess.run") as query,
              patch("tsound.web_session.subprocess.Popen") as launch):
            query.return_value.returncode = 0
            query.return_value.stdout = "app.zen_browser.zen.desktop\n"
            launch.return_value.wait.return_value = 0
            self.assertTrue(open_default_browser())
        self.assertEqual(launch.call_args.args[0], [
            "/usr/bin/flatpak", "run", "--command=launch-script.sh", "app.zen_browser.zen",
            "--new-window", "https://soundcloud.com/signin",
        ])

    def test_zen_launch_failure_tries_desktop_handler(self):
        from unittest.mock import patch

        from tsound.web_session import open_default_browser

        with (patch("tsound.web_session.shutil.which", side_effect=lambda name: f"/usr/bin/{name}"),
              patch("tsound.web_session.subprocess.run") as run,
              patch("tsound.web_session.subprocess.Popen") as launch):
            run.return_value.returncode = 0
            run.return_value.stdout = "app.zen_browser.zen.desktop"
            launch.return_value.wait.return_value = 1
            self.assertTrue(open_default_browser())
        self.assertEqual(run.call_args.args[0], [
            "/usr/bin/kioclient", "exec", "https://soundcloud.com/signin",
        ])

    def test_default_session_skips_launch_if_already_signed_in(self):
        from threading import Event
        from unittest.mock import patch

        from tsound.web_service import WebSoundCloud

        with (tempfile.TemporaryDirectory() as temp,
              patch.dict(os.environ, {"TSOUND_HOME": temp}),
              patch("tsound.web_service.browser_profile", return_value=([], None)),
              patch("tsound.web_service.web_client_id", return_value="test-web-id"),
              patch("tsound.web_service.request", return_value={"id": 123}),
              patch("tsound.web_service.open_default_browser") as launch):
            # Use a real absolute path: a POSIX "/tmp/..." string is not absolute on Windows.
            profile = Path(temp)/"test-zen-profile"
            with (patch("tsound.web_service.default_profile", return_value=profile),
                  patch("tsound.web_service.session_token", side_effect=lambda target: "test" if target == profile else None)):
                service = WebSoundCloud(SoundCloud())
                self.assertFalse(service.signed_in)
                service.default_browser_login(Event())
                self.assertEqual(service.account_id(), "123")
                launch.assert_not_called()
                saved = json.loads((Path(temp) / "web-login.json").read_text(encoding="utf-8"))
                self.assertEqual(saved["profile"], str(profile))
                self.assertNotIn('token', saved)
                restarted = WebSoundCloud(SoundCloud())
                self.assertTrue(restarted.signed_in)
                self.assertEqual(restarted.account_id(), "123")
                app = App(None, restarted)
                try:
                    self.assertFalse(app.login)
                finally:
                    for pool in app.pools.values():
                        pool.shutdown(wait=True, cancel_futures=True)
                launch.assert_not_called()

    def test_read_session_while_browser_holds_exclusive_lock(self):
        import sqlite3
        from contextlib import closing

        from tsound.web_session import session_token

        with tempfile.TemporaryDirectory() as directory:
            profile = Path(directory)
            with closing(sqlite3.connect(profile / "cookies.sqlite")) as browser:
                browser.execute("CREATE TABLE moz_cookies (host, name, value, expiry, lastAccessed)")
                browser.execute("INSERT INTO moz_cookies VALUES (?, ?, ?, 0, 0)",
                                (".soundcloud.com", "oauth_token", "fixture"))
                browser.commit()
                browser.execute("BEGIN EXCLUSIVE")
                self.assertEqual(session_token(profile), "fixture")

    def test_separate_browser_signin_verifies_account(self):
        import sqlite3
        from contextlib import closing
        from threading import Event
        from unittest.mock import Mock, patch

        from tsound.web_service import WebSoundCloud
        from tsound.web_session import session_token

        with tempfile.TemporaryDirectory() as temp:
            profile = Path(temp) / "isolated"
            profile.mkdir()
            database = profile / "cookies.sqlite"
            with closing(sqlite3.connect(database)) as conn, conn:
                conn.execute("CREATE TABLE moz_cookies (host, name, value, expiry, lastAccessed)")
                conn.execute("INSERT INTO moz_cookies VALUES (?, ?, ?, 0, 0)",
                             ("example.com", "oauth_token", "unrelated"))
            self.assertIsNone(session_token(profile))

            def browser(command, target):
                self.assertEqual(command, ["firefox"])
                self.assertEqual(target, profile)
                with closing(sqlite3.connect(database)) as conn, conn:
                    conn.execute("INSERT INTO moz_cookies VALUES (?, ?, ?, 0, 0)",
                                 (".soundcloud.com", "oauth_token", "test-session"))
                return Mock(poll=Mock(return_value=None))

            with (patch.dict(os.environ, {"TSOUND_HOME": temp}),
                  patch("tsound.web_service.browser_profile", return_value=(["firefox"], profile)),
                  patch("tsound.web_service.start_browser", side_effect=browser),
                  patch("tsound.web_service.web_client_id", return_value="test-web-id"),
                  patch("tsound.web_service.request", return_value={"id": 123}) as request):
                service = WebSoundCloud(SoundCloud())
                self.assertFalse(service.signed_in)
                service.browser_login(Event())
                self.assertTrue(service.signed_in)
                self.assertEqual(service.account_id(), "123")
                request.assert_called_once_with(
                    "https://api-v2.soundcloud.com/me?client_id=test-web-id",
                    token="test-session", method=None)


@unittest.skipUnless(sys.platform.startswith("linux") and shutil.which("ffmpeg"), "Linux with FFmpeg")
class AudioTest(unittest.TestCase):
    def test_silent_pcm_play_pause_and_end(self):
        from array import array
        from math import pi, sin
        from threading import Event
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {"SDL_AUDIODRIVER": "dummy"}):
            source = Path(temp) / "sine.wav"
            with wave.open(str(source), "wb") as stream:
                stream.setparams((1, 2, 48000, 0, "NONE", ""))
                stream.writeframes(array("h", (int(8000 * sin(i * pi / 60)) for i in range(48000))).tobytes())
            self.assertGreater(len(decoded_waveform(str(source), 1, Event())), 900)
            player = Playback(str(source), .15, True, .2)
            try:
                deadline = time.monotonic() + 4
                while player.label != "Пауза" and time.monotonic() < deadline:
                    time.sleep(.02)
                self.assertEqual(player.label, "Пауза")
                self.assertAlmostEqual(player.position, .15, places=2)
                player.paused = False
                player.thread.join(timeout=4)
                self.assertTrue(player.ended, player.label)
                self.assertAlmostEqual(player.position, 1, places=2)
                self.assertGreater(max(player.levels), 0)
            finally:
                player.close()
                player.thread.join(timeout=2)


@unittest.skipUnless(os.name == "posix", "POSIX PTY")
class TerminalTest(unittest.TestCase):
    def test_demo_search_and_comment(self):
        import fcntl
        import pty
        import struct
        import termios

        master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 48, 115, 0, 0))
        env = dict(os.environ, TERM="xterm-256color", LC_ALL="C.UTF-8")
        child = subprocess.Popen([sys.executable, "-m", "tsound", "--demo", "--ascii"],
                                 stdin=slave, stdout=slave, stderr=slave, env=env)
        os.close(slave)

        def see(needle, timeout=4):
            data = b""
            expected = needle.encode()
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                if select.select([master], [], [], .1)[0]:
                    try:
                        data += os.read(master, 65536)
                    except OSError:
                        break
                    if expected in data:
                        return
            self.fail(f"Terminal did not show {needle!r}. Tail: {data[-400:]!r}")

        try:
            see("SoundCloud Terminal")
            see("Neon Afterimage")
            os.write(master, b"\x1b[23~\x0c")
            see("[60%]")
            os.write(master, b"\x1b[24~\x0c")
            see("[65%]")
            os.write(master, b"\x1b[21~\x0c")
            see("[Muted]")
            os.write(master, b"\x1b[21~\x0c")
            see("[65%]")
            os.write(master, b"\x1b[19~")
            see("@ari")
            os.write(master, b"\x1b[19~\x1bOR\x0c")
            see("[F3 Свернуть]")
            os.write(master, b"\x0c")
            see("[Играть]")
            os.write(master, b"\x0c")
            see("[F В избранном]")
            os.write(master, b"f\x0c")
            see("[F В избранное]")
            os.write(master, b"\x1b[<35;37;28M\x0c")
            see("@mira")
            os.write(master, b"\x1b[<35;2;2M\x0c")
            see("0:02 / 1:47")
            os.write(master, b"\x1b[<0;21;28M\x1b[<32;43;28M\x1b[<0;43;28m\x0c")
            see("0:38 / 1:47")
            os.write(master, b"\x0c")
            see("Далее: Soft Circuit")
            os.write(master, b"\x1b[20~\x0c")
            see("Далее: Night Relay")
            os.write(master, b"\x1b[18~\x0c")
            see("Далее: Soft Circuit")
            os.write(master, b"\x1bOS\x0c")
            see("[F4 Плеер]")
            os.write(master, b"6\x0c")
            see("Quiet Machines")
            os.write(master, b"\r")
            see("Soft Circuit")
            os.write(master, b"/Soft\x0c")
            see("Список")
            os.write(master, b"\t\r\x0c")
            see("Soft Circuit")
            os.write(master, b"\x1bOS\x0c")
            see("[F4 Библиотека]")
            os.write(master, b"\x11")
            self.assertEqual(child.wait(timeout=3), 0)
        finally:
            if child.poll() is None:
                child.kill()
                child.wait()
            os.close(master)


if __name__ == "__main__":
    unittest.main()
