#!/usr/bin/env python3
"""User-only Linux native install/update/rollback for ttools. No UI or OAuth."""

import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

APP_ID = "tspotify"
DEFAULT_MANIFEST = None


@contextlib.contextmanager
def locked(path):
    import fcntl

    with path.open("a+b") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError(
                "tspotify is running or another update is in progress; stop it first"
            ) from None
        yield


def fetch(url, target, limit):
    if not url.startswith("https://"):
        raise ValueError("Only HTTPS download URLs are allowed")
    request = urllib.request.Request(url, headers={"User-Agent": "tspotify-ttools-installer/1"})
    with urllib.request.urlopen(request, timeout=60) as response, target.open("wb") as stream:
        count = 0
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            count += len(chunk)
            if count > limit:
                raise RuntimeError("Download exceeds the package size limit")
            stream.write(chunk)


def read_manifest(value, directory):
    if value.startswith("https://"):
        path = directory / "update.json"
        fetch(value, path, 1024 * 1024)
    else:
        if "://" in value:
            raise ValueError("Only HTTPS manifests or explicit local files are allowed")
        path = Path(value).expanduser().resolve()
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or data.get("app_id") != APP_ID:
        raise ValueError("Wrong manifest schema or app_id")
    version = data.get("version", "")
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Invalid version")
    artifact = next((entry for entry in data["artifacts"] if entry["platform"] == "linux-x86_64"), None)
    if not artifact or not re.fullmatch(r"[0-9a-f]{64}", artifact.get("sha256", "")):
        raise ValueError("Missing Linux x86_64 artifact/checksum")
    return data, artifact


def extract(archive, directory):
    with zipfile.ZipFile(archive) as package:
        entries = package.infolist()
        if len(entries) > 20000 or sum(entry.file_size for entry in entries) > 1024**3:
            raise ValueError("Archive exceeds extraction limits")
        for entry in entries:
            path = Path(entry.filename)
            mode = entry.external_attr >> 16
            kind = stat.S_IFMT(mode)
            if (
                path.is_absolute()
                or ".." in path.parts
                or "\\" in entry.filename
                or not path.parts
                or path.parts[0] != "tspotify"
                or kind not in (0, stat.S_IFREG, stat.S_IFDIR)
            ):
                raise ValueError("Unsafe archive entry: " + entry.filename)
            target = directory / path
            if entry.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with package.open(entry) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)
            target.chmod(0o755 if mode & 0o111 else 0o644)
    binary = directory / "tspotify/tspotify"
    if not binary.is_file():
        raise ValueError("Archive has no native tspotify executable")
    binary.chmod(0o755)
    return binary


def verify(binary, version):
    result = subprocess.run(
        [str(binary), "--version"], capture_output=True, text=True, timeout=20, check=True
    )
    if result.stdout.strip() != "tspotify " + version:
        raise ValueError("The native program version does not match its manifest")
    result = subprocess.run(
        [str(binary), "verify-runtime"], capture_output=True, text=True, timeout=30, check=True
    )
    data = json.loads(result.stdout)
    if not data.get("ok") or data.get("version") != version:
        raise ValueError("Runtime dependency verification failed")


def atomic_text(path, text, mode=0o600):
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".install-", delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(text.encode("utf-8"))
        stream.flush()
        os.fsync(stream.fileno())
    temporary.chmod(mode)
    temporary.replace(path)


def link(path, target):
    temporary = path.with_name(path.name + ".next")
    temporary.unlink(missing_ok=True)
    temporary.symlink_to(target)
    temporary.replace(path)


def target_of(path):
    if not path.is_symlink():
        return None
    value = os.readlink(path)
    resolved = (path.parent / value).resolve()
    versions = (path.parent / "versions").resolve()
    if versions not in resolved.parents:
        raise ValueError("Installed version points outside the managed versions directory")
    return value


