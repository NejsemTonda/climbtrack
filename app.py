import json
import os
import sqlite3
import uuid
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from flask import Flask, abort, flash, g, redirect, render_template, request, url_for

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("HC4_DB", os.path.join(APP_DIR, "hc4.db"))
TZ = ZoneInfo("Europe/Prague")

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or os.urandom(32)

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


def init_db(conn, seed=True):
    with open(os.path.join(APP_DIR, "schema.sql")) as f:
        conn.executescript(f.read())
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


def route_key(c):
    if c["route_color"] and c["chain_number"]:
        return f"{c['route_color']}#{c['chain_number']}"
    if c["route_id"]:
        return f"r:{c['route_id']}"
    return f"c:{c['id']}"


def total_points(climbs):
    """Each route counts once per child, with its best style (lead 4 > top rope 2)."""
    best = {}
    for c in climbs:
        k = route_key(c)
        best[k] = max(best.get(k, 0), points_for_style(c["style"]))
    return sum(best.values())


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
    for c in q("SELECT id, child_id, route_id, route_color, chain_number, style FROM climbs"):
        climbs.setdefault(c["child_id"], []).append(c)
    lezik = {r["child_id"]: r["s"] for r in q("SELECT child_id, SUM(reward) s FROM lezik_completions GROUP BY child_id")}
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

    # Routes the child has not finished on lead first (same order as the original).
    styles = {}
    for c in climbs:
        if c["route_color"] and c["chain_number"]:
            styles.setdefault(f"{c['route_color']}#{c['chain_number']}", set()).add(c["style"])
    def rank(r):
        s = styles.get(f"{r['color']}#{r['chain_number']}", set())
        return 2 if "na prvním" in s else 1 if "top rope" in s else 0
    routes = sorted(({**dict(r), "rank": rank(r)} for r in q("SELECT * FROM routes ORDER BY chain_number, color")),
                    key=lambda r: r["rank"])

    challenge, tasks = current_challenge()
    done_ids = {d["task_id"] for d in done}
    done_in_challenge = sum(1 for t in tasks if t["id"] in done_ids)
    lvl = child["level"] or "začátečník"
    for t in tasks:
        t["done"] = t["id"] in done_ids
        t["wrong_level"] = not t["done"] and bool(t["levels"]) and lvl not in t["levels"]
        t["locked"] = not t["done"] and (t["wrong_level"] or done_in_challenge >= LEZIK_MAX_PER_CHALLENGE)

    history = sorted([("climb", c["climbed_at"], c) for c in climbs] + [("lezik", d["completed_at"], d) for d in done],
                     key=lambda h: h[1], reverse=True)
    return render_template("child.html", child=child, routes=routes, tasks=tasks, challenge=challenge,
                           done_in_challenge=done_in_challenge, history=history,
                           points=total_points(climbs), lezik_total=sum(d["reward"] for d in done))


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
    if not route or style not in STYLES:
        flash("Vyberte cestu a styl", "error")
        return redirect(url_for("child_detail", child_id=child_id))
    prev = {r["style"] for r in q("SELECT style FROM climbs WHERE child_id=? AND route_color=? AND chain_number=?",
                                  child_id, route["color"], route["chain_number"])}
    if style in prev:
        flash(f"Tuhle cestu už má zapsanou ({style})", "error")
    elif style == "top rope" and "na prvním" in prev:
        flash("Tuhle cestu už vylezl/a na prvním", "error")
    else:
        run("""INSERT INTO climbs (id, child_id, group_id, route_id, route_color, chain_number, style, climbed_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            new_id(), child_id, child["group_id"], route["id"], route["color"], route["chain_number"], style, now_iso())
        flash(f"{route['color']} {route['chain_number']} · {'Lead' if style == 'na prvním' else 'Top Rope'} zapsáno")
    return redirect(url_for("child_detail", child_id=child_id))


@app.post("/dite/<child_id>/cesta/zrusit")
def undo_climb(child_id):
    route = q1("SELECT * FROM routes WHERE id=?", request.form.get("route_id", ""))
    style = request.form.get("style")
    if route and style in STYLES:
        run("DELETE FROM climbs WHERE child_id=? AND route_color=? AND chain_number=? AND style=?",
            child_id, route["color"], route["chain_number"], style)
        flash("Zápis zrušen")
    return redirect(url_for("child_detail", child_id=child_id))


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
        color = request.form.get("color")
        n = form_int("chain_number", 1, 999)
        if color not in ROUTE_COLORS or n is None:
            flash("Vyberte barvu a zadejte číslo řetězu", "error")
        elif q1("SELECT 1 FROM routes WHERE color=? AND chain_number=?", color, n):
            flash("Tato cesta už v seznamu je", "error")
        else:
            run("INSERT INTO routes VALUES (?,?,?,?)", new_id(), color, n, now_iso())
            flash("Cesta přidána")
        return redirect(url_for("routes_page"))
    return render_template("routes.html", routes=q("SELECT * FROM routes ORDER BY chain_number, color"))


@app.post("/cesty/<route_id>/smazat")
def delete_route(route_id):
    run("DELETE FROM routes WHERE id=?", route_id)  # climbs keep color + chain, route_id becomes NULL
    flash("Cesta odebrána")
    return redirect(url_for("routes_page"))


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
    lezik_label=lezik_label, cesty_word=cesty_word, points_for_style=points_for_style,
    level_class=lambda l: {"mírně pokročilé": "mid", "master": "master"}.get(l or "", "beginner"),
    color_hex=lambda c: ROUTE_COLORS.get(c or "", "#e5e7eb"),
    this_year=lambda: date.today().year,
)

if __name__ == "__main__":
    if not os.path.exists(DB_PATH):
        init_db(sqlite3.connect(DB_PATH))
    app.run(debug=True)
