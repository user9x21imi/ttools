import math
import time

from .service import Comment, Entry


class Demo:
    def __init__(self):
        self.tracks = [Entry("track", str(index), title, artist, artist.lower(), 107 + 32 * index,
                             f"demo:{index}", "After Hours")
                       for index, (title, artist) in enumerate([
                           ("Neon Afterimage", "Static Harbor"),
                           ("Soft Circuit", "Lumen Field"),
                           ("Night Relay", "Static Harbor"),
                           ("Glasslines", "Aster Drive"),
                           ("Last Light", "Lumen Field"),
                       ])]
        self.playlists = [Entry("playlist", "p1", "After Hours", "Static Harbor", art="demo:2"),
                          Entry("album", "p2", "Quiet Machines", "Lumen Field", art="demo:3")]
        self.artists = [Entry("user", track.artist_key, track.artist, art=track.art)
                        for track in (self.tracks[0], self.tracks[1], self.tracks[3])]
        self.likes = self.tracks[:3]

    def search(self, query):
        return [item for item in self.tracks + self.playlists + self.artists
                if all(word in (item.title + " " + item.artist).casefold()
                       for word in query.casefold().split())]

    def section(self, tab):
        return {
            "recent": self.tracks[:3], "artists": self.artists,
            "mixes": [Entry("station", "m1", "Night Drive", art="demo:4")],
            "likes": self.likes[:], "playlists": self.playlists, "uploads": self.tracks[3:],
            "feed": self.tracks[::-1],
        }[tab]

    def collection(self, item):
        if item.kind == "user":
            return [track for track in self.tracks if track.artist_key == item.key]
        return self.tracks[:] if item.key != "p2" else self.tracks[2:]

    def comments(self, track):
        draft = [(2, "ari", "В наушниках совсем другой звук."),
                 (6, "sena", "Вот этот переход!"),
                 (11, "lofi", "Бас здесь отлично лёг."),
                 (18, "echoes", "Добавляю в ночной плейлист."),
                 (33, "mira", "Любимая часть."),
                 (61, "drifts", "Этот синтезатор…"),
                 (95, "ari", "Ещё раз с начала.")]
        return [Comment(*args) for args in draft]

    def like(self, track, value):
        if value and track not in self.likes:
            self.likes.append(track)
        elif not value and track in self.likes:
            self.likes.remove(track)

    def waveform(self, track):
        seed = int(track.key)
        return [min(1, (.25 + .72 * abs(math.sin(i * .039 + seed))) *
                    (.41 + .59 * abs(math.sin(i * .73 + math.sin(i * .17) * 2))))
                for i in range(1200)]


class DemoPlayback:
    def __init__(self, offset, duration, paused):
        self.offset = offset
        self.duration = duration
        self.started = time.monotonic()
        self.paused = paused
        self.gain = 0
        self.levels = []

    @property
    def position(self):
        return min(self.duration, self.offset + (0 if self.paused else time.monotonic() - self.started))

    @property
    def ended(self):
        return self.position >= self.duration

    @property
    def label(self):
        return "Демо · пауза" if self.paused else "Демо · без звука"

    def toggle(self):
        self.offset = self.position
        self.started = time.monotonic()
        self.paused = not self.paused

    def close(self):
        pass
