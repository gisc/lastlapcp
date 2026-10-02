"""Timed speed-drill competition ("Pit Stop Sprint"). No student data here.
Windows are per class group, in SGT. Nothing is visible to students unless CONFIRMED is True
AND the student's class window is open right now."""
from datetime import datetime, timedelta, timezone

SGT = timezone(timedelta(hours=8))

NAME = "Pit Stop Sprint"
TAGLINE = "How many laps can you stack before the chequered flag?"
BLURB = ("Every speed drill you finish is one lap. Play any drills, as often as you like. "
         "Your lap count on the board is all that matters, so a fast fix-and-retry beats a perfect first go. "
         "Stuck? Read the message, tweak, run again. Have fun with it.")
RULES = ["Press Start when you are ready. You get 75 minutes, or until the end of your lesson if that comes first.",
         "A lap is a drill whose checks all pass. Re-running and retrying is fine.",
         "Most laps tops the board. Ties go to whoever got there first.",
         "Drills held by your teacher for review are left off until cleared."]

# Set True only when the teacher has confirmed the windows.
CONFIRMED = False
PERSONAL_MIN = 75
UNIQUE_DRILLS = False   # False: every passed drill is a lap (repeats count). True: each drill counts once.

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
    """One board across classes. A lap = passed, unflagged (or cleared) attempt that started and finished
    inside that student's own clock (joined_at to min(joined_at + 75 min, class cutoff))."""
    roster = roster_lookup(db)
    rows = db.execute(
        """SELECT a.id, a.user_id, a.algo, a.elapsed_ms, a.started_at, a.finished_at, u.name, u.email
           FROM speed_attempts a JOIN users u ON u.id=a.user_id
           WHERE a.passed=1 AND (a.flagged=0 OR a.cleared=1) AND u.role='student' ORDER BY a.finished_at, a.id""").fetchall()
    joins = {r["user_id"]: datetime.fromisoformat(r["joined_at"]).astimezone(SGT)
             for r in db.execute("SELECT user_id, joined_at FROM comp_joins")}
    per = {}
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
        if UNIQUE_DRILLS and r["algo"] in per.get(r["user_id"], {"algos": ()})["algos"]:
            continue
        p = per.setdefault(r["user_id"], {"uid": r["user_id"], "name": rn or r["name"] or "Student",
                                          "cls": rc, "laps": 0, "last": f, "best": r["elapsed_ms"], "algos": set()})
        p["laps"] += 1; p["last"] = f; p["best"] = min(p["best"], r["elapsed_ms"]); p["algos"].add(r["algo"])
    board = sorted(per.values(), key=lambda p: (-p["laps"], p["last"]))
    for i, p in enumerate(board, 1):
        p["rank"] = i; p["drills"] = len(p["algos"])
    return board
