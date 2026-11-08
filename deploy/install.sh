#!/usr/bin/env bash
# Install/refresh the lezik CLI and systemd user units from this repo. Run as the app user (no sudo).
# `lezik deploy` runs this automatically after every pull.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
UNITS="$HOME/.config/systemd/user"

mkdir -p "$HOME/.local/bin" "$UNITS" "$HOME/data/backups"
install -m 755 "$REPO/deploy/lezik" "$HOME/.local/bin/lezik"
install -m 644 "$REPO"/deploy/systemd/*.service "$REPO"/deploy/systemd/*.timer "$UNITS/"
[ -x "$REPO/.venv/bin/python" ] || python3 -m venv "$REPO/.venv"
"$REPO/.venv/bin/pip" install -q --disable-pip-version-check -r "$REPO/requirements.txt" gunicorn
[ -f "$HOME/env" ] || { echo "!! Missing ~/env — copy deploy/env.example there and fill it in."; exit 1; }
systemctl --user daemon-reload
systemctl --user enable -q lezik.service lezik-backup.timer
systemctl --user start lezik-backup.timer
echo "Installed lezik CLI and units."
