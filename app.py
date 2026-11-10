import json
import os
import sqlite3
import uuid
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from flask import Flask, abort, flash, g, redirect, render_template, request, send_from_directory, url_for

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("HC4_DB", os.path.join(APP_DIR, "hc4.db"))
PHOTO_DIR = os.environ.get("HC4_PHOTOS", os.path.join(os.path.dirname(os.path.abspath(DB_PATH)), "boulder-photos"))
TZ = ZoneInfo("Europe/Prague")

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or os.urandom(32)
PHOTO_MAX_BYTES = 10 * 1024 * 1024
app.config["MAX_CONTENT_LENGTH"] = PHOTO_MAX_BYTES + 64 * 1024  # photo + form fields

WEEKDAYS_CS = ["", "Pondělí", "Úterý", "Středa", "Čtvrtek"]
WEEKDAYS_SHORT = ["", "Po", "Út", "St", "Čt"]
LEVELS = ["začátečník", "mírně pokročilé", "master"]
STYLES = ["top rope", "na prvním"]
STYLE_POINTS = {"top rope": 2, "na prvním": 4}
SLOTS = ["14:30", "16:00", "17:30"]
ROUTE_COLORS = {
    "bílá": "#ffffff", "šedá": "#94a3b8", "černá": "#1e293b", "žlutá": "#facc15",
    "oranžová": "#f97316", "červená": "#ef4444", "vínová": "#9f1239", "fialová": "#a855f7",
    "zelená": "#22c55e", "modrá": "#3b82f6", "písková": "#fde68a",
}
LEZIK_MAX_PER_CHALLENGE = 2
MAX_TASKS = 6
KINDS = {"cesta": "Cesty", "traverz": "Traverzy", "boulder": "Bouldery"}
KIND_STYLE = {"traverz": "hotovo", "boulder": "top"}  # the single "done" style of non-rope climbs
STYLE_LABELS = {"hotovo": "traverz", "top": "boulder"}
TRAVERSE_POINTS = 5
WEEKLY_BONUS_MAX = 4


# ---------- db ----------

def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    conn = g.pop("db", None)
    if conn:
        conn.close()


def q(sql, *args):
    return db().execute(sql, args).fetchall()


def q1(sql, *args):
    return db().execute(sql, args).fetchone()


def run(sql, *args):
    db().execute(sql, args)
    db().commit()


def new_id():
    return str(uuid.uuid4())


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def table_cols(conn, table):
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def init_db(conn, seed=True):
    """Create missing tables and migrate older databases in place."""
    old_routes = table_cols(conn, "routes") and "kind" not in table_cols(conn, "routes")
    if old_routes:  # v2 -> v3: rebuild routes without UNIQUE (color, chain_number)
        conn.execute("PRAGMA legacy_alter_table=ON")  # keep climbs' FK pointing at "routes"
        conn.execute("ALTER TABLE routes RENAME TO routes_v2")
    with open(os.path.join(APP_DIR, "schema.sql")) as f:
        conn.executescript(f.read())
    if old_routes:
        conn.execute("INSERT INTO routes (id, color, chain_number, created_at) SELECT id, color, chain_number, created_at FROM routes_v2")
        conn.execute("DROP TABLE routes_v2")
    for col in ("route_kind TEXT NOT NULL DEFAULT 'cesta'", "route_name TEXT", "points INTEGER", "catalog_route_id TEXT"):
        if col.split()[0] not in table_cols(conn, "climbs"):
            conn.execute(f"ALTER TABLE climbs ADD COLUMN {col}")
    if seed and not conn.execute("SELECT 1 FROM groups").fetchone():
        names = {1: ["Malí horolezci", "Skalní veverky", "Pokročilí"],
                 2: ["Malí horolezci", "Starteři", "Pokročilí"],
                 3: ["Malí horolezci", "Starteři", "Pokročilí"],
                 4: ["Malí horolezci", "Starteři", "Připravená parta"]}
        times = [("14:30", "16:00"), ("16:00", "17:30"), ("17:30", "19:00")]
        for day, ns in names.items():
            for name, (s, e) in zip(ns, times):
                conn.execute("INSERT INTO groups VALUES (?,?,?,?,?,?)", (new_id(), name, day, s, e, now_iso()))
    conn.commit()


