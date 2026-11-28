"""Prepare an immutable MIT upstream with a small, audited local-control patch."""

import argparse
import hashlib
import io
from pathlib import Path
import tarfile
import tomllib
import urllib.request

COMMIT = "966d84a6b90ee82d977430d4b4ee3f59dfc4b204"
SHA256 = "fd37e0f6bf2c04c3ce917f8faa1ad5540860d840d955f7add504217f75ee1f85"
URL = "https://codeload.github.com/aome510/spotify-player/tar.gz/" + COMMIT


def prepare(destination, archive=None):
    data = Path(archive).read_bytes() if archive else urllib.request.urlopen(URL, timeout=60).read()
    if hashlib.sha256(data).hexdigest() != SHA256:
        raise ValueError("Upstream source checksum mismatch")
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(data)) as package:
        for entry in package:
            path = Path(entry.name)
            if path.is_absolute() or ".." in path.parts or entry.issym() or entry.islnk():
                raise ValueError("Unsafe source entry")
            relative = Path(*path.parts[1:])
            if not relative.parts:
                continue
            target = destination / relative
            if entry.isdir():
                target.mkdir(parents=True, exist_ok=True)
            elif entry.isfile():
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(package.extractfile(entry).read())
    crate = destination / "spotify_player"
    request = crate / "src/cli/mod.rs"
    text = request.read_text()
    anchor = "pub enum Request {\n"
    assert text.count(anchor) == 1
    request.write_text(
        text.replace(anchor, anchor + "    Local { command: String, #[serde(default)] value: i64 },\n", 1)
    )
    client = crate / "src/cli/client.rs"
    text = client.read_text()
    anchor = "    match request {\n"
    assert anchor in text
    client.write_text(
        text.replace(
            anchor,
            anchor
            + "        Request::Local { command, value } => client.tspotify_local_control(&command, value),\n",
            1,
        )
    )
    implementation = crate / "src/client/mod.rs"
    text = implementation.read_text()
    anchor = "impl AppClient {\n"
    patch = (Path(__file__).resolve().parents[1] / "engine/local_control.rs").read_text()
    assert text.count(anchor) == 1
    text = text.replace(anchor, anchor + patch, 1)
    start = text.index("    pub fn initialize_playback(")
    end = text.index("    /// Create a new client session", start)
    text = (
        text[:start]
        + "    pub fn initialize_playback(&self, _state: &SharedState, _resume: bool) {\n        // tspotify owns activation. Never transfer old Web API state behind its back.\n    }\n"
        + text[end:]
    )
    field = "stream_conn: Arc<Mutex<Option<librespot_connect::Spirc>>>,"
    text = text.replace(
        field,
        field
        + '\n    #[cfg(feature = "streaming")]\n    pub(crate) tspotify_state: Arc<Mutex<serde_json::Value>>,',
        1,
    )
    init = "stream_conn: Arc::new(Mutex::new(None)),"
    text = text.replace(
        init,
        init
        + '\n            #[cfg(feature = "streaming")]\n            tspotify_state: Arc::new(Mutex::new(serde_json::json!({"revision": 0, "repeat_state": "off", "shuffle_state": false}))),',
        1,
    )
    native = (Path(__file__).resolve().parents[1] / "engine/native_state.rs").read_text()
    native += (Path(__file__).resolve().parents[1] / "engine/jam.rs").read_text()
    text = text.replace("impl AppClient {\n", "impl AppClient {\n" + native, 1)
    text += (Path(__file__).resolve().parents[1] / "engine/connect_tests.rs").read_text()
    implementation.write_text(text)
    streaming = crate / "src/streaming.rs"
    body = streaming.read_text().replace(
        "                // Suppress Spotify's auto-resume",
        "                client.tspotify_player_event(&event);\n                // Suppress Spotify's auto-resume",
        1,
    )
    assert "client.tspotify_player_event(&event);" in body
    reset = "    let configs = config::get_config();"
    body = body.replace(
        reset,
        '    { let mut native = client.tspotify_state.lock(); let revision = native["revision"].as_u64().unwrap_or(0) + 1; *native = serde_json::json!({"revision": revision, "device_id": session.device_id(), "is_playing": false, "repeat_state": "off", "shuffle_state": false}); }\n'
        + reset,
        1,
    )
    streaming.write_text(body)
    cli = crate / "src/cli/mod.rs"
    cli.write_text(
        cli.read_text().replace(
            "const MAX_REQUEST_SIZE: usize = 4096;", "const MAX_REQUEST_SIZE: usize = 65507;", 1
        )
    )
    cargo = crate / "Cargo.toml"
    cargo.write_text(cargo.read_text().replace('version = "0.25.2"', 'version = "0.25.2+tspotify.9"', 1))
    lock = destination / "Cargo.lock"
    old = 'name = "spotify_player"\nversion = "0.25.2"'
    assert old in lock.read_text()
    lock.write_text(
        lock.read_text().replace(old, 'name = "spotify_player"\nversion = "0.25.2+tspotify.9"', 1)
    )
    # Backport the upstream Connect fix: an empty URI must not override a real UID/index.
    expected = "4b2a21e9e19b906c6676b1a515fc5529d5414f69049f5a167dfb2ea3206e5a27"
    vendor_data = urllib.request.urlopen(
        "https://static.crates.io/crates/librespot-connect/librespot-connect-0.8.0.crate", timeout=60
    ).read()
    if hashlib.sha256(vendor_data).hexdigest() != expected:
        raise ValueError("librespot-connect source checksum mismatch")
    vendor = destination / "vendor/librespot-connect"
    with tarfile.open(fileobj=io.BytesIO(vendor_data), mode="r:gz") as package:
        for entry in package:
            path = Path(entry.name)
            if path.is_absolute() or ".." in path.parts or entry.issym() or entry.islnk():
                raise ValueError("Unsafe dependency entry")
            relative = Path(*path.parts[1:])
            if entry.isfile() and relative.parts:
                target = vendor / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(package.extractfile(entry).read())
    model = vendor / "src/model.rs"
    body = model.read_text()
    assert "if let Some(uri) = value.track_uri {" in body
    body = body.replace(
        "if let Some(uri) = value.track_uri {",
        "if let Some(uri) = value.track_uri.filter(|uri| !uri.is_empty()) {",
        1,
    )
    body = body.replace(
        "if let Some(uid) = value.track_uid {",
        "if let Some(uid) = value.track_uid.filter(|uid| !uid.is_empty()) {",
        1,
    )
    model.write_text(body)
    spirc = vendor / "src/spirc.rs"
    body = spirc.read_text()
    field = "    tspotify_queue: Arc<std::sync::Mutex<serde_json::Value>>,\n"
    body = body.replace("struct SpircTask {\n", "struct SpircTask {\n" + field, 1)
    body = body.replace("pub struct Spirc {\n", "pub struct Spirc {\n" + field, 1)
    body = body.replace(
        "        let mut task = SpircTask {",
        "        let tspotify_queue = Arc::new(std::sync::Mutex::new(serde_json::json!({})));\n        let mut task = SpircTask {\n            tspotify_queue: tspotify_queue.clone(),",
        1,
    )
    body = body.replace(
        "let spirc = Spirc { commands: cmd_tx };",
        "let spirc = Spirc { commands: cmd_tx, tspotify_queue };",
        1,
    )
    body = body.replace(
        "impl Spirc {\n",
        "impl Spirc {\n    pub fn tspotify_queue(&self) -> serde_json::Value { self.tspotify_queue.lock().unwrap().clone() }\n",
        1,
    )
    body = body.replace(
        "            let commands = self.commands.as_mut();",
        """            let p = self.connect_state.player();
            *self.tspotify_queue.lock().unwrap() = serde_json::json!({
                "queue_current_uri": p.track.uri,
                "actual_shuffle": self.connect_state.shuffling_context(),
                "actual_repeat": if self.connect_state.repeat_track() { "track" } else if self.connect_state.repeat_context() { "context" } else { "off" },
                "next_uris": p.next_tracks.iter().take(20).map(|t| t.uri.clone()).collect::<Vec<_>>(),
                "context_uri": p.context_uri,
                "queue_ended": self.connect_state.is_active() && !p.track.uri.is_empty() && matches!(self.play_status, SpircPlayStatus::Stopped),
            });
            let commands = self.commands.as_mut();""",
        1,
    )
    # Remote Resume already reloads from Stopped; local Play/Next must do so too.
    body = body.replace(
        "SpircCommand::Play => self.handle_play(),",
        "SpircCommand::Play if matches!(self.play_status, SpircPlayStatus::Stopped) => self.load_track(true, 0)?,\n            SpircCommand::Play => self.handle_play(),",
        1,
    )
    body = body.replace(
        "SpircCommand::Next => self.handle_next(None)?,",
        "SpircCommand::Next if matches!(self.play_status, SpircPlayStatus::Stopped) => self.load_track(true, 0)?,\n            SpircCommand::Next => self.handle_next(None)?,",
        1,
    )
    assert "SpircCommand::Play if" in body and "SpircCommand::Next if" in body
    body = body.replace(
        "    Play,\n", "    Play,\n    TspotifyMode { name: String, value: i64, revision: u64 },\n", 1
    )
    body = body.replace("struct SpircTask {\n", "struct SpircTask {\n    tspotify_mode_revision: u64,\n", 1)
    body = body.replace(
        "        let mut task = SpircTask {\n",
        "        let mut task = SpircTask {\n            tspotify_mode_revision: 0,\n",
        1,
    )
    body = body.replace(
        "impl Spirc {\n",
        """impl Spirc {
    pub fn tspotify_mode(&self, name: &str, value: i64, revision: u64) -> Result<(), Error> {
        Ok(self.commands.send(SpircCommand::TspotifyMode { name: name.to_owned(), value, revision })?)
    }
""",
        1,
    )
    body = body.replace(
        '"queue_current_uri": p.track.uri,',
        '"queue_current_uri": p.track.uri, "applied_mode_revision": self.tspotify_mode_revision,',
        1,
    )
    anchor = "            SpircCommand::Shutdown => {"
    assert anchor in body
    body = body.replace(
        anchor,
        """            SpircCommand::TspotifyMode { name, value, revision } => {
                if name == "shuffle" {
                    if self.connect_state.is_active() { self.handle_shuffle(value != 0)?; }
                    else { self.connect_state.set_shuffle(value != 0); }
                } else {
                    if self.connect_state.is_active() {
                        self.handle_repeat_context(value == 1);
                        self.handle_repeat_track(value == 2);
                    } else {
                        self.connect_state.set_repeat_context(value == 1);
                        self.connect_state.set_repeat_track(value == 2);
                    }
                }
                self.tspotify_mode_revision = revision;
            },
"""
        + anchor,
        1,
    )
    spirc.write_text(body)
    workspace = destination / "Cargo.toml"
    workspace.write_text(
        workspace.read_text()
        + '\n[patch.crates-io]\nlibrespot-connect = { path = "vendor/librespot-connect" }\n'
    )
    body = lock.read_text()
    start = body.index('name = "librespot-connect"\n')
    end = body.index("[[package]]", start)
    block = body[start:end]
    entry = next(e for e in tomllib.loads(body)["package"] if e["name"] == "librespot-connect")
    assert entry["checksum"] == expected
    block = "\n".join(line for line in block.split("\n") if not line.startswith(("source =", "checksum =")))
    lock.write_text(body[:start] + block + body[end:])
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("destination")
    parser.add_argument("--archive")
    args = parser.parse_args()
    print(prepare(args.destination, args.archive))
