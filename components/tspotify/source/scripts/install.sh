#!/bin/sh
set -eu
release="${TSPOTIFY_RELEASE:-latest}"
case "$release" in latest) release_path=latest/download ;; v[0-9]*.[0-9]*.[0-9]*) release_path="download/$release" ;; *) echo "Invalid release" >&2; exit 1 ;; esac
repo="https://github.com/user9x21imi/tspotify/releases/$release_path"
case "$(uname -s)/$(uname -m)" in
  Linux/x86_64) asset=tspotify-linux-x86_64.zip ;;
  Darwin/arm64) asset=tspotify-macos-arm64.zip ;;
  Darwin/x86_64) asset=tspotify-macos-x86_64.zip ;;
  *) echo "No native build for this OS/architecture. See the source installation instructions." >&2; exit 1 ;;
esac
command -v curl >/dev/null 2>&1 || { echo 'curl is required.' >&2; exit 1; }
command -v unzip >/dev/null 2>&1 || { echo 'unzip is required.' >&2; exit 1; }
task_tmp=$(mktemp -d)
trap 'rm -rf "$task_tmp"' EXIT HUP INT TERM
echo '+-- installing tspotify ---------------------------------------+'
curl -fL --retry 3 "$repo/$asset" -o "$task_tmp/$asset"
curl -fsSL --retry 3 "$repo/SHA256SUMS.txt" -o "$task_tmp/checksums"
expected=$(awk -v name="$asset" '$2 == name {print $1}' "$task_tmp/checksums")
case "$expected" in ''|*[!a-fA-F0-9]*) echo 'Missing/invalid release checksum.' >&2; exit 1 ;; esac
[ "${#expected}" -eq 64 ] || { echo 'Invalid SHA-256 length.' >&2; exit 1; }
if command -v sha256sum >/dev/null 2>&1; then
  actual=$(sha256sum "$task_tmp/$asset" | awk '{print $1}')
else
  actual=$(shasum -a 256 "$task_tmp/$asset" | awk '{print $1}')
fi
[ "$actual" = "$expected" ] || { echo 'Checksum mismatch. Installation stopped.' >&2; exit 1; }
unzip -q "$task_tmp/$asset" -d "$task_tmp/unpacked"
[ -f "$task_tmp/unpacked/tspotify/tspotify" ] || { echo 'Invalid release archive.' >&2; exit 1; }
app_root="$HOME/.local/share/tspotify"
mkdir -p "$app_root" "$HOME/.local/bin"
if [ -d "$app_root/app" ]; then
  rm -rf "$app_root/app.previous"
  mv "$app_root/app" "$app_root/app.previous"
fi
mv "$task_tmp/unpacked/tspotify" "$app_root/app"
chmod +x "$app_root/app/tspotify"
ln -sfn "$app_root/app/tspotify" "$HOME/.local/bin/tspotify"
case "${SHELL:-}" in
  */zsh) shell_config="$HOME/.zshrc" ;;
  */bash)
    if [ "$(uname -s)" = Darwin ]; then shell_config="$HOME/.bash_profile"; else shell_config="$HOME/.bashrc"; fi ;;
  *) shell_config="$HOME/.profile" ;;
esac
case ":$PATH:" in
  *":$HOME/.local/bin:"*) ;;
  *)
    if ! [ -f "$shell_config" ] || ! grep -F '# tspotify user bin' "$shell_config" >/dev/null 2>&1; then
      printf '\n# tspotify user bin\nexport PATH="$HOME/.local/bin:$PATH"\n' >> "$shell_config"
    fi ;;
esac
"$HOME/.local/bin/tspotify" --version
echo 'Installed. Open a new terminal and run: tspotify'
echo "Or run now: $HOME/.local/bin/tspotify"