@app.cli.command("init-db")
def init_db_cmd():
    """Create tables and the default 12 groups."""
    conn = sqlite3.connect(DB_PATH)
    init_db(conn)
    print(f"Database ready: {DB_PATH}")


# ---------- domain logic ----------

def points_for_style(style):
    return STYLE_POINTS.get(style or "", 0)


def points_for_climb(c):
    """Traverz 5, boulder its stored points, rope route by style."""
    if c["route_kind"] == "traverz":
        return TRAVERSE_POINTS
    if c["route_kind"] == "boulder":
        return c["points"] or 0
    return points_for_style(c["style"])


def route_key(c):
    kind = c["route_kind"] or "cesta"
    rid = c["catalog_route_id"] or c["route_id"]
    if kind != "cesta" and rid:
        return f"r:{rid}"
    if c["route_name"] or (c["route_color"] and c["chain_number"]):
        return f"{kind}:{c['route_color'] or ''}#{c['chain_number'] or 0}#{c['route_name'] or ''}"
    if c["route_id"]:
        return f"r:{c['route_id']}"
    return f"c:{c['id']}"


def total_points(climbs):
    """Each route counts once per child, with its best style (lead 4 > top rope 2)."""
    best = {}
    for c in climbs:
        k = route_key(c)
        best[k] = max(best.get(k, 0), points_for_climb(c))
    return sum(best.values())


def route_label(r):
    """Name, or colour · number; falls back to the kind name."""
    parts = " · ".join(str(x) for x in (r["color"], r["chain_number"] or "") if x)
    if r["name"]:
        return f"{r['name']} ({parts})" if parts else r["name"]
    return parts or {"boulder": "Boulder", "traverz": "Traverz"}.get(r["kind"], "Cesta")


def week_start(d=None):
    """Monday of the calendar week (Prague time)."""
    d = d or datetime.now(TZ).date()
    return (d - timedelta(days=d.weekday())).isoformat()


def photo_ext(data):
    """jpg/png/webp from the file's magic bytes, else None."""
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def remove_photo(path):
    if path:
        try:
            os.remove(os.path.join(PHOTO_DIR, os.path.basename(path)))
        except FileNotFoundError:
            pass


def level_for_years(years):
    if years is None:
        return None
    if years > 4:
        return "master"
    if years > 2:
        return "mírně pokročilé"
    return "začátečník"


def lezik_label(n):
    if n == 1:
        return "lezík"
    if 2 <= n <= 4:
        return "lezíky"
    return "lezíků"


def cesty_word(n):
    if n == 1:
        return "cesta"
    if 2 <= n <= 4:
        return "cesty"
    return "cest"


def current_challenge():
    ch = q1("SELECT * FROM lezik_challenges ORDER BY starts_on DESC, created_at DESC LIMIT 1")
    if not ch:
        return None, []
    tasks = [dict(t, levels=json.loads(t["levels"]))
             for t in q("SELECT * FROM lezik_tasks WHERE challenge_id=? ORDER BY position", ch["id"])]
    return ch, tasks


def child_stats():
    """{child_id: (climb_count, points, lezik)} for every child."""
    climbs = {}
    for c in q("""SELECT id, child_id, route_id, route_color, chain_number, style, route_kind, route_name, points,
                         catalog_route_id FROM climbs"""):
        climbs.setdefault(c["child_id"], []).append(c)
    lezik = {r["child_id"]: r["s"] for r in q("""SELECT child_id, SUM(reward) s FROM (
        SELECT child_id, reward FROM lezik_completions UNION ALL SELECT child_id, reward FROM lezik_weekly_bonuses
    ) GROUP BY child_id""")}
    ids = set(climbs) | set(lezik)
    return {i: (len(climbs.get(i, [])), total_points(climbs.get(i, [])), lezik.get(i, 0)) for i in ids}


def today_weekday():
    return datetime.now(TZ).isoweekday()  # 1=Mon..7=Sun, groups use 1..4


# ---------- request guards ----------

