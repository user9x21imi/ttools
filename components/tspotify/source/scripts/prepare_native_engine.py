"""Prepare an immutable MIT upstream with a small, audited local-control patch."""

import argparse
import hashlib
import io
from pathlib import Path
import tarfile
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
    implementation.write_text(text.replace(anchor, anchor + patch, 1))
    cargo = crate / "Cargo.toml"
    cargo.write_text(cargo.read_text().replace('version = "0.25.2"', 'version = "0.25.2+tspotify.1"', 1))
    lock = destination / "Cargo.lock"
    old = 'name = "spotify_player"\nversion = "0.25.2"'
    assert old in lock.read_text()
    lock.write_text(
        lock.read_text().replace(old, 'name = "spotify_player"\nversion = "0.25.2+tspotify.1"', 1)
    )
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("destination")
    parser.add_argument("--archive")
    args = parser.parse_args()
    print(prepare(args.destination, args.archive))
