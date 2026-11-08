# Hosting (lezik.cz)

```
Browser ──https──▶ router :443 ──▶ Caddy (root) ──http──▶ gunicorn (user climbtrack) ──▶ SQLite
                   (port forward)  lezik.cz, TLS          127.0.0.1:3100, Flask app       ~/data/hc4.db
```

- **DNS**: `lezik.cz` and `www.lezik.cz` have `A` records to the server's public IP. No `AAAA` records.
- **Caddy** ([`Caddyfile`](Caddyfile) → `/etc/caddy/Caddyfile`) handles HTTPS (Let's Encrypt, auto-renewed),
  proxies `lezik.cz` to the app and redirects `www` to the bare domain. The app listens only on localhost.
- **App** runs as the unprivileged user `climbtrack` (SSH key login, no password, no sudo) as a systemd
  *user* service ([`systemd/lezik.service`](systemd/lezik.service)); linger keeps it running at boot without a login.
- **Backups**: [`systemd/lezik-backup.timer`](systemd/lezik-backup.timer) runs `lezik backup` daily, keeping the last 30.

Layout of `/home/climbtrack`:

```
app/              this repo (deploy-only checkout) + .venv
data/hc4.db       live database — outside the repo, so deploys never touch it
data/backups/     backups
env               settings, see env.example
.local/bin/lezik  installed copy of deploy/lezik
```

## Day to day

`ssh climbtrack@kdesi.duckdns.org`, then:

| Command | |
|---|---|
| `lezik deploy` | back up DB, reset `~/app` to `origin/<branch>`, reinstall deps + CLI + units, restart; rolls back if the app doesn't respond |
| `lezik logs` | follow logs |
| `lezik status` / `restart` / `stop` / `start` | service control |
| `lezik backup` / `backups` / `restore FILE` | database backups |
| `lezik config` | edit `~/env` (e.g. set `APP_PASSWORD`) and restart |
| `lezik check` | test the app locally and via https://lezik.cz |

Release = push to GitHub, then `lezik deploy`. Changes to files in `deploy/` take effect on the next deploy
(`install.sh` re-copies the CLI and units). The Caddyfile is the exception: copy it to `/etc/caddy/` and
`sudo systemctl reload caddy`.

## New server

On a fresh Arch machine with this repo checked out: `sudo deploy/setup-server.sh`
(installs Caddy, creates the `climbtrack` user with the invoking user's SSH keys, clones the repo, starts the app).
Then copy the database to `/home/climbtrack/data/hc4.db` and `lezik restart`. Forward ports 80/443 and set DNS.
