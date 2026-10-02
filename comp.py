"""Timed speed-drill competition ("Pit Stop Sprint"). No student data here.
Windows are per class group, in SGT. Nothing is visible to students unless CONFIRMED is True
AND the student's class window is open right now."""
from datetime import datetime, timedelta, timezone

SGT = timezone(timedelta(hours=8))

NAME = "Pit Stop Sprint"
TAGLINE = "How many laps can you stack before the chequered flag?"
BLURB = ("Finish as many different speed drills as you can, as fast as you can. "
         "Each drill is one lap. Retry a drill to beat your own time, and it still counts as one lap. "
         "Stuck? Read the message, tweak, run again. Have fun with it.")
DEFINE = [
    ("Drill", "one exercise, for example Bubble sort or Stack."),
    ("Lap", "one different drill you finish with all checks passing. Doing the same drill again is still one lap."),
]
RULES = [
    "Press Start when you are ready. You get 75 minutes. If your lesson ends sooner, your clock stops at the end of your lesson.",
    "A drill only counts if you start it and finish it while your clock is running. Anything started before you press Start, or finished after your clock ends, does not count.",
    "Ranking: most laps first. If laps are tied, the higher partial credit wins. If still tied, the lowest total time wins.",
    "Total time is the sum of your best time on each drill you finished. A faster retry replaces your old time for that drill.",
    "Partial credit: on a drill you have not finished, the checks you pass still earn a share of one point. The checks run in order and stop at the first one that fails, so it is only a rough guide, and some short drills give none. It only breaks ties.",
    "Your teacher can adjust partial credit, and a drill under teacher review is left off the board until it is cleared.",
]
EXAMPLE_TITLE = "Example"
EXAMPLE = [
    "Mia finishes Bubble sort in 2:10, Linear search in 1:30 and Stack in 3:00. That is 3 laps, total 6:40.",
    "She retries Bubble sort and does it in 1:50. Still 3 laps, but her total drops to 6:20.",
    "Sam finishes 4 drills in a total of 14:00. Sam ranks above Mia: 4 laps beats 3, even though Sam's total is longer.",
    "Leo also finishes 3 drills, in a slower 7:00, but has partial credit 0.4 on a 4th. Mia has 0.2. Leo ranks above Mia: laps are tied, so partial credit decides before time.",
]

# Set True only when the teacher has confirmed the windows.
CONFIRMED = False
PERSONAL_MIN = 75

def _w(day, a, b):
    return (datetime.fromisoformat(f"{day}T{a}:00").replace(tzinfo=SGT),
            datetime.fromisoformat(f"{day}T{b}:00").replace(tzinfo=SGT))

# Lesson windows as confirmed by the teacher: 25S21 12:30-14:00, 25S11+25S22 14:00-15:30 (2 Oct 2026, SGT).
# Each student starts their own PERSONAL_MIN clock after joining; it is capped at the class cutoff.
WINDOWS = [
    {"label": "25S21", "classes": ("25S21",), "start": _w("2026-10-02", "12:30", "14:00")[0], "end": _w("2026-10-02", "12:30", "14:00")[1]},
    {"label": "25S11 + 25S22", "classes": ("25S11", "25S22"), "start": _w("2026-10-02", "14:00", "15:30")[0], "end": _w("2026-10-02", "14:00", "15:30")[1]},
]

def window_for_class(cls):
    for w in WINDOWS:
        if cls in w["classes"]:
            return w
    return None

def state(w, now):
    if not CONFIRMED:
        return "pending"
    if now < w["start"]:
        return "upcoming"
    return "open" if now < w["end"] else "closed"

def student_window(cls, now):
    """The window to show a student right now, or None (not their class, not confirmed, or outside the window)."""
    w = window_for_class(cls)
    return w if w and state(w, now) == "open" else None

def personal_end(w, joined):
    return min(joined + timedelta(minutes=PERSONAL_MIN), w["end"])

