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
RULES = ["Only drills finished inside your lesson window count as laps.",
         "A lap is a drill whose checks all pass. Re-running and retrying is fine.",
         "Most laps tops the board. Ties go to whoever got there first.",
         "Drills held by your teacher for review are left off until cleared."]

# Set True only when the teacher has confirmed the windows.
CONFIRMED = False

def _w(day, a, b):
    return (datetime.fromisoformat(f"{day}T{a}:00").replace(tzinfo=SGT),
            datetime.fromisoformat(f"{day}T{b}:00").replace(tzinfo=SGT))

# Provisional: the lesson times as stated. The 75-minute length vs these lesson lengths is undecided.
WINDOWS = [
    {"label": "25S21", "classes": ("25S21",), "start": _w("2026-10-02", "12:30", "14:00")[0], "end": _w("2026-10-02", "12:30", "14:00")[1]},
    {"label": "25S11 + 25S22", "classes": ("25S11", "25S22"), "start": _w("2026-10-02", "14:00", "15:39")[0], "end": _w("2026-10-02", "14:00", "15:39")[1]},
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

def standings(db, roster_lookup, norm_email):
    """One board across classes. A lap = passed, unflagged (or cleared) attempt that started and finished
    inside that student's class window."""
    roster = roster_lookup(db)
    rows = db.execute(
        """SELECT a.id, a.user_id, a.algo, a.elapsed_ms, a.started_at, a.finished_at, u.name, u.email
           FROM speed_attempts a JOIN users u ON u.id=a.user_id
           WHERE a.passed=1 AND (a.flagged=0 OR a.cleared=1) AND u.role='student' ORDER BY a.finished_at, a.id""").fetchall()
    per = {}
    for r in rows:
        rn, rc = roster.get(norm_email(r["email"]), (None, None))
        w = window_for_class(rc)
        if not w:
            continue
        s = datetime.fromisoformat(r["started_at"]); f = datetime.fromisoformat(r["finished_at"])
        if s < w["start"] or f > w["end"]:
            continue
        p = per.setdefault(r["user_id"], {"uid": r["user_id"], "name": rn or r["name"] or "Student",
                                          "cls": rc, "laps": 0, "last": f, "best": r["elapsed_ms"], "algos": set()})
        p["laps"] += 1; p["last"] = f; p["best"] = min(p["best"], r["elapsed_ms"]); p["algos"].add(r["algo"])
    board = sorted(per.values(), key=lambda p: (-p["laps"], p["last"]))
    for i, p in enumerate(board, 1):
        p["rank"] = i; p["drills"] = len(p["algos"])
    return board