@app.before_request
def guard():
    # Optional shared password (HTTP basic auth). The original app had no login.
    pw = os.environ.get("APP_PASSWORD")
    if pw:
        auth = request.authorization
        if not auth or auth.password != pw:
            return "Přihlášení vyžadováno", 401, {"WWW-Authenticate": 'Basic realm="HC4"'}
    # Block cross-site form posts (browsers re-send basic auth credentials cross-site).
    if request.method == "POST":
        src = request.headers.get("Origin") or request.headers.get("Referer")
        if src and urlparse(src).netloc != request.host:
            abort(403)


# ---------- form helpers ----------

def form_int(name, lo, hi):
    """Integer from form within [lo, hi], or None when missing/invalid."""
    try:
        v = int(request.form.get(name, ""))
    except ValueError:
        return None
    return v if lo <= v <= hi else None


def child_form():
    """Validated child fields from the add/edit form, or None (with a flash)."""
    name = request.form.get("first_name", "").strip()[:60]
    gender = request.form.get("gender")
    birth = form_int("birth_year", 1940, date.today().year)
    years = form_int("climbing_years", 0, 60)
    if not name or gender not in ("kluk", "holka") or birth is None or years is None:
        flash("Vyplňte jméno, rok narození a kolik let leze", "error")
        return None
    return dict(first_name=name, gender=gender, birth_year=birth, climbing_years=years, level=level_for_years(years))


# ---------- pages ----------

@app.get("/")
def index():
    today = today_weekday()
    day = request.args.get("day", type=int) or (today if 1 <= today <= 4 else 1)
    if not 1 <= day <= 4:
        day = 1
    groups = q("SELECT * FROM groups WHERE weekday=? ORDER BY start_time", day)
    return render_template("index.html", day=day, today=today, groups=groups,
                           prev_day=(day - 2) % 4 + 1, next_day=day % 4 + 1)


@app.get("/skupina/<group_id>")
def group_detail(group_id):
    group = q1("SELECT * FROM groups WHERE id=?", group_id) or abort(404)
    children = q("SELECT * FROM children WHERE group_id=? ORDER BY first_name", group_id)
    climbs = q("""SELECT climbs.*, children.first_name FROM climbs JOIN children ON children.id = climbs.child_id
                  WHERE climbs.group_id=? ORDER BY climbed_at DESC LIMIT 15""", group_id)
    n_climbs = q1("SELECT COUNT(*) n FROM climbs WHERE group_id=?", group_id)["n"]
    return render_template("group.html", group=group, children=children, climbs=climbs,
                           n_climbs=n_climbs, stats=child_stats())


