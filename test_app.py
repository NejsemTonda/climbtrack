"""Run: .venv/bin/python test_app.py"""
import os
import re
import tempfile

os.environ["HC4_DB"] = os.path.join(tempfile.mkdtemp(), "test.db")
import sqlite3

import app as hc4

hc4.init_db(sqlite3.connect(hc4.DB_PATH))
c = hc4.app.test_client()


def climb(color, chain, style):
    return {"route_color": color, "chain_number": chain, "route_id": None, "id": "x", "style": style}


# points (ported from src/test/points.test.ts)
assert hc4.points_for_style("top rope") == 2 and hc4.points_for_style("na prvním") == 4
assert hc4.points_for_style("přelez") == 0 and hc4.points_for_style(None) == 0
assert hc4.total_points([climb("modrá", 5, "top rope")] * 2) == 2
assert hc4.total_points([climb("modrá", 5, "top rope"), climb("modrá", 5, "na prvním")]) == 4
assert hc4.level_for_years(5) == "master" and hc4.level_for_years(3) == "mírně pokročilé" and hc4.level_for_years(0) == "začátečník"

# every page renders
assert c.get("/").status_code == 200
gid = re.search(r"/skupina/([\w-]+)", c.get("/?day=1").text).group(1)
assert c.get(f"/skupina/{gid}").status_code == 200

# add child, route, climbs
c.post(f"/skupina/{gid}/deti", data={"first_name": "Anna", "gender": "holka", "birth_year": "2016", "climbing_years": "3"})
cid = re.search(r"/dite/([\w-]+)", c.get(f"/skupina/{gid}").text).group(1)
c.post("/cesty", data={"color": "modrá", "chain_number": "5"})
assert "Tato cesta už v seznamu je" in c.post("/cesty", data={"color": "modrá", "chain_number": "5"}, follow_redirects=True).text
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
