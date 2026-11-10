"""Run: .venv/bin/python test_app.py"""
import os
import re
import tempfile

os.environ["HC4_DB"] = os.path.join(tempfile.mkdtemp(), "test.db")
import sqlite3

import app as hc4

hc4.init_db(sqlite3.connect(hc4.DB_PATH))
c = hc4.app.test_client()


def climb(color, chain, style, kind="cesta", **kw):
    return {"route_color": color, "chain_number": chain, "route_id": None, "id": "x", "style": style,
            "route_kind": kind, "route_name": None, "points": None, "catalog_route_id": None, **kw}


# points (ported from src/test/points.test.ts)
assert hc4.points_for_style("top rope") == 2 and hc4.points_for_style("na prvním") == 4
assert hc4.points_for_style("přelez") == 0 and hc4.points_for_style(None) == 0
assert hc4.total_points([climb("modrá", 5, "top rope")] * 2) == 2
assert hc4.total_points([climb("modrá", 5, "top rope"), climb("modrá", 5, "na prvním")]) == 4
# traverzy a bouldery (v3)
b = climb("modrá", 0, "top", "boulder", points=7, catalog_route_id="a")
assert hc4.total_points([b, b, climb("modrá", 0, "top", "boulder", points=3, catalog_route_id="b")]) == 10
assert hc4.points_for_climb(climb(None, 0, "hotovo", "traverz")) == 5
assert hc4.total_points([climb("modrá", 5, "na prvním"), climb("modrá", 5, "hotovo", "traverz")]) == 9
from datetime import date as _d
assert hc4.week_start(_d(2026, 11, 9)) == hc4.week_start(_d(2026, 11, 15)) == "2026-11-09"
assert hc4.week_start(_d(2026, 11, 16)) == "2026-11-16"
assert hc4.level_for_years(5) == "master" and hc4.level_for_years(3) == "mírně pokročilé" and hc4.level_for_years(0) == "začátečník"

# every page renders
assert c.get("/").status_code == 200
gid = re.search(r"/skupina/([\w-]+)", c.get("/?day=1").text).group(1)
assert c.get(f"/skupina/{gid}").status_code == 200

# add child, route, climbs
c.post(f"/skupina/{gid}/deti", data={"first_name": "Anna", "gender": "holka", "birth_year": "2016", "climbing_years": "3"})
cid = re.search(r"/dite/([\w-]+)", c.get(f"/skupina/{gid}").text).group(1)
c.post("/cesty", data={"color": "modrá", "chain_number": "5"})
assert "Toto už v seznamu je" in c.post("/cesty", data={"color": "modrá", "chain_number": "5"}, follow_redirects=True).text
rid = hc4.sqlite3.connect(hc4.DB_PATH).execute("SELECT id FROM routes").fetchone()[0]
c.post(f"/dite/{cid}/cesta", data={"route_id": rid, "style": "top rope"})
c.post(f"/dite/{cid}/cesta", data={"route_id": rid, "style": "na prvním"})
assert "už má zapsanou" in c.post(f"/dite/{cid}/cesta", data={"route_id": rid, "style": "top rope"}, follow_redirects=True).text
page = c.get(f"/dite/{cid}").text
assert "4 b" in page and "mírně pokročilé" in page

# lezík: create challenge with a master-only task, limit of 2
c.post("/lezik", data={"starts_on": "2026-11-01", "title-0": "A", "reward-0": "3", "title-1": "B", "reward-1": "1",
                       "title-2": "C", "reward-2": "2", "title-3": "M", "reward-3": "5", "levels-3": "master"})