@app.post("/skupina/<group_id>/deti")
def add_child(group_id):
    q1("SELECT 1 FROM groups WHERE id=?", group_id) or abort(404)
    f = child_form()
    if f:
        run("""INSERT INTO children (id, group_id, first_name, gender, birth_year, climbing_years, level, created_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            new_id(), group_id, f["first_name"], f["gender"], f["birth_year"], f["climbing_years"], f["level"], now_iso())
        flash("Dítě přidáno")
    return redirect(url_for("group_detail", group_id=group_id))


@app.get("/deti")
def children_page():
    children = q("""SELECT children.*, groups.weekday, groups.start_time FROM children
                    LEFT JOIN groups ON groups.id = children.group_id ORDER BY first_name""")
    return render_template("children.html", children=children, stats=child_stats())


@app.get("/dite/<child_id>")
def child_detail(child_id):
    child = q1("""SELECT children.*, groups.weekday, groups.start_time, groups.end_time FROM children
                  LEFT JOIN groups ON groups.id = children.group_id WHERE children.id=?""", child_id) or abort(404)
    climbs = q("SELECT * FROM climbs WHERE child_id=? ORDER BY climbed_at DESC", child_id)
    done = q("SELECT * FROM lezik_completions WHERE child_id=? ORDER BY completed_at DESC", child_id)
    bonuses = q("SELECT * FROM lezik_weekly_bonuses WHERE child_id=?", child_id)
    bonus = next((b for b in bonuses if b["week_start"] == week_start()), None)
    kind = request.args.get("druh") if request.args.get("druh") in KINDS else "cesta"

    # Routes the child has not finished (on lead) first (same order as the original).
    styles = {}
    for c in climbs:
        if (c["route_kind"] or "cesta") != kind:
            continue
        if kind != "cesta":
            styles.setdefault(c["catalog_route_id"] or c["route_id"], set()).add(c["style"])
        elif c["route_color"] and c["chain_number"]:
            styles.setdefault(f"{c['route_color']}#{c['chain_number']}", set()).add(c["style"])
    def rank(r):
        s = styles.get(r["id"] if kind != "cesta" else f"{r['color']}#{r['chain_number']}", set())
        return 2 if s & {"na prvním", "hotovo", "top"} else 1 if "top rope" in s else 0
    routes = sorted(({**dict(r), "rank": rank(r)}
                     for r in q("SELECT * FROM routes WHERE kind=? ORDER BY chain_number, color, name", kind)),
                    key=lambda r: r["rank"])

    challenge, tasks = current_challenge()
    done_ids = {d["task_id"] for d in done}
    done_in_challenge = sum(1 for t in tasks if t["id"] in done_ids)
    lvl = child["level"] or "začátečník"
    for t in tasks:
        t["done"] = t["id"] in done_ids
        t["wrong_level"] = not t["done"] and bool(t["levels"]) and lvl not in t["levels"]
        t["locked"] = not t["done"] and (t["wrong_level"] or done_in_challenge >= LEZIK_MAX_PER_CHALLENGE)

    lezik = list(done) + [{"task_title": "Týdenní bonus", "reward": b["reward"], "completed_at": b["updated_at"]}
                          for b in bonuses]
    history = sorted([("climb", c["climbed_at"], c) for c in climbs] + [("lezik", d["completed_at"], d) for d in lezik],
                     key=lambda h: h[1], reverse=True)
    return render_template("child.html", child=child, routes=routes, kind=kind, tasks=tasks, challenge=challenge,
                           done_in_challenge=done_in_challenge, history=history, bonus=bonus,
                           points=total_points(climbs), lezik_total=sum(d["reward"] for d in lezik))


@app.post("/dite/<child_id>/smazat")
def delete_child(child_id):
    child = q1("SELECT * FROM children WHERE id=?", child_id) or abort(404)
    run("DELETE FROM children WHERE id=?", child_id)  # climbs, lezíky and bonuses cascade
    flash("Dítě odebráno")
    return redirect(url_for("group_detail", group_id=child["group_id"]))


@app.post("/dite/<child_id>/bonus")
def toggle_bonus(child_id):
    """Weekly BONUS: one entry per child and week (1–4 lezíky); posting again cancels it."""
    q1("SELECT 1 FROM children WHERE id=?", child_id) or abort(404)
    week = week_start()
    if q1("SELECT 1 FROM lezik_weekly_bonuses WHERE child_id=? AND week_start=?", child_id, week):
        run("DELETE FROM lezik_weekly_bonuses WHERE child_id=? AND week_start=?", child_id, week)
        flash("Bonus zrušen")
    else:
        reward = form_int("reward", 1, WEEKLY_BONUS_MAX)
        if reward is None:
            flash(f"Bonus může být 1 až {WEEKLY_BONUS_MAX} lezíky", "error")
        else:
            run("INSERT INTO lezik_weekly_bonuses VALUES (?,?,?,?,?,?)", new_id(), child_id, week, reward, now_iso(), now_iso())
            flash(f"+{reward} {lezik_label(reward)}")
    return redirect(url_for("child_detail", child_id=child_id))


@app.post("/dite/<child_id>")
def edit_child(child_id):
    q1("SELECT 1 FROM children WHERE id=?", child_id) or abort(404)
    f = child_form()
    if f:
        run("UPDATE children SET first_name=?, gender=?, birth_year=?, climbing_years=?, level=? WHERE id=?",
            f["first_name"], f["gender"], f["birth_year"], f["climbing_years"], f["level"], child_id)
        flash("Údaje upraveny")
    return redirect(url_for("child_detail", child_id=child_id))


@app.post("/dite/<child_id>/cesta")
def log_climb(child_id):
    child = q1("SELECT * FROM children WHERE id=?", child_id) or abort(404)
    route = q1("SELECT * FROM routes WHERE id=?", request.form.get("route_id", ""))
    style = request.form.get("style")
    if not route or style not in (KIND_STYLE.get(route["kind"]) or STYLES):
        flash("Vyberte cestu a styl", "error")
        return redirect(url_for("child_detail", child_id=child_id))
    kind = route["kind"]
    url = url_for("child_detail", child_id=child_id, druh=kind)
    if kind == "cesta":
        prev = {r["style"] for r in q("""SELECT style FROM climbs WHERE child_id=? AND route_kind='cesta'
                                         AND route_color=? AND chain_number=?""",
                                      child_id, route["color"], route["chain_number"])}
    else:
        prev = {r["style"] for r in q("SELECT style FROM climbs WHERE child_id=? AND catalog_route_id=?", child_id, route["id"])}
    if style in prev:
        flash(f"Tuhle cestu už má zapsanou ({style})" if kind == "cesta" else "Tohle už má zapsané", "error")
    elif style == "top rope" and "na prvním" in prev:
        flash("Tuhle cestu už vylezl/a na prvním", "error")
    else:
        points = {"traverz": TRAVERSE_POINTS, "boulder": route["points"] or 0}.get(kind)
        run("""INSERT INTO climbs (id, child_id, group_id, route_id, route_color, chain_number, style, climbed_at,
                                   route_kind, route_name, points, catalog_route_id)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            new_id(), child_id, child["group_id"], route["id"], route["color"], route["chain_number"], style, now_iso(),
            kind, route["name"] or None, points, route["id"] if kind != "cesta" else None)
        label = {"na prvním": "Lead", "top rope": "Top Rope", "hotovo": "Hotovo", "top": "Top"}[style]
        flash(f"{route_label(route)} · {label} zapsáno")
    return redirect(url)


