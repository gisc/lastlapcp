"""Last Day Drill: an open, no-clock board over the 19 speed drills. No student data here.
Every roster student of the listed classes appears, attempted or not. A drill tile is coloured by the
student's fastest valid finish inside the window (green within the drill's limit, orange up to 1 minute over,
red beyond, grey = not finished yet)."""
from datetime import datetime, timedelta, timezone

SGT = timezone(timedelta(hours=8))
NAME = "Last Day Drill"
TAGLINE = "Finish every drill you can before the window closes. Tiles show how fast you were."
# Window: opens when this goes live, closes 22:00 SGT on Tuesday 6 October 2026.
OPENS = datetime.fromisoformat("2026-10-05T11:30:00").replace(tzinfo=SGT)
CLOSES = datetime.fromisoformat("2026-10-06T22:00:00").replace(tzinfo=SGT)
CLASS_ORDER = ("25S11", "25S21", "25S22")
CONFIRMED = True

RULES = [
    "Open from now until 10:00 pm on Tuesday 6 October. There is no personal clock: take as long as you need on each drill.",
    "Each of the 19 drills is one tile. Do a drill as normal on its own page and pass all the checks.",
    "A tile uses your fastest finish for that drill in this window. Green: within the drill's limit (5 minutes, or 8 for the two binary search trees). Orange: up to 1 minute over. Red: more than 1 minute over. Grey: not finished yet.",
    "You can retry a drill. A faster finish replaces the colour of your old one.",
    "Attempts held for teacher review are left off until your teacher clears them.",
]

def is_open(now):
    return CONFIRMED and OPENS <= now < CLOSES

def board(db, roster_lookup, norm_email, algos, tile_band):
    """Rows for every roster student in CLASS_ORDER: class order first, then (greens, oranges, reds, total time)."""
    roster = roster_lookup(db)
    emails = {e: (n, c) for e, (n, c) in roster.items() if c in CLASS_ORDER}
    users = {norm_email(r["email"]): r["id"] for r in db.execute("SELECT id, email FROM users WHERE role='student'")}
    best = {}
    for r in db.execute(
            """SELECT a.algo, a.elapsed_ms, a.started_at, a.finished_at, u.email FROM speed_attempts a
               JOIN users u ON u.id=a.user_id
               WHERE a.passed=1 AND (a.flagged=0 OR a.cleared=1) AND u.role='student' AND a.finished_at<>''""").fetchall():
        e = norm_email(r["email"])
        if e not in emails:
            continue
        try:
            s = datetime.fromisoformat(r["started_at"]); f = datetime.fromisoformat(r["finished_at"])
        except ValueError:
            continue
        if s < OPENS or f > CLOSES:
            continue
        d = best.setdefault(e, {})
        if r["algo"] not in d or r["elapsed_ms"] < d[r["algo"]]:
            d[r["algo"]] = r["elapsed_ms"]
    rows = []
    for e, (name, cls) in emails.items():
        b = best.get(e, {})
        tiles = [{"slug": a["slug"], "title": a["title"], "best": b.get(a["slug"]), "limit_min": a["limit_min"],
                  "band": tile_band(b.get(a["slug"]), a["limit_ms"])} for a in algos]
        cnt = {k: sum(1 for t in tiles if t["band"] == k) for k in ("green", "orange", "red")}
        rows.append({"uid": users.get(e), "email": e, "name": name or e, "cls": cls, "tiles": tiles,
                     "g": cnt["green"], "o": cnt["orange"], "r": cnt["red"], "done": sum(cnt.values()),
                     "total": sum(v for v in b.values())})
    rows.sort(key=lambda p: (CLASS_ORDER.index(p["cls"]), -p["g"], -p["o"], -p["r"], p["total"], p["name"].lower()))
    rk = {}
    for p in rows:
        rk[p["cls"]] = rk.get(p["cls"], 0) + 1
        p["rank"] = rk[p["cls"]]
    return rows
