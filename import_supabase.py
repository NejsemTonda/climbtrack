"""One-off copy of all data from the old Lovable/Supabase project into hc4.db.

Usage:  python import_supabase.py ../climbtrack/.env
Reads SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY from that .env file. Replaces everything in hc4.db.
"""
import json
import sqlite3
import sys
import urllib.request

from app import DB_PATH, init_db

COLUMNS = {
    "groups": ["id", "name", "weekday", "start_time", "end_time", "created_at"],
    "children": ["id", "group_id", "first_name", "gender", "birth_year", "climbing_years", "level", "created_at"],
    "routes": ["id", "color", "chain_number", "created_at"],
    "climbs": ["id", "child_id", "group_id", "route_id", "route_color", "chain_number", "grade", "style", "note", "climbed_at"],
    "lezik_challenges": ["id", "title", "starts_on", "ends_on", "created_at"],
    "lezik_tasks": ["id", "challenge_id", "title", "reward", "levels", "position"],
    "lezik_completions": ["id", "child_id", "task_id", "task_title", "reward", "completed_at"],
}


def fetch(base, key, table):
    rows, offset = [], 0
    while True:  # PostgREST caps responses at 1000 rows
        req = urllib.request.Request(f"{base}/rest/v1/{table}?select=*&order=id&limit=1000&offset={offset}",
                                     headers={"apikey": key, "Authorization": f"Bearer {key}"})
        with urllib.request.urlopen(req, timeout=30) as r:
            page = json.load(r)
        rows += page
        if len(page) < 1000:
            return rows
        offset += 1000


def main(env_path):
    env = dict(l.strip().split("=", 1) for l in open(env_path) if "=" in l and not l.startswith("#"))
    base = env["SUPABASE_URL"].strip('"').rstrip("/")
    key = env["SUPABASE_PUBLISHABLE_KEY"].strip('"')
    data = {t: fetch(base, key, t) for t in COLUMNS}  # fetch everything before touching the local db

    conn = sqlite3.connect(DB_PATH)
    init_db(conn, seed=False)
    with conn:
        for t in reversed(COLUMNS):
            conn.execute(f"DELETE FROM {t}")
        for t, cols in COLUMNS.items():
            for row in data[t]:
                vals = [json.dumps(row[c], ensure_ascii=False) if c == "levels" else row.get(c) for c in cols]
                conn.execute(f"INSERT INTO {t} ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})", vals)
            print(f"{t}: {len(data[t])}")
    print(f"Imported into {DB_PATH}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "../climbtrack/.env")