@app.post("/dite/<child_id>/cesta/zrusit")
def undo_climb(child_id):
    route = q1("SELECT * FROM routes WHERE id=?", request.form.get("route_id", ""))
    style = request.form.get("style")
    if route and route["kind"] != "cesta":
        run("DELETE FROM climbs WHERE child_id=? AND catalog_route_id=?", child_id, route["id"])
        flash("Zápis zrušen")
    elif route and style in STYLES:
        run("DELETE FROM climbs WHERE child_id=? AND route_kind='cesta' AND route_color=? AND chain_number=? AND style=?",
            child_id, route["color"], route["chain_number"], style)
        flash("Zápis zrušen")
    return redirect(url_for("child_detail", child_id=child_id, druh=route["kind"] if route else None))


@app.post("/dite/<child_id>/lezik/<task_id>")
def toggle_lezik(child_id, task_id):
    child = q1("SELECT * FROM children WHERE id=?", child_id) or abort(404)
    url = url_for("child_detail", child_id=child_id)
    existing = q1("SELECT id FROM lezik_completions WHERE child_id=? AND task_id=?", child_id, task_id)
    if existing:
        run("DELETE FROM lezik_completions WHERE id=?", existing["id"])
        flash("Splnění zrušeno")
        return redirect(url)
    _, tasks = current_challenge()
    task = next((t for t in tasks if t["id"] == task_id), None)
    if not task:
        abort(404)
    done = sum(1 for t in tasks if q1("SELECT 1 FROM lezik_completions WHERE child_id=? AND task_id=?", child_id, t["id"]))
    if done >= LEZIK_MAX_PER_CHALLENGE:
        flash(f"V této výzvě lze splnit jen {LEZIK_MAX_PER_CHALLENGE} úkoly", "error")
    elif task["levels"] and (child["level"] or "začátečník") not in task["levels"]:
        flash(f"Jen pro: {', '.join(task['levels'])}", "error")
    else:
        run("INSERT INTO lezik_completions VALUES (?,?,?,?,?,?)",
            new_id(), child_id, task_id, task["title"], task["reward"], now_iso())
        flash(f"+{task['reward']} {lezik_label(task['reward'])}")
    return redirect(url)


