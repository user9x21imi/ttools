"""Change only this terminal's title when playback metadata changes."""

import os
import shutil
import subprocess
import sys
import unicodedata


def playback_title(playback):
    item = playback.get("item") or {}
    name = item.get("name", "")
    artist = ", ".join(a.get("name", "") for a in item.get("artists", []))
    title = "tspotify"
    if name:
        title += " · " + (artist + " — " if artist else "") + name
        if playback.get("is_loading"):
            title += " · загрузка"
        elif not playback.get("is_playing"):
            title += " · пауза"
    # Metadata is untrusted terminal input: exclude OSC terminators and controls.
    return " ".join("".join(" " if unicodedata.category(c).startswith("C") else c for c in title).split())[
        :240
    ]


class TerminalTitle:
    def __init__(self):
        self.stream = sys.stdout
        self.active = self.stream.isatty()
        self.last = None
        self.konsole_format = None
        if not self.active:
            return
        service, session = os.environ.get("KONSOLE_DBUS_SERVICE"), os.environ.get("KONSOLE_DBUS_SESSION")
        binary = shutil.which("qdbus6") or shutil.which("qdbus")
        if service and session and binary:
            try:
                result = subprocess.run(
                    [binary, service, session, "org.kde.konsole.Session.tabTitleFormat", "0"],
                    capture_output=True,
                    text=True,
                    timeout=0.4,
                )
                if result.returncode == 0:
                    self.konsole_format = result.stdout.rstrip("\n")
            except (OSError, subprocess.TimeoutExpired):
                pass
        self.stream.write("\x1b[22;0t")  # Save the previous window/icon title where supported.
        if self.konsole_format is not None:
            self.stream.write("\x1b]30;%w\x07")  # Konsole tabs must display the supplied window title.
        self.stream.flush()

    def update(self, playback):
        title = playback_title(playback)
        if self.active and title != self.last:
            self.stream.write("\x1b]0;" + title + "\x07")
            self.stream.flush()
            self.last = title

    def close(self):
        if self.active:
            if self.konsole_format is not None:
                self.stream.write("\x1b]30;" + self.konsole_format + "\x07")
            self.stream.write("\x1b[23;0t")
            self.stream.flush()
            self.active = False