def get_join(db, uid):
    r = db.execute("SELECT joined_at FROM comp_joins WHERE user_id=?", (uid,)).fetchone()
    return datetime.fromisoformat(r["joined_at"]).astimezone(SGT) if r else None

def standings(db, roster_lookup, norm_email):
    """One board across classes. A valid attempt = passed, unflagged (or cleared) attempt that started and finished
    inside that student's own clock (joined_at to min(joined_at + 75 min, class cutoff))."""
    roster = roster_lookup(db)
    rows = db.execute(
        """SELECT a.id, a.user_id, a.algo, a.elapsed_ms, a.started_at, a.finished_at, u.name, u.email
           FROM speed_attempts a JOIN users u ON u.id=a.user_id
           WHERE a.passed=1 AND (a.flagged=0 OR a.cleared=1) AND u.role='student' ORDER BY a.finished_at, a.id""").fetchall()
    joins = {r["user_id"]: datetime.fromisoformat(r["joined_at"]).astimezone(SGT)
             for r in db.execute("SELECT user_id, joined_at FROM comp_joins")}
    ovr = {r["user_id"]: r for r in db.execute("SELECT user_id, partial, note FROM comp_override")}
    per = {}
    def _slot(uid, rn, name, rc):
        return per.setdefault(uid, {"uid": uid, "name": rn or name or "Student", "cls": rc, "bests": {}, "pbest": {}})
    for r in rows:
        rn, rc = roster.get(norm_email(r["email"]), (None, None))
        w = window_for_class(rc)
        if not w:
            continue
        s = datetime.fromisoformat(r["started_at"]); f = datetime.fromisoformat(r["finished_at"])
        j = joins.get(r["user_id"])
        if j is None or j < w["start"] or j >= w["end"]:
            continue
        if s < j or f > personal_end(w, j):
            continue
        p = _slot(r["user_id"], rn, r["name"], rc)
        cur = p["bests"].get(r["algo"])
        if cur is None or r["elapsed_ms"] < cur:
            p["bests"][r["algo"]] = r["elapsed_ms"]
    # Automatic partial credit: best check progress (0-1) on a drill the student has not finished inside their clock.
    for r in db.execute(
            """SELECT a.user_id, a.algo, a.ck_frac, a.started_at, a.ck_at, u.name, u.email FROM speed_attempts a
               JOIN users u ON u.id=a.user_id
               WHERE a.passed=0 AND a.ck_frac>0 AND (a.flagged=0 OR a.cleared=1) AND u.role='student'""").fetchall():
        rn, rc = roster.get(norm_email(r["email"]), (None, None))
        w = window_for_class(rc); j = joins.get(r["user_id"])
        if not w or j is None or j < w["start"] or j >= w["end"] or not r["ck_at"]:
            continue
        if datetime.fromisoformat(r["started_at"]) < j or datetime.fromisoformat(r["ck_at"]) > personal_end(w, j):
            continue
        p = _slot(r["user_id"], rn, r["name"], rc)
        p["pbest"][r["algo"]] = max(p["pbest"].get(r["algo"], 0), r["ck_frac"])
    for p in per.values():
        p["drills"] = len(p["bests"]); p["total"] = sum(p["bests"].values())
        p["auto"] = round(sum(v for k, v in p["pbest"].items() if k not in p["bests"]), 2)
        o = ovr.get(p["uid"])
        p["override"] = o["partial"] if o else None
        p["partial"] = o["partial"] if o else p["auto"]
    for uid, o in ovr.items():
        if uid not in per:
            u = db.execute("SELECT name, email FROM users WHERE id=?", (uid,)).fetchone()
            if u:
                rn, rc = roster.get(norm_email(u["email"]), (None, None))
                if window_for_class(rc):
                    p = _slot(uid, rn, u["name"], rc)
                    p.update(drills=0, total=0, auto=0, override=o["partial"], partial=o["partial"])
    board = sorted(per.values(), key=lambda p: (-p["drills"], -p["partial"], p["total"], p["name"]))
    for i, p in enumerate(board, 1):
        p["rank"] = i
    return board