@app.route("/cesty", methods=["GET", "POST"])
def routes_page():
    if request.method == "POST":
        kind = request.form.get("kind") if request.form.get("kind") in KINDS else "cesta"
        add_route(kind)
        return redirect(url_for("routes_page", druh=kind))
    kind = request.args.get("druh") if request.args.get("druh") in KINDS else "cesta"
    return render_template("routes.html", kind=kind,
                           routes=q("SELECT * FROM routes WHERE kind=? ORDER BY chain_number, color, name", kind))


def add_route(kind):
    color = request.form.get("color", "")
    name = request.form.get("name", "").strip()[:80] if kind == "traverz" else ""
    desc = request.form.get("description", "").strip()[:300] if kind != "cesta" else ""
    n = form_int("chain_number", 1, 999) if kind == "cesta" else 0
    pts = form_int("points", 1, 100) if kind == "boulder" else None
    photo = request.files.get("photo") if kind == "boulder" else None
    data = photo.read(PHOTO_MAX_BYTES + 1) if photo and photo.filename else b""
    ext = photo_ext(data)
    if color and color not in ROUTE_COLORS:
        flash("Neznámá barva", "error")
    elif kind == "cesta" and (not color or n is None):
        flash("Vyberte barvu a zadejte číslo", "error")
    elif kind == "traverz" and not name and not color:
        flash("Napište název nebo vyberte barvu", "error")
    elif kind == "boulder" and pts is None:
        flash("Zadejte počet bodů za boulder", "error")
    elif data and not ext:
        flash("Vyberte fotku JPG, PNG nebo WebP", "error")
    elif len(data) > PHOTO_MAX_BYTES:
        flash("Fotka může mít nejvýše 10 MB", "error")
    elif kind != "boulder" and q1("SELECT 1 FROM routes WHERE kind=? AND color=? AND chain_number=? AND name=?",
                                  kind, color, n, name):
        flash("Toto už v seznamu je", "error")
    else:
        path = None
        if data:
            os.makedirs(PHOTO_DIR, exist_ok=True)
            path = f"{uuid.uuid4()}.{ext}"
            with open(os.path.join(PHOTO_DIR, path), "wb") as f:
                f.write(data)
        try:
            run("""INSERT INTO routes (id, color, chain_number, created_at, kind, points, name, photo_path, description)
                   VALUES (?,?,?,?,?,?,?,?,?)""", new_id(), color, n, now_iso(), kind, pts, name, path, desc or None)
        except sqlite3.Error:
            remove_photo(path)
            raise
        flash("Přidáno")


@app.post("/cesty/<route_id>/smazat")
def delete_route(route_id):
    route = q1("SELECT * FROM routes WHERE id=?", route_id) or abort(404)
    run("DELETE FROM routes WHERE id=?", route_id)  # climbs keep color + chain / catalog id, route_id becomes NULL
    remove_photo(route["photo_path"])
    flash("Odebráno")
    return redirect(url_for("routes_page", druh=route["kind"]))


@app.get("/foto/<name>")
def photo(name):
    return send_from_directory(PHOTO_DIR, name, max_age=30 * 24 * 3600)  # names are random uuids, never reused


def task_rows():
    """Task rows from the challenge form: [(task_id or '', title, reward, levels)]."""
    rows = []
    for i in range(MAX_TASKS):
        title = request.form.get(f"title-{i}", "").strip()[:200]
        try:
            reward = min(100, max(1, int(request.form.get(f"reward-{i}", "1"))))
        except ValueError:
            reward = 1
        levels = [l for l in request.form.getlist(f"levels-{i}") if l in LEVELS]
        rows.append((request.form.get(f"id-{i}", ""), title, reward, levels))
    return rows


def challenge_dates():
    try:
        start = date.fromisoformat(request.form.get("starts_on", ""))
    except ValueError:
        start = date.today()
    return start.isoformat(), (start + timedelta(days=13)).isoformat()


@app.get("/lezik")
def lezik_page():
    challenge, tasks = current_challenge()
    return render_template("lezik.html", challenge=challenge, tasks=tasks, today=date.today().isoformat())


