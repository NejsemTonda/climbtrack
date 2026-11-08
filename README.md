# HC4 — evidence lezení

Flask + SQLite + plain HTML/CSS/JS rewrite of the Lovable app (`../climbtrack`).

```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/flask --app app init-db                  # empty db with the 12 default groups
# or copy the live data from Supabase (replaces hc4.db):
.venv/bin/python import_supabase.py ../climbtrack/.env
.venv/bin/flask --app app run                      # http://127.0.0.1:5000
.venv/bin/python test_app.py                       # self-check
```

Environment:
- `APP_PASSWORD` — if set, the whole app asks for it (HTTP basic auth, any username). Unset = open to anyone with the link, like the original.
- `SECRET_KEY` — set a fixed value in production (it signs the flash-message cookie).
- `HC4_DB` — database path (default `./hc4.db`).

Production: run behind any WSGI server, e.g. `pip install gunicorn && gunicorn -w 2 app:app`, with HTTPS in front if you use `APP_PASSWORD`.
Backup = copy `hc4.db`.

Hosting on lezik.cz (Caddy, systemd, `lezik` management command): see [`deploy/README.md`](deploy/README.md).