db = sqlite3.connect(hc4.DB_PATH)
tasks = dict(db.execute("SELECT title, id FROM lezik_tasks").fetchall())
assert db.execute("SELECT ends_on FROM lezik_challenges").fetchone()[0] == "2026-11-14"
assert "Jen pro: master" in c.post(f"/dite/{cid}/lezik/{tasks['M']}", follow_redirects=True).text
c.post(f"/dite/{cid}/lezik/{tasks['A']}")
c.post(f"/dite/{cid}/lezik/{tasks['B']}")
assert "lze splnit jen 2" in c.post(f"/dite/{cid}/lezik/{tasks['C']}", follow_redirects=True).text
c.post(f"/dite/{cid}/lezik/{tasks['B']}")  # toggle off
assert db.execute("SELECT SUM(reward) FROM lezik_completions").fetchone()[0] == 3

# edit challenge: drop task A (earned lezíky stay), rename B
chid = db.execute("SELECT id FROM lezik_challenges").fetchone()[0]
c.post(f"/lezik/{chid}", data={"starts_on": "2026-11-01", "id-0": tasks["A"], "id-1": tasks["B"], "title-1": "B2", "reward-1": "1",
                              "id-2": tasks["C"], "title-2": "C", "id-3": tasks["M"], "title-3": "M", "levels-3": "master"})
assert db.execute("SELECT title FROM lezik_tasks ORDER BY position").fetchall() == [("B2",), ("C",), ("M",)]
assert db.execute("SELECT task_id, reward FROM lezik_completions").fetchall() == [(None, 3)]
for p in ["/deti", "/cesty", "/lezik", f"/dite/{cid}"]:
    assert c.get(p).status_code == 200, p

# cross-site post is rejected
assert c.post("/cesty", data={}, headers={"Origin": "https://evil.example"}).status_code == 403
print("ok")

# undo a logged climb (v2): lead undo leaves top rope, then top rope undo leaves nothing
c.post(f"/dite/{cid}/cesta/zrusit", data={"route_id": rid, "style": "na prvním"})
assert db.execute("SELECT style FROM climbs WHERE child_id=?", (cid,)).fetchall() == [("top rope",)]
c.post(f"/dite/{cid}/cesta/zrusit", data={"route_id": rid, "style": "top rope"})
assert db.execute("SELECT COUNT(*) FROM climbs").fetchone()[0] == 0

# delete challenge (v2): tasks gone, earned lezíky stay
c.post(f"/lezik/{chid}/smazat")
assert db.execute("SELECT COUNT(*) FROM lezik_challenges").fetchone()[0] == 0
assert db.execute("SELECT COUNT(*) FROM lezik_tasks").fetchone()[0] == 0
assert db.execute("SELECT reward FROM lezik_completions").fetchall() == [(3,)]
assert c.get("/lezik").status_code == 200
print("ok v2")

# v3: traverzy, bouldery with photos, weekly bonus, delete child
import io
c.post("/cesty", data={"kind": "traverz", "name": "Dlouhý", "color": "", "description": "zleva doprava"})
assert "Napište název" in c.post("/cesty", data={"kind": "traverz", "color": ""}, follow_redirects=True).text
png = b"\x89PNG\r\n\x1a\n" + b"0" * 100
c.post("/cesty", data={"kind": "boulder", "color": "modrá", "points": "7", "photo": (io.BytesIO(png), "a.png")},
       content_type="multipart/form-data")
c.post("/cesty", data={"kind": "boulder", "color": "modrá", "points": "3"})  # same colour is fine for bouldery
assert "JPG, PNG nebo WebP" in c.post("/cesty", data={"kind": "boulder", "points": "3", "photo": (io.BytesIO(b"<svg>"), "x.svg")},
                                      content_type="multipart/form-data", follow_redirects=True).text
boulders = db.execute("SELECT id, points, photo_path FROM routes WHERE kind='boulder' ORDER BY points").fetchall()
assert len(boulders) == 2 and boulders[1][2].endswith(".png")
assert c.get(f"/foto/{boulders[1][2]}").data == png
assert c.get("/foto/..%2Fhc4.db").status_code == 404
trav = db.execute("SELECT id FROM routes WHERE kind='traverz'").fetchone()[0]
for rid_, st in [(boulders[0][0], "top"), (boulders[1][0], "top"), (trav, "hotovo")]:
    c.post(f"/dite/{cid}/cesta", data={"route_id": rid_, "style": st})