@app.post("/lezik")
def create_challenge():
    rows = [r for r in task_rows() if r[1]]
    if not rows:
        flash("Zadejte aspoň jeden úkol", "error")
        return redirect(url_for("lezik_page"))
    start, end = challenge_dates()
    cid = new_id()
    conn = db()
    with conn:
        conn.execute("INSERT INTO lezik_challenges VALUES (?,?,?,?,?)",
                     (cid, request.form.get("title", "").strip()[:200], start, end, now_iso()))
        for pos, (_, title, reward, levels) in enumerate(rows):
            conn.execute("INSERT INTO lezik_tasks VALUES (?,?,?,?,?,?)",
                         (new_id(), cid, title, reward, json.dumps(levels, ensure_ascii=False), pos))
    flash("Nová výzva vyhlášena")
    return redirect(url_for("lezik_page"))


@app.post("/lezik/<challenge_id>")
def edit_challenge(challenge_id):
    q1("SELECT 1 FROM lezik_challenges WHERE id=?", challenge_id) or abort(404)
    rows = task_rows()
    if not any(r[1] for r in rows):
        flash("Výzva musí mít aspoň jeden úkol", "error")
        return redirect(url_for("lezik_page"))
    start, end = challenge_dates()
    conn = db()
    with conn:
        conn.execute("UPDATE lezik_challenges SET title=?, starts_on=?, ends_on=? WHERE id=?",
                     (request.form.get("title", "").strip()[:200], start, end, challenge_id))
        for pos, (tid, title, reward, levels) in enumerate(rows):
            lv = json.dumps(levels, ensure_ascii=False)
            if tid and not title:  # removed row; children keep lezíky already earned
                conn.execute("DELETE FROM lezik_tasks WHERE id=? AND challenge_id=?", (tid, challenge_id))
            elif tid:
                conn.execute("UPDATE lezik_tasks SET title=?, reward=?, levels=?, position=? WHERE id=? AND challenge_id=?",
                             (title, reward, lv, pos, tid, challenge_id))
            elif title:
                conn.execute("INSERT INTO lezik_tasks VALUES (?,?,?,?,?,?)", (new_id(), challenge_id, title, reward, lv, pos))
    flash("Výzva upravena")
    return redirect(url_for("lezik_page"))


@app.post("/lezik/<challenge_id>/smazat")
def delete_challenge(challenge_id):
    # tasks cascade; completions keep their lezíky (task_id -> NULL)
    run("DELETE FROM lezik_challenges WHERE id=?", challenge_id)
    flash("Výzva smazána")
    return redirect(url_for("lezik_page"))


# ---------- template helpers ----------

def fmt_date(s, short=False):
    d = datetime.fromisoformat(s)
    if d.tzinfo:
        d = d.astimezone(TZ)
    return f"{d.day}. {d.month}." if short else f"{d.day}. {d.month}. {d.year}"


app.jinja_env.filters["date"] = fmt_date
app.jinja_env.globals.update(
    WEEKDAYS_CS=WEEKDAYS_CS, WEEKDAYS_SHORT=WEEKDAYS_SHORT, LEVELS=LEVELS, SLOTS=SLOTS, STYLES=STYLES,
    STYLE_POINTS=STYLE_POINTS, ROUTE_COLORS=ROUTE_COLORS, MAX_TASKS=MAX_TASKS, LEZIK_MAX=LEZIK_MAX_PER_CHALLENGE,
    KINDS=KINDS, KIND_STYLE=KIND_STYLE, STYLE_LABELS=STYLE_LABELS, TRAVERSE_POINTS=TRAVERSE_POINTS,
    WEEKLY_BONUS_MAX=WEEKLY_BONUS_MAX, route_label=route_label,
    lezik_label=lezik_label, cesty_word=cesty_word, points_for_climb=points_for_climb,
    level_class=lambda l: {"mírně pokročilé": "mid", "master": "master"}.get(l or "", "beginner"),
    color_hex=lambda c: ROUTE_COLORS.get(c or "", "#e5e7eb"),
    this_year=lambda: date.today().year,
)

if __name__ == "__main__":
    if not os.path.exists(DB_PATH):
        init_db(sqlite3.connect(DB_PATH))
    app.run(debug=True)
