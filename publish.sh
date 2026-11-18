#!/bin/sh
# Run with a working GitHub CLI connection. The release workflow publishes after CI.
set -eu
cd -- "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
python3 -m unittest discover -s tests -q
command -v gh >/dev/null 2>&1 || { echo 'GitHub CLI (gh) is required.' >&2; exit 1; }
gh auth status
if [ ! -d .git ]; then git init -b main; fi
git add -- .
if ! git diff --cached --quiet; then
    git -c user.name=user9x21imi -c user.email=164790188+user9x21imi@users.noreply.github.com commit -m 'Prepare ttools suite installers, verified updates and preview release'
fi
if ! gh repo view user9x21imi/ttools >/dev/null 2>&1; then
    gh repo create user9x21imi/ttools --public --source . --remote origin --description 'Animated terminal workspace and unified app installer'
fi
if ! git remote get-url origin >/dev/null 2>&1; then git remote add origin https://github.com/user9x21imi/ttools.git; fi
git push -u origin main
printf '%s\n' 'Code pushed. GitHub Actions will test all three OSes, package assets, and publish the preview release.'