assert "už má zapsané" in c.post(f"/dite/{cid}/cesta", data={"route_id": trav, "style": "hotovo"}, follow_redirects=True).text
assert c.post(f"/dite/{cid}/cesta", data={"route_id": trav, "style": "na prvním"}, follow_redirects=True).text.count("Vyberte cestu")
assert "15 b" in c.get(f"/dite/{cid}?druh=boulder").text
c.post(f"/cesty/{boulders[1][0]}/smazat")  # removing the boulder keeps the child's points and deletes the photo
assert not os.path.exists(os.path.join(hc4.PHOTO_DIR, boulders[1][2]))
assert "15 b" in c.get(f"/dite/{cid}?druh=traverz").text
c.post(f"/dite/{cid}/cesta/zrusit", data={"route_id": trav})
assert "10 b" in c.get(f"/dite/{cid}").text

assert "1 až 4" in c.post(f"/dite/{cid}/bonus", data={"reward": "5"}, follow_redirects=True).text
c.post(f"/dite/{cid}/bonus", data={"reward": "4"})
page = c.get(f"/dite/{cid}").text
assert "Týdenní bonus" in page and "7 lezíků" in page  # 3 from the challenge + 4 bonus
c.post(f"/dite/{cid}/bonus")  # second post cancels
assert db.execute("SELECT COUNT(*) FROM lezik_weekly_bonuses").fetchone()[0] == 0
for p in ["/cesty?druh=traverz", "/cesty?druh=boulder", f"/skupina/{gid}", "/deti"]:
    assert c.get(p).status_code == 200, p

c.post(f"/dite/{cid}/bonus", data={"reward": "2"})
c.post(f"/dite/{cid}/smazat")
assert db.execute("SELECT COUNT(*) FROM children").fetchone()[0] == 0
assert db.execute("SELECT COUNT(*) FROM climbs").fetchone()[0] == 0
assert db.execute("SELECT COUNT(*) FROM lezik_weekly_bonuses").fetchone()[0] == 0

# migration of a v2 database keeps routes and the climbs -> routes foreign key
old = sqlite3.connect(":memory:")
old.executescript("""
CREATE TABLE routes (id TEXT PRIMARY KEY, color TEXT NOT NULL, chain_number INTEGER NOT NULL, created_at TEXT NOT NULL, UNIQUE (color, chain_number));
CREATE TABLE climbs (id TEXT PRIMARY KEY, child_id TEXT, group_id TEXT, route_id TEXT REFERENCES routes(id) ON DELETE SET NULL,
  route_color TEXT, chain_number INTEGER, grade TEXT NOT NULL DEFAULT '', style TEXT NOT NULL, note TEXT, climbed_at TEXT NOT NULL);
INSERT INTO routes VALUES ('r1', 'modrá', 5, 'now');
INSERT INTO climbs (id, route_id, style, climbed_at) VALUES ('c1', 'r1', 'top rope', 'now');
""")
hc4.init_db(old, seed=False)
assert old.execute("SELECT kind, name FROM routes").fetchall() == [("cesta", "")]
assert old.execute("SELECT route_kind FROM climbs").fetchall() == [("cesta",)]
assert {r[2] for r in old.execute("PRAGMA foreign_key_list(climbs)")} == {"routes"}
old.execute("INSERT INTO routes (id, color, chain_number, created_at, kind) VALUES ('r2', 'modrá', 0, 'now', 'boulder')")
old.execute("INSERT INTO routes (id, color, chain_number, created_at, kind) VALUES ('r3', 'modrá', 0, 'now', 'boulder')")
hc4.init_db(old, seed=False)  # idempotent
print("ok v3")