def install(args):
    if not args.rollback and not args.manifest:
        raise ValueError("Pass --manifest with an existing HTTPS manifest or a local update.json")
    if platform.system() != "Linux" or platform.machine() not in ("x86_64", "AMD64"):
        raise RuntimeError("This installer supports Linux x86_64 only")
    libc, libc_version = platform.libc_ver()
    if libc != "glibc" or tuple(map(int, libc_version.split(".")[:2])) < (2, 39):
        raise RuntimeError("The native runtime requires glibc 2.39 or newer")
    prefix = Path(args.prefix).expanduser().resolve()
    prefix.mkdir(parents=True, exist_ok=True, mode=0o700)
    with locked(prefix / "install.lock"), locked(prefix / "run.lock"):
        current, previous = prefix / "current", prefix / "previous"
        old = target_of(current)
        old_previous = target_of(previous)
        if args.rollback:
            prior = target_of(previous)
            if not prior:
                raise RuntimeError("No previous installation is available")
            binary = prefix / prior / "tspotify/tspotify"
            info = json.loads((binary.parent / ".ttools-managed.json").read_text(encoding="utf-8"))
            verify(binary, info["version"])
            link(current, prior)
            if old:
                link(previous, old)
            print(json.dumps({"app_id": APP_ID, "version": info["version"], "rollback": True}))
            return
        versions = prefix / "versions"
        versions.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".stage-", dir=versions) as folder:
            stage = Path(folder)
            manifest, artifact = read_manifest(args.manifest, stage)
            if args.archive:
                archive = Path(args.archive).expanduser().resolve()
            else:
                archive = stage / "runtime.zip"
                fetch(artifact["url"], archive, 256 * 1024**2)
            with archive.open("rb") as archive_stream:
                digest = hashlib.sha256()
                for chunk in iter(lambda: archive_stream.read(1024 * 1024), b""):
                    digest.update(chunk)
                digest = digest.hexdigest()
            if digest != artifact["sha256"]:
                raise ValueError("SHA-256 mismatch; the installed version has not been changed")
            unpacked = stage / "unpacked"
            binary = extract(archive, unpacked)
            verify(binary, manifest["version"])
            if args.prepare_engine:
                subprocess.run([str(binary), "install-engine"], check=True, timeout=600)
            marker = {
                "app_id": APP_ID,
                "update_owner": "ttools",
                "prefix": str(prefix),
                "version": manifest["version"],
                "sha256": digest,
            }
            atomic_text(binary.parent / ".ttools-managed.json", json.dumps(marker))
            identity = manifest["version"] + "-" + digest[:12] + "-" + stage.name.removeprefix(".stage-")
            destination = versions / identity
            unpacked.rename(destination)
            new = "versions/" + identity
            bin_dir = prefix / "bin"
            bin_dir.mkdir(exist_ok=True)
            wrapper = (
                "#!/bin/sh\nset -eu\n"
                'prefix=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)\n'
                'export TSPOTIFY_INSTALL_PREFIX="$prefix"\n'
                "export TSPOTIFY_UPDATE_OWNER=ttools\n"
                'exec "$prefix/current/tspotify/tspotify" "$@"\n'
            )
            try:
                atomic_text(bin_dir / "tspotify", wrapper, 0o755)
                if old:
                    link(previous, old)
                link(current, new)
                atomic_text(
                    prefix / "install.json",
                    json.dumps(
                        {**marker, "artifact_url": artifact.get("url"), "manifest": args.manifest},
                        ensure_ascii=False,
                        indent=2,
                    )
                    + "\n",
                )
            except BaseException:
                if old:
                    link(current, old)
                else:
                    current.unlink(missing_ok=True)
                if old_previous:
                    link(previous, old_previous)
                else:
                    previous.unlink(missing_ok=True)
                shutil.rmtree(destination, ignore_errors=True)
                raise
            keep = {target_of(current), target_of(previous)}
            for candidate in versions.iterdir():
                if (
                    candidate.is_dir()
                    and not candidate.name.startswith(".")
                    and "versions/" + candidate.name not in keep
                ):
                    shutil.rmtree(candidate)
        print(
            json.dumps(
                {
                    "app_id": APP_ID,
                    "version": manifest["version"],
                    "installed": str(prefix / "bin/tspotify"),
                    "update_owner": "ttools",
                },
                ensure_ascii=False,
            )
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prefix", default=str(Path.home() / ".local/share/ttools/apps/tspotify"))
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST)
    parser.add_argument("--archive", help="explicit offline archive; still checked against manifest SHA-256")
    parser.add_argument(
        "--prepare-engine", action="store_true", help="download/check pinned engine without login or playback"
    )
    parser.add_argument("--rollback", action="store_true")
    args = parser.parse_args()
    try:
        install(args)
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as error:
        print("tspotify installer: " + str(error), file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
