#!/usr/bin/env bash
# One-time setup of a fresh Arch machine for lezik.cz. Run with sudo.
# Creates the app user, installs Caddy, clones the repo and starts the app.
# Afterwards: put the database at /home/climbtrack/data/hc4.db (or run `flask --app app init-db`).
set -euo pipefail
[ "$EUID" -eq 0 ] || { echo "Run with sudo"; exit 1; }
U=climbtrack
H=/home/$U
REPO_URL=https://github.com/NejsemTonda/climbtrack
HERE="$(cd "$(dirname "$0")" && pwd)"
as_user() { runuser -u $U -- env XDG_RUNTIME_DIR=/run/user/$(id -u $U) "$@"; }

pacman -S --needed --noconfirm caddy git python
install -m 644 "$HERE/Caddyfile" /etc/caddy/Caddyfile
systemctl enable --now caddy
systemctl reload caddy

id $U &>/dev/null || useradd --create-home --shell /bin/bash --user-group $U
passwd -l $U >/dev/null          # no password: SSH key login only
chmod 750 $H
grep -q '.local/bin' $H/.bashrc 2>/dev/null || echo 'export PATH="$HOME/.local/bin:$PATH"' >> $H/.bashrc
install -d -o $U -g $U -m 700 $H/.ssh $H/data
[ -n "${SUDO_USER:-}" ] && [ -f /home/$SUDO_USER/.ssh/authorized_keys ] && [ ! -f $H/.ssh/authorized_keys ] &&
  install -o $U -g $U -m 600 /home/$SUDO_USER/.ssh/authorized_keys $H/.ssh/authorized_keys

[ -d $H/app/.git ] || as_user git clone -q $REPO_URL $H/app
if [ ! -f $H/env ]; then
  sed "s|^SECRET_KEY=.*|SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')|" $H/app/deploy/env.example > $H/env
  chown $U:$U $H/env; chmod 600 $H/env
fi

loginctl enable-linger $U
systemctl start user@$(id -u $U).service
as_user $H/app/deploy/install.sh
as_user systemctl --user restart lezik
echo "Done. Manage with: ssh $U@<host>, then 'lezik'."
