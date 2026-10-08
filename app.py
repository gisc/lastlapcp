"""LastLapCP - gamified A-level H2 Computing (9569) revision app.
Flask + SQLite + Jinja. Mobile-first. Google sign-in with an email allowlist.
All secrets/identity data come from env vars, never from the repo."""
import ast
import json
import os
import re
import random
import sqlite3
from datetime import date, datetime, timedelta, timezone
from functools import wraps

from flask import (Flask, abort, g, redirect, render_template, request, send_from_directory,
                   jsonify, session, url_for)
from authlib.integrations.flask_client import OAuth
import papers_data
import speed_data
import speed_examples
import comp
import lastday
from werkzeug.middleware.proxy_fix import ProxyFix

SGT = timezone(timedelta(hours=8))
DB_PATH = os.environ.get("DATABASE_PATH", "/data/lastlapcp.db")
def _norm_email(e):
    e = e.strip().lower()
    local, sep, domain = e.partition("@")
    if sep and domain in ("gmail.com", "googlemail.com"):
        local = local.replace(".", "")
        return local + "@gmail.com"
    return e

def _norm_answer(s):
    return " ".join((s or "").strip().lower().split())

def _fib_match(typed, accepted, case_sensitive=False):
    """Correct when the typed answer equals an accepted variant, or one contains
    the other as a contiguous run of whole words (so 'double entry' matches the
    keyword 'double' but 'router' does not match 'route'). With case_sensitive,
    only whitespace is normalised - identifiers like StackPointer must match
    exactly, as Python names are case-sensitive."""
    if case_sensitive:
        t = " ".join((typed or "").strip().split())
    else:
        t = _norm_answer(typed)
    if not t:
        return False
    tw = t.split()
    for a in accepted:
        aw = a.split()
        if t == " ".join(aw):
            return True
        for hay, needle in ((tw, aw), (aw, tw)):
            for i in range(len(hay) - len(needle) + 1):
                if hay[i:i + len(needle)] == needle:
                    return True
    return False

TEACHER_EMAILS = {_norm_email(e) for e in os.environ.get("TEACHER_EMAILS", "").split(",") if e.strip()}
ALLOWED_EMAILS = {_norm_email(e) for e in os.environ.get("ALLOWED_EMAILS", "").split(",") if e.strip()} | TEACHER_EMAILS

def _parse_roster():
    """ROSTER env: entries separated by ; or newlines, each 'class:name:email'.
    Identity data stays in env vars, never in the repo."""
    out = []
    raw = os.environ.get("ROSTER", "")
    for part in re.split(r"[;\n]+", raw):
        part = part.strip()
        if not part:
            continue
        bits = part.split(":", 2)
        if len(bits) != 3:
            continue
        cls, name, email = (b.strip() for b in bits)
        out.append({"class": cls, "name": name, "email": email, "norm": _norm_email(email)})
    return out

ROSTER_ENV = _parse_roster()
ROSTER_GROUPS = [("25S11 + 25S22 (combined lessons)", ("25S11", "25S22")), ("25S21", ("25S21",))]

app = Flask(__name__)
# Behind the Olares TLS-terminating gateway: honor X-Forwarded-* and force https
# so url_for(_external=True) builds https URLs (Google OAuth redirect_uri).
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
app.config["PREFERRED_URL_SCHEME"] = "https"
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-secret-change-me")
app.config.update(
    SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "1") == "1",
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=timedelta(days=60),
)

oauth = OAuth(app)
google = oauth.register(
    name="google",
    client_id=os.environ.get("GOOGLE_CLIENT_ID", ""),
    client_secret=os.environ.get("GOOGLE_CLIENT_SECRET", ""),
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)

# ---------------- DB ----------------

def get_db():
    if "db" not in g:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
        g.db.execute("PRAGMA journal_mode=WAL")
        g.db.execute("PRAGMA busy_timeout=5000")
    return g.db

@app.teardown_appcontext
def close_db(_=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL, name TEXT,
  role TEXT NOT NULL DEFAULT 'student', created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS questions(
  id INTEGER PRIMARY KEY, topic TEXT NOT NULL, paper TEXT NOT NULL,
  qtype TEXT NOT NULL, stem TEXT NOT NULL, explanation TEXT NOT NULL,
  misconception TEXT DEFAULT '', code TEXT DEFAULT '',
  case_sensitive INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS options(
  id INTEGER PRIMARY KEY, question_id INTEGER NOT NULL REFERENCES questions(id),
  ord INTEGER NOT NULL, text TEXT NOT NULL, is_correct INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS attempts(
  id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
  question_id INTEGER NOT NULL REFERENCES questions(id),
  correct INTEGER NOT NULL, xp INTEGER NOT NULL,
  chosen TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_attempts_user ON attempts(user_id);
CREATE INDEX IF NOT EXISTS idx_attempts_q ON attempts(question_id);
CREATE TABLE IF NOT EXISTS roster(
  email TEXT PRIMARY KEY, name TEXT, class TEXT
);
CREATE TABLE IF NOT EXISTS t3_questions(
  id INTEGER PRIMARY KEY, topic TEXT NOT NULL, title TEXT NOT NULL,
  intro TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS t3_parts(
  id INTEGER PRIMARY KEY, question_id INTEGER NOT NULL REFERENCES t3_questions(id),
  ord INTEGER NOT NULL, instruction TEXT NOT NULL,
  starter TEXT DEFAULT '', tests TEXT NOT NULL, model TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS t3_attempts(
  id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
  part_id INTEGER NOT NULL REFERENCES t3_parts(id),
  passed INTEGER NOT NULL, xp INTEGER NOT NULL,
  code TEXT NOT NULL, output TEXT DEFAULT '', created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_t3att_user ON t3_attempts(user_id);
CREATE INDEX IF NOT EXISTS idx_t3att_part ON t3_attempts(part_id);
CREATE TABLE IF NOT EXISTS feedback(
  id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
  qref TEXT NOT NULL, qlabel TEXT NOT NULL, qurl TEXT DEFAULT '',
  message TEXT NOT NULL, created_at TEXT NOT NULL,
  useful INTEGER NOT NULL DEFAULT 0, useful_at TEXT DEFAULT '');
CREATE INDEX IF NOT EXISTS idx_feedback_user ON feedback(user_id);
CREATE TABLE IF NOT EXISTS speed_attempts(
  id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
  algo TEXT NOT NULL, mode TEXT NOT NULL, started_at TEXT NOT NULL,
  finished_at TEXT DEFAULT '', elapsed_ms INTEGER NOT NULL DEFAULT 0,
  passed INTEGER NOT NULL DEFAULT 0, runs INTEGER NOT NULL DEFAULT 0,
  code TEXT NOT NULL DEFAULT '', paste_count INTEGER NOT NULL DEFAULT 0,
  flagged INTEGER NOT NULL DEFAULT 0, flag_note TEXT NOT NULL DEFAULT '',
  cleared INTEGER NOT NULL DEFAULT 0, ck_frac REAL NOT NULL DEFAULT 0, ck_at TEXT NOT NULL DEFAULT '');
CREATE INDEX IF NOT EXISTS idx_speed_algo ON speed_attempts(algo, passed);
CREATE INDEX IF NOT EXISTS idx_speed_user ON speed_attempts(user_id);
CREATE TABLE IF NOT EXISTS comp_override(
  user_id INTEGER PRIMARY KEY REFERENCES users(id), partial REAL NOT NULL, note TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS comp_joins(
  user_id INTEGER PRIMARY KEY REFERENCES users(id), joined_at TEXT NOT NULL);
"""

# One-time stem fixes: rename live rows in place (keeps question id and attempts)
# so the stem-merge below does not re-add the edited stem as a duplicate.
STEM_RENAMES = {
    "The time complexity of linear search on n items is O(n).":
        "The time complexity of linear search on n items is:",
    "Denary 10 in binary is 1010.":
        "Denary 10 in binary is:",
    "Standard ASCII uses 7 bits per character.":
        "How many bits per character does Standard ASCII use?",
}

def seed_questions(db):
    for old_stem, new_stem in STEM_RENAMES.items():
        db.execute(
            "UPDATE questions SET stem=? WHERE stem=? AND NOT EXISTS (SELECT 1 FROM questions WHERE stem=?)",
            (new_stem, old_stem, new_stem))
    db.commit()
    have = {r["stem"] for r in db.execute("SELECT stem FROM questions").fetchall()}
    seed_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seed_questions.json")
    with open(seed_path, encoding="utf-8") as f:
        bank = json.load(f)
    for q in bank:
        if q["stem"] in have:
            continue
        cur = db.execute(
            "INSERT INTO questions(topic,paper,qtype,stem,explanation,misconception,code,case_sensitive) VALUES(?,?,?,?,?,?,?,?)",
            (q["topic"], q["paper"], q["qtype"], q["stem"], q["explanation"], q.get("misconception", ""), q.get("code", ""),
             1 if q.get("case_sensitive") else 0))
        qid = cur.lastrowid
        for i, opt in enumerate(q["options"]):
            db.execute("INSERT INTO options(question_id,ord,text,is_correct) VALUES(?,?,?,?)",
                       (qid, i, opt["text"], 1 if opt["correct"] else 0))
    db.commit()

def seed_t3(db):
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seed_t3.json")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        bank = json.load(f)
    have = {r["title"] for r in db.execute("SELECT title FROM t3_questions").fetchall()}
    for q in bank:
        if q["title"] in have:
            continue
        cur = db.execute("INSERT INTO t3_questions(topic,title,intro,kind,created_at) VALUES(?,?,?,?,?)",
                         (q["topic"], q["title"], q["intro"], q.get("kind", "code"), datetime.now(timezone.utc).isoformat()))
        qid = cur.lastrowid
        for i, p in enumerate(q["parts"], 1):
            db.execute("INSERT INTO t3_parts(question_id,ord,instruction,starter,tests,model,rubric) VALUES(?,?,?,?,?,?,?)",
                       (qid, i, p["instruction"], p.get("starter", ""), p.get("tests", ""), p["model"],
                        json.dumps(p["rubric"]) if p.get("rubric") else ""))
    # 2026-09-30 (v2): seed-is-truth refresh for ALL Tier 3 theory rubrics and model
    # answers. Title-merge seeding only inserts new questions, so patch stored rows whose
    # rubric or model differs from seed. Covers the broader key points, atomic splits and
    # wider synonym groups from the fair-marking fix.
    for q in bank:
        if q.get("kind") != "theory" or not q["parts"][0].get("rubric"):
            continue
        row = db.execute("SELECT id FROM t3_questions WHERE title=?", (q["title"],)).fetchone()
        if not row:
            continue
        part = db.execute("SELECT rubric, model FROM t3_parts WHERE question_id=? AND ord=1",
                          (row["id"],)).fetchone()
        if part:
            seed_rubric = json.dumps(q["parts"][0]["rubric"])
            seed_model = q["parts"][0]["model"]
            if (part["rubric"] or "") != seed_rubric or (part["model"] or "") != seed_model:
                db.execute("UPDATE t3_parts SET rubric=?, model=? WHERE question_id=? AND ord=1",
                           (seed_rubric, seed_model, row["id"]))
    # 2026-10-01: circular queue parts 1-2 never said _rear starts at -1, so a student who
    # started it at 0 failed with a confusing message. Patch the stored rows only while they
    # still hold the previous seed text (a teacher-edited part is left alone).
    cq = next((q for q in bank if q["title"] == "Implement a circular queue"), None)
    cq_old = [
        ("Write the constructor __init__(capacity) that sets up a fixed-size list self._items of capacity None values, plus self._capacity, self._front, self._rear and a count self._count. Then write is_empty() and is_full() using the count.",
         "q = CircularQueue(3)\nassert q.is_empty() == True and q.is_full() == False, 'a new queue is empty, not full'\nassert len(q._items) == 3, 'the underlying list has exactly capacity slots'"),
        ("Add enqueue(item). It returns False when the queue is full. Otherwise it moves _rear forward by one slot, wrapping back to index 0 at the end of the list, stores the item there, and returns True. (Wrap with modulo: (self._rear + 1) % self._capacity.)",
         "q = CircularQueue(3)\nassert q.enqueue('a') == True and q.enqueue('b') == True and q.enqueue('c') == True\nassert q.is_full() == True, 'three items fill a capacity-3 queue'\nassert q.enqueue('d') == False, 'enqueue on a full queue returns False'\nassert q._rear == 2, 'rear sits on the last stored item'"),
    ]
    if cq:
        row = db.execute("SELECT id FROM t3_questions WHERE title=?", (cq["title"],)).fetchone()
        if row:
            for i, (oi, ot) in enumerate(cq_old, 1):
                part = db.execute("SELECT instruction, tests FROM t3_parts WHERE question_id=? AND ord=?", (row["id"], i)).fetchone()
                if part and part["instruction"] == oi and part["tests"] == ot:
                    db.execute("UPDATE t3_parts SET instruction=?, tests=? WHERE question_id=? AND ord=?",
                               (cq["parts"][i - 1]["instruction"], cq["parts"][i - 1]["tests"], row["id"], i))
    # 2026-09-30: feedback XP columns for DBs created before they existed
    fbcols = [r["name"] for r in db.execute("PRAGMA table_info(feedback)")]
    if "useful" not in fbcols:
        db.execute("ALTER TABLE feedback ADD COLUMN useful INTEGER NOT NULL DEFAULT 0")
    if "useful_at" not in fbcols:
        db.execute("ALTER TABLE feedback ADD COLUMN useful_at TEXT DEFAULT ''")
    db.commit()

# ---------------- tier 3 test harness ----------------
# Rewrites plain `assert X == Y, "label"` tests (and `and`-chains of them) into
# _ll_check calls so a failure says:  label: expected X, got Y
# Runs at render time, so stored tests and the teacher admin form stay plain asserts.
T3_TEST_PREAMBLE = """def _ll_check(got, op, expected, label):
    if op == '==': ok = got == expected
    elif op == '!=': ok = got != expected
    elif op == 'is': ok = got is expected
    elif op == 'is not': ok = got is not expected
    elif op == 'in': ok = got in expected
    elif op == 'not in': ok = got not in expected
    elif op == '<': ok = got < expected
    elif op == '<=': ok = got <= expected
    elif op == '>': ok = got > expected
    else: ok = got >= expected
    if not ok:
        want = repr(expected) if op in ('==', 'is') else op + ' ' + repr(expected)
        raise AssertionError(f'{label}: expected {want}, got {got!r}')
"""

_LL_OPS = {ast.Eq: '==', ast.NotEq: '!=', ast.Is: 'is', ast.IsNot: 'is not',
           ast.In: 'in', ast.NotIn: 'not in',
           ast.Lt: '<', ast.LtE: '<=', ast.Gt: '>', ast.GtE: '>='}

class _T3AssertRewriter(ast.NodeTransformer):
    def visit_Assert(self, node):
        values = node.test.values if isinstance(node.test, ast.BoolOp) and isinstance(node.test.op, ast.And) else [node.test]
        for v in values:
            if not (isinstance(v, ast.Compare) and len(v.ops) == 1 and type(v.ops[0]) in _LL_OPS):
                return node  # anything exotic stays a plain assert
        out = []
        for v in values:
            if isinstance(node.msg, ast.Constant) and isinstance(node.msg.value, str):
                label = node.msg
            else:
                label = ast.Constant(ast.unparse(v))
            out.append(ast.Expr(value=ast.Call(
                func=ast.Name(id='_ll_check', ctx=ast.Load()),
                args=[v.left, ast.Constant(_LL_OPS[type(v.ops[0])]), v.comparators[0], label],
                keywords=[])))
        return out

def rewrite_t3_tests(src):
    try:
        tree = ast.parse(src)
        tree = _T3AssertRewriter().visit(tree)
        ast.fix_missing_locations(tree)
        return ast.unparse(tree)
    except Exception:
        return src  # unparseable tests run as-is, failures keep the old style

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA busy_timeout=5000")
    db.executescript(SCHEMA)
    db.row_factory = sqlite3.Row
    cols = [r["name"] for r in db.execute("PRAGMA table_info(questions)")]
    if "code" not in cols:
        db.execute("ALTER TABLE questions ADD COLUMN code TEXT DEFAULT ''")
    if "case_sensitive" not in cols:
        db.execute("ALTER TABLE questions ADD COLUMN case_sensitive INTEGER NOT NULL DEFAULT 0")
    spcols = [r["name"] for r in db.execute("PRAGMA table_info(speed_attempts)")]
    if "ck_frac" not in spcols:
        db.execute("ALTER TABLE speed_attempts ADD COLUMN ck_frac REAL NOT NULL DEFAULT 0")
    if "ck_at" not in spcols:
        db.execute("ALTER TABLE speed_attempts ADD COLUMN ck_at TEXT NOT NULL DEFAULT ''")
    t3qcols = [r["name"] for r in db.execute("PRAGMA table_info(t3_questions)")]
    if "kind" not in t3qcols:
        db.execute("ALTER TABLE t3_questions ADD COLUMN kind TEXT NOT NULL DEFAULT 'code'")
    t3pcols = [r["name"] for r in db.execute("PRAGMA table_info(t3_parts)")]
    if "rubric" not in t3pcols:
        db.execute("ALTER TABLE t3_parts ADD COLUMN rubric TEXT NOT NULL DEFAULT ''")
    db.commit()
    backfill_edge_flags(db)
    seed_questions(db)
    seed_t3(db)
    db.close()

def _edge_reason(slug, note):
    """Student-facing reason for an 'Edge case' flag, built from the teacher note."""
    m = re.search(r"Edge case: ([^;]*?) - no check for an empty (stack|queue)", note or "")
    if not m:
        return ""
    names = " and ".join(x.strip() for x in m.group(1).split(","))
    return ("Held off the speed leaderboard: no empty-%s check was found in %s. Review how your code handles an empty %s. "
            "This is an automatic code check, not a final judgement; your teacher can clear the flag if the handling is valid."
            % (m.group(2), names, m.group(2)))

def backfill_edge_flags(db):
    """Flag earlier passed stack/queue attempts whose code has no empty check on pop/peek/dequeue.
    Static read only, idempotent, never touches cleared attempts, code or times."""
    rows = db.execute(
        """SELECT id, algo, code, flag_note FROM speed_attempts
           WHERE passed=1 AND cleared=0 AND algo IN ('stack','queue') AND code<>'' AND flag_note NOT LIKE '%Edge case:%'""").fetchall()
    n = 0
    for r in rows:
        notes = speed_data.edge_notes(r["algo"], r["code"])
        if notes:
            note = "; ".join([x for x in [r["flag_note"]] if x] + ["Edge case: " + x for x in notes])
            db.execute("UPDATE speed_attempts SET flagged=1, flag_note=? WHERE id=?", (note, r["id"]))
            n += 1
    if n:
        db.commit()
    return n

# ---------------- tier 3 theory grader ----------------
# Free-text "write everything you know" answers are graded server-side against a
# rubric of key points, so the accepted terms never ship to the browser. Each key
# point has groups of synonyms; every group must hit for a green. Some groups
# hitting = orange (partial, told which aspect is missing). Known misconception
# patterns = red with an explanation. Student text never leaves this server.

def _norm_text(s):
    s = s.lower().replace("n't", " not")
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    return " " + re.sub(r"\s+", " ", s).strip() + " "

_NEGATORS = ("not", "never", "no", "cannot", "without", "doesnt", "dont", "isnt", "wont")

def _term_hit(text, term, not_after=None, window=3):
    # unnegated match only: no negator within `window` words before the term,
    # and none of the `not_after` blocker words within `window` words before it
    guards = _NEGATORS + tuple(not_after or ())
    for m in re.finditer(r"\b" + re.escape(term), text):
        before = text[:m.start()].split()[-window:]
        if not any(w in guards for w in before):
            return True
    return False

def _term_hit_negated(text, term, window=3):
    # negated match only: a negator must appear within `window` words before the term
    for m in re.finditer(r"\b" + re.escape(term), text):
        before = text[:m.start()].split()[-window:]
        if any(w in _NEGATORS for w in before):
            return True
    return False

def _group_hit(text, group):
    # group is either ["term", ...] or {"any": [...], "not_after": [...], "negated_any": [...]}
    # "any" terms need an unnegated hit; "negated_any" terms need a negated hit
    # (e.g. crediting "nodes are NOT stored contiguously" for the non-contiguous point).
    if isinstance(group, dict):
        if any(_term_hit(text, t, not_after=group.get("not_after")) for t in group.get("any", [])):
            return True
        return any(_term_hit_negated(text, t) for t in group.get("negated_any", []))
    return any(_term_hit(text, t) for t in group)

def grade_theory(text, rubric):
    bullets = []
    for line in text.splitlines():
        b = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", line).strip()
        if b:
            bullets.append(b)
    points = rubric.get("points", [])
    pats = [{"pat": m["pat"], "feedback": m["feedback"]} for m in rubric.get("misconceptions", [])]
    for p in points:
        for w in p.get("wrong", []):
            pats.append({"pat": w["pat"], "feedback": w["feedback"]})
    claimed = {}
    results = []
    for b in bullets:
        n = _norm_text(b)
        wrong_fb = ""
        for m in pats:
            if all(_group_hit(n, g) for g in m["pat"]):
                wrong_fb = m["feedback"]
                break
        if wrong_fb:
            results.append({"text": b, "verdict": "red", "feedback": wrong_fb})
            continue
        hit_i = [i for i, p in enumerate(points)
                 if all(_group_hit(n, g) for g in p["req"])]
        if hit_i:
            for i in hit_i:
                if claimed.get(i) != "green":
                    claimed[i] = "green"
            results.append({"text": b, "verdict": "green", "feedback": ""})
            continue
        best_i, best_hits = None, 0
        for i, p in enumerate(points):
            if claimed.get(i) == "green":
                continue
            hits = sum(1 for g in p["req"] if _group_hit(n, g))
            if 0 < hits < len(p["req"]) and hits > best_hits:
                best_i, best_hits = i, hits
        if best_i is not None:
            p = points[best_i]
            missing = [p["aspects"][j] for j, g in enumerate(p["req"]) if not _group_hit(n, g)]
            claimed.setdefault(best_i, "orange")
            results.append({"text": b, "verdict": "orange",
                            "feedback": "On the right track - missing: " + "; ".join(missing) + "."})
            continue
        results.append({"text": b, "verdict": "grey", "feedback": "Not one of the key points tracked for this topic - it may still be correct, it just does not count toward the score."})
    greens = sum(1 for v in claimed.values() if v == "green")
    total = len(points)
    reds = sum(1 for r in results if r["verdict"] == "red")
    missed = [p["point"] for i, p in enumerate(points) if i not in claimed]
    partial = [p["point"] for i, p in enumerate(points) if claimed.get(i) == "orange"]
    passed = total > 0 and reds == 0 and greens * 10 >= total * 7
    return {"results": results, "greens": greens, "total": total, "reds": reds,
            "missed": missed, "partial": partial, "passed": passed}

# ---------------- auth helpers ----------------

def current_user():
    uid = session.get("uid")
    if not uid:
        return None
    return get_db().execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()

def login_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        if not current_user():
            return redirect(url_for("login"))
        return f(*a, **kw)
    return wrapper

def teacher_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        u = current_user()
        if not u:
            return redirect(url_for("login"))
        if u["role"] != "teacher":
            abort(403)
        return f(*a, **kw)
    return wrapper

# ---------------- stats helpers ----------------

def user_stats(db, uid):
    row = db.execute(
        "SELECT COALESCE(SUM(xp),0) xp, COUNT(*) n, COALESCE(SUM(correct),0) c FROM attempts WHERE user_id=?",
        (uid,)).fetchone()
    t3xp = db.execute("SELECT COALESCE(SUM(xp),0) xp FROM t3_attempts WHERE user_id=?", (uid,)).fetchone()["xp"]
    fbxp = db.execute("SELECT COUNT(*) c FROM feedback WHERE user_id=? AND useful=1", (uid,)).fetchone()["c"] * FB_USEFUL_XP
    dates = {r["d"] for r in db.execute(
        "SELECT DISTINCT date(created_at, '+8 hours') d FROM attempts WHERE user_id=?", (uid,))}
    dates |= {r["d"] for r in db.execute(
        "SELECT DISTINCT date(created_at, '+8 hours') d FROM t3_attempts WHERE user_id=?", (uid,))}
    streak = 0
    day = datetime.now(SGT).date()
    if day.isoformat() not in dates:
        day -= timedelta(days=1)
    while day.isoformat() in dates:
        streak += 1
        day -= timedelta(days=1)
    topics = db.execute(
        """SELECT q.topic, COUNT(*) n, COALESCE(SUM(a.correct),0) c
           FROM attempts a JOIN questions q ON q.id=a.question_id
           WHERE a.user_id=? GROUP BY q.topic ORDER BY q.topic""", (uid,)).fetchall()
    mastery = [{"topic": t["topic"], "n": t["n"],
                "pct": round(100 * t["c"] / t["n"]) if t["n"] else 0} for t in topics]
    return {"xp": row["xp"] + t3xp + fbxp, "attempts": row["n"], "correct": row["c"],
            "streak": streak, "mastery": mastery}

TIER_QTYPES = {0: ("binary",), 1: ("mcq", "checkbox"), 2: ("fib",)}

def pick_question(db, uid, topic=None, tier=None, paper=None):
    params, where = [], ""
    if topic:
        where += " AND q.topic=?"
        params.append(topic)
    if tier in TIER_QTYPES:
        where += " AND q.qtype IN (%s)" % ",".join("?" * len(TIER_QTYPES[tier]))
        params.extend(TIER_QTYPES[tier])
    if paper in ("P1", "P2"):
        where += " AND q.paper=?"
        params.append(paper)
    row = db.execute(
        f"""SELECT q.id FROM questions q
            WHERE NOT EXISTS(SELECT 1 FROM attempts a WHERE a.question_id=q.id AND a.user_id=?) {where}
            ORDER BY RANDOM() LIMIT 1""", [uid] + params).fetchone()
    if not row:
        row = db.execute(
            f"""SELECT q.id FROM questions q WHERE 1=1 {where}
                ORDER BY COALESCE((SELECT MAX(a.created_at) FROM attempts a
                          WHERE a.question_id=q.id AND a.user_id=?), ''), RANDOM() LIMIT 1""",
            params + [uid]).fetchone()
    return row["id"] if row else None

def load_question(db, qid):
    q = db.execute("SELECT * FROM questions WHERE id=?", (qid,)).fetchone()
    opts = db.execute("SELECT * FROM options WHERE question_id=? ORDER BY ord", (qid,)).fetchall()
    return q, opts

@app.context_processor
def _comp_skin():
    """Session-only colour skin while the student's competition window is open (never when CONFIRMED is off)."""
    try:
        if request.path.startswith("/static") or not session.get("uid"):
            return {}
        if request.path == "/teacher/comp":
            return {"comp_skin": True}
        u = current_user()
        if not u or u["role"] == "teacher" or not comp.CONFIRMED:
            return {}
        cls = _roster_lookup(get_db()).get(_norm_email(u["email"]), (None, None))[1]
        return {"comp_skin": bool(comp.student_window(cls, datetime.now(SGT)))}
    except Exception:
        return {}

# ---------------- routes ----------------

@app.route("/")
def home():
    u = current_user()
    if not u:
        return redirect(url_for("login"))
    db = get_db()
    stats = user_stats(db, u["id"])
    today = datetime.now(SGT).date()
    exams = []
    for label, kind, d in [("Paper 2", "Practical", date(2026, 10, 7)),
                           ("Paper 1", "Written", date(2026, 11, 11))]:
        exams.append({"label": label, "kind": kind,
                      "when": d.strftime("%a %-d %b"), "days": (d - today).days})
    topics = [r["topic"] for r in db.execute(
        "SELECT DISTINCT topic FROM questions WHERE qtype IN ('mcq','checkbox') ORDER BY topic")]
    t3, t3t = [], []
    for r in db.execute("SELECT * FROM t3_questions ORDER BY id").fetchall():
        n = db.execute("SELECT COUNT(*) c FROM t3_parts WHERE question_id=?", (r["id"],)).fetchone()["c"]
        done = db.execute(
            """SELECT COUNT(DISTINCT p.ord) c FROM t3_parts p JOIN t3_attempts a ON a.part_id=p.id
                WHERE p.question_id=? AND a.user_id=? AND a.passed=1""", (r["id"], u["id"])).fetchone()["c"]
        (t3t if r["kind"] == "theory" else t3).append(
            {"id": r["id"], "title": r["title"], "topic": r["topic"], "n": n, "done": done})
    ld_open = False
    if u["role"] != "teacher":
        ld_cls = _roster_lookup(db).get(_norm_email(u["email"]), (None, None))[1]
        ld_open = ld_cls in lastday.CLASS_ORDER and lastday.is_open(datetime.now(SGT))
    cw = None
    if u["role"] != "teacher":
        cw = comp.student_window(_roster_lookup(db).get(_norm_email(u["email"]), (None, None))[1], datetime.now(SGT))
    return render_template("home.html", u=u, stats=stats, topics=topics, t3=t3, t3t=t3t, exams=exams, cw=cw, comp=comp, ld_open=ld_open, ld=lastday)

@app.route("/login")
def login():
    if current_user():
        return redirect(url_for("home"))
    configured = bool(os.environ.get("GOOGLE_CLIENT_ID"))
    return render_template("login.html", configured=configured)

@app.route("/login/google")
def login_google():
    if not os.environ.get("GOOGLE_CLIENT_ID"):
        abort(500, "OAuth not configured")
    return google.authorize_redirect(url_for("auth_callback", _external=True))

def _is_allowed_email(db, email):
    """Deny by default: an email gets in only via TEACHER_EMAILS, the
    ALLOWED_EMAILS env list, or the roster table managed by the teacher."""
    email = _norm_email(email)
    if email in ALLOWED_EMAILS:
        return True
    return db.execute("SELECT 1 FROM roster WHERE lower(email)=?", (email,)).fetchone() is not None

@app.route("/login/callback")
def auth_callback():
    token = google.authorize_access_token()
    info = token.get("userinfo") or {}
    email = _norm_email(info.get("email") or "")
    if not email:
        return render_template("denied.html", reason="Google did not return an email address."), 403
    if info.get("email_verified") is False:
        return render_template("denied.html", reason="Google reports this email address is not verified."), 403
    db = get_db()
    if not _is_allowed_email(db, email):
        return render_template("denied.html",
            reason="This account is not on the LastLapCP class list. Ask your teacher to add it."), 403
    role = "teacher" if email in TEACHER_EMAILS else "student"
    db.execute("INSERT INTO users(email,name,role,created_at) VALUES(?,?,?,?) "
               "ON CONFLICT(email) DO UPDATE SET name=excluded.name, role=excluded.role",
               (email, info.get("name", ""), role, datetime.now(timezone.utc).isoformat()))
    db.commit()
    u = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    session.permanent = True
    session["uid"] = u["id"]
    return redirect(url_for("home"))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/quiz")
@login_required
def quiz():
    topic = request.args.get("topic") or None
    tier = request.args.get("tier", type=int)
    paper = request.args.get("paper") or None
    qid = pick_question(get_db(), session["uid"], topic, tier, paper)
    if qid is None:
        return render_template("quiz.html", empty=True, topic=topic, tier=tier, paper=paper)
    return redirect(url_for("question", qid=qid, topic=topic or "", tier="" if tier is None else tier, paper=paper or ""))

@app.route("/q/<int:qid>")
@login_required
def question(qid):
    topic = request.args.get("topic") or ""
    tier = request.args.get("tier", type=int)
    paper = request.args.get("paper") or ""
    q, opts = load_question(get_db(), qid)
    if not q:
        abort(404)
    opts = list(opts)
    random.shuffle(opts)
    return render_template("quiz.html", q=q, opts=opts, topic=topic, tier=tier, paper=paper,
                           empty=False, feedback=None)

@app.route("/q/<int:qid>", methods=["POST"])
@login_required
def answer(qid):
    topic = request.form.get("topic", "")
    tier = request.form.get("tier", type=int)
    paper = request.form.get("paper", "")
    db = get_db()
    u = current_user()
    q, opts = load_question(db, qid)
    if not q:
        abort(404)
    if q["qtype"] == "fib":
        typed = request.form.get("fib_text", "")
        cs = bool(q["case_sensitive"])
        accepted = {(" ".join(o["text"].strip().split()) if cs else _norm_answer(o["text"])) for o in opts}
        correct = 1 if _fib_match(typed, accepted, case_sensitive=cs) else 0
        if correct:
            best = db.execute("SELECT COALESCE(MAX(xp),0) b FROM attempts WHERE user_id=? AND question_id=?",
                              (u["id"], qid)).fetchone()["b"]
            xp = 2 if best > 0 else 10
        else:
            xp = 0
        db.execute("INSERT INTO attempts(user_id,question_id,correct,xp,chosen,created_at) VALUES(?,?,?,?,?,?)",
                   (u["id"], qid, correct, xp, typed.strip()[:200],
                    datetime.now(timezone.utc).isoformat()))
        db.commit()
        stats = user_stats(db, u["id"])
        return render_template("quiz.html", q=q, opts=opts, topic=topic, tier=tier, paper=paper,
                               empty=False,
                               feedback={"correct": correct, "xp": xp, "typed": typed.strip(),
                                         "accepted": sorted({o["text"] for o in opts})}, stats=stats)
    correct_ids = {o["id"] for o in opts if o["is_correct"]}
    if q["qtype"] == "binary":
        v = request.form.get("opt")
        chosen = {int(v)} if v else set()
        correct = 1 if (chosen and chosen == correct_ids) else 0
        if correct:
            best = db.execute("SELECT COALESCE(MAX(xp),0) b FROM attempts WHERE user_id=? AND question_id=?",
                              (u["id"], qid)).fetchone()["b"]
            xp = 2 if best > 0 else 5
        else:
            xp = 0
        db.execute("INSERT INTO attempts(user_id,question_id,correct,xp,chosen,created_at) VALUES(?,?,?,?,?,?)",
                   (u["id"], qid, correct, xp, ",".join(map(str, sorted(chosen))),
                    datetime.now(timezone.utc).isoformat()))
        db.commit()
        stats = user_stats(db, u["id"])
        return render_template("quiz.html", q=q, opts=opts, topic=topic, tier=tier, paper=paper,
                               empty=False,
                               feedback={"correct": correct, "xp": xp, "chosen": chosen,
                                         "correct_ids": correct_ids}, stats=stats)
    if q["qtype"] == "checkbox":
        chosen = {int(x) for x in request.form.getlist("opt")}
    else:
        v = request.form.get("opt")
        chosen = {int(v)} if v else set()
    correct = 1 if (chosen and chosen == correct_ids) else 0
    if correct:
        best = db.execute("SELECT COALESCE(MAX(xp),0) b FROM attempts WHERE user_id=? AND question_id=?",
                          (u["id"], qid)).fetchone()["b"]
        base = 15 if q["qtype"] == "checkbox" else 10
        xp = 2 if best > 0 else base
    else:
        xp = 0
    db.execute("INSERT INTO attempts(user_id,question_id,correct,xp,chosen,created_at) VALUES(?,?,?,?,?,?)",
               (u["id"], qid, correct, xp, ",".join(map(str, sorted(chosen))),
                datetime.now(timezone.utc).isoformat()))
    db.commit()
    stats = user_stats(db, u["id"])
    return render_template("quiz.html", q=q, opts=opts, topic=topic, tier=tier, paper=paper,
                           empty=False,
                           feedback={"correct": correct, "xp": xp, "chosen": chosen,
                                     "correct_ids": correct_ids}, stats=stats)

@app.route("/teacher")
@teacher_required
def teacher():
    db = get_db()
    topics = [r["topic"] for r in db.execute("SELECT DISTINCT topic FROM questions ORDER BY topic")]
    users = {_norm_email(u["email"]): u for u in db.execute("SELECT * FROM users WHERE role='student'").fetchall()}

    def row_for(name, display_email, norm_email=None):
        u = users.get(norm_email or display_email)
        if not u:
            return {"name": name, "email": display_email, "signed_in": False}
        st = user_stats(db, u["id"])
        last = db.execute("SELECT MAX(created_at) m FROM attempts WHERE user_id=?", (u["id"],)).fetchone()["m"]
        return {"name": name, "email": display_email, "signed_in": True, "stats": st,
                "by_topic": {m["topic"]: m for m in st["mastery"]},
                "last": (datetime.fromisoformat(last).astimezone(SGT).strftime("%d %b %H:%M") if last else "-")}

    tmap = []
    for year, _slug, p1, p2 in reversed(papers_data.YEARS):
        tmap.append({"year": year, "paper": "P2", "cells": {q: ts for q, ts in p2}})
        tmap.append({"year": year, "paper": "P1", "cells": {q: ts for q, ts in p1}})
    fb = [{"id": r["id"], "useful": bool(r["useful"]),
           "name": r["uname"] or r["uemail"], "qlabel": r["qlabel"], "qurl": r["qurl"],
           "message": r["message"],
           "ts": datetime.fromisoformat(r["created_at"]).astimezone(SGT).strftime("%d %b %H:%M")}
          for r in db.execute("""SELECT f.*, u.name uname, u.email uemail FROM feedback f
                                 JOIN users u ON u.id=f.user_id ORDER BY f.id DESC LIMIT 100""").fetchall()]
    roster = [{"name": r["name"], "email": r["email"], "norm": _norm_email(r["email"]), "class": r["class"]}
              for r in db.execute("SELECT name,email,class FROM roster").fetchall()]
    if not roster:
        roster = ROSTER_ENV
    if roster:
        groups = []
        for label, classes in ROSTER_GROUPS:
            members = [r for r in roster if r["class"] in classes]
            rows = [row_for(r["name"], r.get("email") or r["norm"], r["norm"]) for r in members]
            rows.sort(key=lambda r: (not r["signed_in"], -(r["stats"]["xp"] if r["signed_in"] else 0)))
            groups.append({"label": label, "rows": rows})
        return render_template("teacher.html", groups=groups, topics=topics, roster=True, fb=fb, tmap=tmap)

    rows = [row_for(u["name"] or u["email"], u["email"], _norm_email(u["email"])) for u in users.values()]
    rows = [r for r in rows if r["signed_in"]]
    rows.sort(key=lambda r: -r["stats"]["xp"])
    return render_template("teacher.html", groups=[{"label": "Signed-in students", "rows": rows}],
                           topics=topics, roster=False, fb=fb, tmap=tmap)

@app.route("/teacher/admin/roster", methods=["GET", "POST"])
@teacher_required
def roster_admin():
    db = get_db()
    if request.method == "POST":
        text = request.form.get("roster_text", "")
        entries = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            bits = line.split(":", 2)
            if len(bits) != 3 or "@" not in bits[2]:
                continue
            cls, name, email = (b.strip() for b in bits)
            entries.append((_norm_email(email), name, cls))
        db.execute("DELETE FROM roster")
        db.executemany("INSERT INTO roster(email,name,class) VALUES(?,?,?)", entries)
        db.commit()
        return redirect(url_for("roster_admin", saved=len(entries)))
    rows = db.execute("SELECT * FROM roster ORDER BY class, name").fetchall()
    current = "\n".join(f"{r['class']}:{r['name']}:{r['email']}" for r in rows)
    return render_template("roster.html", current=current, saved=request.args.get("saved"),
                           count=len(rows))

@app.route("/healthz")
def healthz():
    return {"ok": True}

@app.errorhandler(403)
def forbidden(e):
    return render_template("denied.html", reason="Teachers only."), 403

@app.route("/sw.js")
def service_worker():
    return send_from_directory("static", "sw.js", mimetype="application/javascript")

init_db()



# ---------------- teacher question bank ----------------

def _topics(db):
    return [r["topic"] for r in db.execute("SELECT DISTINCT topic FROM questions ORDER BY topic")]

@app.route("/teacher/questions")
@teacher_required
def bank():
    db = get_db()
    topic = request.args.get("topic") or ""
    if topic:
        qs = db.execute("SELECT * FROM questions WHERE topic=? ORDER BY id", (topic,)).fetchall()
    else:
        qs = db.execute("SELECT * FROM questions ORDER BY topic, id").fetchall()
    items = [{"q": q, "opts": db.execute("SELECT * FROM options WHERE question_id=? ORDER BY ord", (q["id"],)).fetchall()}
             for q in qs]
    return render_template("bank.html", items=items, topics=_topics(db), topic=topic)

def _read_qform(count=None):
    """Parse the add/edit form. count forces exactly that many option rows (edit);
    None (add) drops blank rows."""
    texts = [t.strip() for t in request.form.getlist("opt_text")]
    if count is not None:
        texts = (texts + [""] * count)[:count]
    corrects = set(request.form.getlist("opt_correct"))
    opts = []
    for i, t in enumerate(texts):
        if count is not None or t or str(i) in corrects:
            opts.append({"text": t, "correct": str(i) in corrects})
    form = {
        "topic": request.form.get("topic", "").strip(),
        "paper": request.form.get("paper", "").strip() or "P1",
        "qtype": request.form.get("qtype", "mcq"),
        "stem": request.form.get("stem", "").strip(),
        "code": request.form.get("code", "").strip(),
        "explanation": request.form.get("explanation", "").strip(),
        "misconception": request.form.get("misconception", "").strip(),
        "case_sensitive": bool(request.form.get("case_sensitive")),
        "opts": opts,
    }
    errs = []
    if not form["topic"]:
        errs.append("Topic is required.")
    if form["qtype"] not in ("mcq", "checkbox", "fib", "binary"):
        errs.append("Type must be mcq, checkbox, fib or binary.")
    if not form["stem"]:
        errs.append("The question stem is required.")
    if not form["explanation"]:
        errs.append("The Why explanation is required.")
    if form["qtype"] == "binary" and len(opts) != 2:
        errs.append("A binary question needs exactly two options.")
    elif len(opts) < (1 if form["qtype"] == "fib" else 2):
        errs.append("At least one accepted answer is required." if form["qtype"] == "fib" else "At least two options are required.")
    elif any(not o["text"] for o in opts):
        errs.append("Every option needs text.")
    nc = sum(1 for o in opts if o["correct"])
    if form["qtype"] in ("mcq", "binary") and nc != 1:
        errs.append("This type needs exactly one correct option ticked.")
    if form["qtype"] == "checkbox" and nc < 2:
        errs.append("A checkbox question needs at least two correct options ticked.")
    if form["qtype"] == "fib":
        for o in form["opts"]:
            o["correct"] = True  # every listed answer is an accepted answer
    return form, errs

def _insert_question(db, form):
    cur = db.execute(
        "INSERT INTO questions(topic,paper,qtype,stem,explanation,misconception,code,case_sensitive) VALUES(?,?,?,?,?,?,?,?)",
        (form["topic"], form["paper"], form["qtype"], form["stem"], form["explanation"], form["misconception"], form["code"],
         1 if form["case_sensitive"] else 0))
    qid = cur.lastrowid
    for i, o in enumerate(form["opts"]):
        db.execute("INSERT INTO options(question_id,ord,text,is_correct) VALUES(?,?,?,?)",
                   (qid, i, o["text"], 1 if o["correct"] else 0))
    return qid

@app.route("/teacher/questions/new", methods=["GET", "POST"])
@teacher_required
def bank_new():
    db = get_db()
    if request.method == "POST":
        form, errs = _read_qform()
        if not errs:
            qid = _insert_question(db, form)
            db.commit()
            return redirect(url_for("bank_edit", qid=qid, saved=1))
        return render_template("qform.html", form=form, errs=errs, topics=_topics(db),
                               qid=None, natt=None, saved=None), 400
    form = {"topic": "", "paper": "P1", "qtype": "mcq", "stem": "", "explanation": "",
            "misconception": "", "code": "", "case_sensitive": False,
            "opts": [{"text": "", "correct": False} for _ in range(4)]}
    return render_template("qform.html", form=form, errs=[], topics=_topics(db),
                           qid=None, natt=None, saved=None)

@app.route("/teacher/questions/<int:qid>/edit", methods=["GET", "POST"])
@teacher_required
def bank_edit(qid):
    db = get_db()
    q, opts = load_question(db, qid)
    if not q:
        abort(404)
    n = len(opts)
    natt = db.execute("SELECT COUNT(*) c FROM attempts WHERE question_id=?", (qid,)).fetchone()["c"]
    if request.method == "POST":
        form, errs = _read_qform(count=n)
        if not errs:
            db.execute(
                "UPDATE questions SET topic=?,paper=?,qtype=?,stem=?,explanation=?,misconception=?,code=?,case_sensitive=? WHERE id=?",
                (form["topic"], form["paper"], form["qtype"], form["stem"],
                 form["explanation"], form["misconception"], form["code"],
                 1 if form["case_sensitive"] else 0, qid))
            for o, row in zip(form["opts"], opts):
                db.execute("UPDATE options SET text=?, is_correct=? WHERE id=?",
                           (o["text"], 1 if o["correct"] else 0, row["id"]))
            db.commit()
            return redirect(url_for("bank_edit", qid=qid, saved=1))
        return render_template("qform.html", form=form, errs=errs, topics=_topics(db),
                               qid=qid, natt=natt, saved=None), 400
    form = {"topic": q["topic"], "paper": q["paper"], "qtype": q["qtype"], "stem": q["stem"],
            "explanation": q["explanation"], "misconception": q["misconception"] or "", "code": q["code"] or "",
            "case_sensitive": bool(q["case_sensitive"]),
            "opts": [{"text": o["text"], "correct": bool(o["is_correct"])} for o in opts]}
    return render_template("qform.html", form=form, errs=[], topics=_topics(db),
                           qid=qid, natt=natt, saved=request.args.get("saved"))


@app.route("/teacher/admin/reset-bank", methods=["POST"])
@teacher_required
def bank_reset():
    """Re-seed the bundled question bank. Only allowed while no student attempts
    exist, so live stats can never be wiped. Teacher-added questions are removed too."""
    db = get_db()
    natt = db.execute("SELECT COUNT(*) c FROM attempts").fetchone()["c"]
    if natt:
        abort(409)
    db.execute("DELETE FROM options")
    db.execute("DELETE FROM questions")
    db.commit()
    seed_questions(db)
    n = db.execute("SELECT COUNT(*) c FROM questions").fetchone()["c"]
    return redirect(url_for("bank", reset=n))


# ---------------- tier 3 (write full code, tested in the browser) ----------------

MAX_T3_PARTS = 6

@app.route("/t3/<int:qid>")
@login_required
def t3_question(qid):
    db = get_db()
    u = current_user()
    q = db.execute("SELECT * FROM t3_questions WHERE id=?", (qid,)).fetchone()
    if not q:
        abort(404)
    parts = db.execute("SELECT * FROM t3_parts WHERE question_id=? ORDER BY ord", (qid,)).fetchall()
    prog = {r["ord"]: bool(r["passed"]) for r in db.execute(
        """SELECT p.ord, MAX(a.passed) passed FROM t3_parts p
           LEFT JOIN t3_attempts a ON a.part_id=p.id AND a.user_id=?
           WHERE p.question_id=? GROUP BY p.ord""", (u["id"], qid)).fetchall()}
    return render_template("t3q.html", q=q, parts=parts, prog=prog)

@app.route("/t3/<int:qid>/part/<int:ord>")
@login_required
def t3_part(qid, ord):
    db = get_db()
    u = current_user()
    q = db.execute("SELECT * FROM t3_questions WHERE id=?", (qid,)).fetchone()
    if not q:
        abort(404)
    parts = db.execute("SELECT * FROM t3_parts WHERE question_id=? ORDER BY ord", (qid,)).fetchall()
    if ord < 1 or ord > len(parts):
        abort(404)
    part = dict(parts[ord - 1])
    if q["kind"] == "theory":
        last = db.execute(
            """SELECT a.code FROM t3_attempts a JOIN t3_parts p ON p.id=a.part_id
               WHERE a.user_id=? AND p.question_id=? AND p.ord=? ORDER BY a.id DESC LIMIT 1""",
            (u["id"], qid, ord)).fetchone()
        passed = db.execute(
            """SELECT 1 FROM t3_attempts a JOIN t3_parts p ON p.id=a.part_id
               WHERE a.user_id=? AND p.question_id=? AND p.ord=? AND a.passed=1 LIMIT 1""",
            (u["id"], qid, ord)).fetchone() is not None
        attempted = db.execute(
            """SELECT 1 FROM t3_attempts a JOIN t3_parts p ON p.id=a.part_id
               WHERE a.user_id=? AND p.question_id=? AND p.ord=? LIMIT 1""",
            (u["id"], qid, ord)).fetchone() is not None
        return render_template("t3theory.html", q=q, part=part, ord=ord, nparts=len(parts),
                               code=last["code"] if last else "", passed=passed, attempted=attempted)
    part["tests"] = T3_TEST_PREAMBLE + "\n" + rewrite_t3_tests(part["tests"])
    prev = None
    if ord > 1:
        row = db.execute(
            """SELECT a.code FROM t3_attempts a JOIN t3_parts p ON p.id=a.part_id
               WHERE a.user_id=? AND p.question_id=? AND p.ord=? AND a.passed=1
               ORDER BY a.id DESC LIMIT 1""",
            (u["id"], qid, ord - 1)).fetchone()
        prev = row["code"] if row else None
    if prev is None:
        code = "\n\n".join(p["starter"] for p in parts[:ord] if p["starter"].strip())
    else:
        code = prev + ("\n\n" + part["starter"] if part["starter"].strip() else "")
    passed = db.execute(
        """SELECT 1 FROM t3_attempts a JOIN t3_parts p ON p.id=a.part_id
           WHERE a.user_id=? AND p.question_id=? AND p.ord=? AND a.passed=1 LIMIT 1""",
        (u["id"], qid, ord)).fetchone() is not None
    attempted = db.execute(
        """SELECT 1 FROM t3_attempts a JOIN t3_parts p ON p.id=a.part_id
           WHERE a.user_id=? AND p.question_id=? AND p.ord=? LIMIT 1""",
        (u["id"], qid, ord)).fetchone() is not None
    return render_template("t3.html", q=q, part=part, ord=ord, nparts=len(parts),
                           code=code, passed=passed, attempted=attempted)

@app.route("/t3/<int:qid>/part/<int:ord>/attempt", methods=["POST"])
@login_required
def t3_record(qid, ord):
    db = get_db()
    u = current_user()
    part = db.execute("SELECT * FROM t3_parts WHERE question_id=? AND ord=?", (qid, ord)).fetchone()
    if not part:
        abort(404)
    data = request.get_json(force=True, silent=True) or {}
    code = str(data.get("code", ""))[:20000]
    passed = 1 if data.get("passed") else 0
    output = str(data.get("output", ""))[:4000]
    if passed:
        best = db.execute("SELECT COALESCE(MAX(xp),0) b FROM t3_attempts WHERE user_id=? AND part_id=?",
                          (u["id"], part["id"])).fetchone()["b"]
        xp = 2 if best > 0 else 15
    else:
        xp = 0
    db.execute("INSERT INTO t3_attempts(user_id,part_id,passed,xp,code,output,created_at) VALUES(?,?,?,?,?,?,?)",
               (u["id"], part["id"], passed, xp, code, output, datetime.now(timezone.utc).isoformat()))
    db.commit()
    return {"ok": True, "passed": bool(passed), "xp": xp, "total_xp": user_stats(db, u["id"])["xp"]}

@app.route("/t3/<int:qid>/part/<int:ord>/check", methods=["POST"])
@login_required
def t3_check(qid, ord):
    db = get_db()
    u = current_user()
    q = db.execute("SELECT * FROM t3_questions WHERE id=?", (qid,)).fetchone()
    part = db.execute("SELECT * FROM t3_parts WHERE question_id=? AND ord=?", (qid, ord)).fetchone()
    if not q or not part or q["kind"] != "theory":
        abort(404)
    data = request.get_json(force=True, silent=True) or {}
    text = str(data.get("text", ""))[:20000]
    res = grade_theory(text, json.loads(part["rubric"]))
    passed = 1 if res["passed"] else 0
    if passed:
        best = db.execute("SELECT COALESCE(MAX(xp),0) b FROM t3_attempts WHERE user_id=? AND part_id=?",
                          (u["id"], part["id"])).fetchone()["b"]
        xp = 2 if best > 0 else 15
    else:
        xp = 0
    db.execute("INSERT INTO t3_attempts(user_id,part_id,passed,xp,code,output,created_at) VALUES(?,?,?,?,?,?,?)",
               (u["id"], part["id"], passed, xp, text,
                json.dumps({"greens": res["greens"], "total": res["total"]}),
                datetime.now(timezone.utc).isoformat()))
    db.commit()
    res.update({"ok": True, "xp": xp, "total_xp": user_stats(db, u["id"])["xp"]})
    return res

# ---------------- student feedback ----------------
# Per-question Feedback button -> teacher dashboard. Server-side guards keep out
# trivial or junk notes; nothing here is public, only teachers see the list.

FB_USEFUL_XP = 5

TRIVIAL_WORDS = {"hi", "hello", "hey", "test", "testing", "ok", "okay", "k", "lol",
                 "idk", "nothing", "yes", "no", "asdf", "qwerty", "abc", "zzz",
                 "haha", "hehe", "blah", "yo", "sup"}

FB_SHORT_ERR = ("That looks too short or unclear to act on. "
                "Please describe the error, issue or idea in a sentence or two.")

# ---------------- tier 3 speed drills ----------------
def _short_name(u):
    n = (u["name"] or u["email"].split("@")[0]).strip()
    parts = n.split()
    return parts[0] + (" " + parts[1][0] + "." if len(parts) > 1 else "")

def _roster_lookup(db):
    """norm email -> (full name, class) from the roster table, else the ROSTER env. Class is never invented."""
    rows = [(_norm_email(r["email"]), r["name"], r["class"]) for r in db.execute("SELECT email,name,class FROM roster")]
    if not rows:
        rows = [(r["norm"], r["name"], r["class"]) for r in ROSTER_ENV]
    return {e: (n, c) for e, n, c in rows}

def _speed_board(db, algo, uid):
    roster = _roster_lookup(db)
    rows = db.execute(
        """SELECT a.id AS aid, a.user_id, a.mode, a.elapsed_ms, u.name, u.email FROM speed_attempts a
           JOIN users u ON u.id=a.user_id
           WHERE a.algo=? AND a.passed=1 AND (a.flagged=0 OR a.cleared=1) AND u.role='student'
           ORDER BY a.elapsed_ms ASC, a.id ASC""", (algo,)).fetchall()
    seen, board = set(), []
    for r in rows:
        if r["user_id"] in seen:
            continue
        seen.add(r["user_id"])
        rn, rc = roster.get(_norm_email(r["email"]), (None, None))
        board.append({"rank": len(board) + 1, "me": r["user_id"] == uid, "aid": r["aid"],
                      "name": rn or r["name"] or "Student", "cls": rc or "",
                      "mode": r["mode"], "ms": r["elapsed_ms"], "band": speed_data.band(r["elapsed_ms"], algo)})
    return board

def _fmt_ms(ms):
    tenths = int(ms // 100)
    return "%d:%02d.%d" % (tenths // 600, (tenths // 10) % 60, tenths % 10)
app.jinja_env.filters["fmt_ms"] = _fmt_ms

def _fmt_ms_up(ms):
    """Tile display: round UP to the next tenth, so a time just over a limit never shows as the limit itself."""
    tenths = -(-int(ms) // 100)
    return "%d:%02d.%d" % (tenths // 600, (tenths // 10) % 60, tenths % 10)
app.jinja_env.filters["fmt_ms_up"] = _fmt_ms_up

@app.route("/speed")
@login_required
def speed_index():
    db = get_db()
    u = current_user()
    items = []
    for a in speed_data.ALGOS:
        best = db.execute(
            """SELECT MIN(elapsed_ms) m FROM speed_attempts WHERE user_id=? AND algo=? AND passed=1
               AND (flagged=0 OR cleared=1)""", (u["id"], a["slug"])).fetchone()["m"]
        items.append({"slug": a["slug"], "title": a["title"], "best": best,
                      "band": speed_data.band(best, a["slug"]) if best is not None else "",
                      "group": a["group"], "limit_min": a["limit_min"]})
    tiles = None
    if u["role"] != "teacher" and comp.CONFIRMED:
        cls = _roster_lookup(db).get(_norm_email(u["email"]), (None, None))[1]
        w = comp.student_window(cls, datetime.now(SGT))
        j = comp.get_join(db, u["id"]) if w else None
        if w and j and datetime.now(SGT) < comp.personal_end(w, j):
            tiles = _comp_tiles(db, u["id"])
    return render_template("speed_index.html", items=items, tiles=tiles)

@app.route("/speed/<slug>")
@login_required
def speed_algo(slug):
    a = speed_data.BY_SLUG.get(slug)
    if not a:
        abort(404)
    db = get_db()
    u = current_user()
    mine = db.execute(
        """SELECT mode, elapsed_ms, passed, flagged, cleared, flag_note, started_at FROM speed_attempts
           WHERE user_id=? AND algo=? ORDER BY id DESC LIMIT 8""", (u["id"], slug)).fetchall()
    hist = []
    for r in mine:
        hist.append({"mode": r["mode"], "passed": bool(r["passed"]), "ms": r["elapsed_ms"],
                     "band": speed_data.band(r["elapsed_ms"], slug) if r["passed"] else "",
                     "flagged": bool(r["flagged"]) and not r["cleared"],
                     "edge": _edge_reason(slug, r["flag_note"]) if r["flagged"] and not r["cleared"] else "",
                     "other_flag": bool(r["flagged"]) and not r["cleared"] and any(
                         k in (r["flag_note"] or "") for k in ("Suspected paste", "Logic check", "Held by teacher")),
                     "when": datetime.fromisoformat(r["started_at"]).astimezone(SGT).strftime("%d %b %H:%M")})
    example = ""
    if u["role"] == "teacher":
        example = speed_examples.EXAMPLES.get(slug, "")
    elif comp.CONFIRMED:
        cls = _roster_lookup(db).get(_norm_email(u["email"]), (None, None))[1]
        if comp.student_window(cls, datetime.now(SGT)):
            example = speed_examples.EXAMPLES.get(slug, "")
    return render_template("speed_algo.html", a=a, example=example, board=_speed_board(db, slug, u["id"]), hist=hist,
                           tests=speed_data.PRE + "\n" + speed_data.instrument(slug)[0], cktotal=speed_data.instrument(slug)[1])

@app.route("/speed/<slug>/code/<int:aid>")
@login_required
def speed_code(slug, aid):
    """Code behind one leaderboard time. Only an attempt currently shown on this algorithm's board
    (a student's best, passed, not held) can be opened, by any signed-in user. Returned as JSON text."""
    if slug not in speed_data.BY_SLUG:
        abort(404)
    db = get_db()
    u = current_user()
    entry = next((r for r in _speed_board(db, slug, u["id"]) if r["aid"] == aid), None)
    if not entry:
        abort(404)
    row = db.execute("SELECT code FROM speed_attempts WHERE id=?", (aid,)).fetchone()
    return jsonify({"name": entry["name"], "cls": entry["cls"], "mode": entry["mode"],
                    "time": _fmt_ms(entry["ms"]), "code": row["code"] if row else ""})

@app.route("/speed/<slug>/start", methods=["POST"])
@login_required
def speed_start(slug):
    if slug not in speed_data.BY_SLUG:
        abort(404)
    data = request.get_json(force=True, silent=True) or {}
    mode = "drill" if data.get("mode") == "drill" else "practice"
    db = get_db()
    u = current_user()
    cur = db.execute("INSERT INTO speed_attempts(user_id,algo,mode,started_at) VALUES(?,?,?,?)",
                     (u["id"], slug, mode, datetime.now(timezone.utc).isoformat()))
    db.commit()
    return {"ok": True, "id": cur.lastrowid}

@app.route("/speed/<slug>/run/<int:aid>", methods=["POST"])
@login_required
def speed_run(slug, aid):
    db = get_db()
    u = current_user()
    row = db.execute("SELECT * FROM speed_attempts WHERE id=? AND user_id=? AND algo=?",
                     (aid, u["id"], slug)).fetchone()
    if not row:
        abort(404)
    if row["passed"]:
        return {"ok": True, "done": True, "ms": row["elapsed_ms"]}
    data = request.get_json(force=True, silent=True) or {}
    code = str(data.get("code", ""))[:20000]
    flags = ["Suspected paste: " + str(x)[:160] for x in (data.get("flags") or [])][:20]
    pastes = int(data.get("paste_count") or 0)
    passed = 1 if data.get("passed") else 0
    if passed:
        # Student code is never executed on the server. The pass/fail comes from the browser,
        # so rankings rely on suspicion flags (paste, logic check) and teacher review.
        flags += ["Logic check: " + n for n in speed_data.logic_notes(slug, code)]
        flags += ["Edge case: " + n for n in speed_data.edge_notes(slug, code)]
    flagged = 1 if flags else 0
    now = datetime.now(timezone.utc)
    ms = int((now - datetime.fromisoformat(row["started_at"])).total_seconds() * 1000) if passed else 0
    total = speed_data.instrument(slug)[1] or 1
    try:
        ck_done = max(0, int(data.get("ck_done") or 0))
    except (TypeError, ValueError):
        ck_done = 0
    frac = 1.0 if passed else min(ck_done, total - 1) / total
    db.execute(
        """UPDATE speed_attempts SET runs=runs+1, code=?, paste_count=?, flagged=?, flag_note=?,
           passed=?, elapsed_ms=?, finished_at=?, ck_frac=MAX(ck_frac, ?), ck_at=? WHERE id=?""",
        (code, pastes, flagged, "; ".join(flags), passed, ms, now.isoformat() if passed else "", frac, now.isoformat(), aid))
    db.commit()
    out = {"ok": True, "done": bool(passed), "ms": ms, "flagged": bool(flagged),
           "paste_flag": any(f.startswith("Suspected paste") for f in flags),
           "logic_flag": any(f.startswith("Logic check") for f in flags),
           "edge_flag": any(f.startswith("Edge case") for f in flags),
           "edge_text": _edge_reason(slug, "; ".join(flags)) if any(f.startswith("Edge case") for f in flags) else ""}
    if passed:
        out["band"] = speed_data.band(ms, slug)
    return out

@app.route("/teacher/speed")
@teacher_required
def teacher_speed():
    db = get_db()
    rows = db.execute(
        """SELECT a.*, u.name, u.email FROM speed_attempts a JOIN users u ON u.id=a.user_id
           WHERE u.role='student' ORDER BY a.id DESC LIMIT 300""").fetchall()
    items = []
    for r in rows:
        items.append({"id": r["id"], "name": r["name"] or r["email"], "email": r["email"],
                      "algo": speed_data.BY_SLUG[r["algo"]]["title"] if r["algo"] in speed_data.BY_SLUG else r["algo"],
                      "mode": r["mode"], "passed": bool(r["passed"]), "ms": r["elapsed_ms"], "runs": r["runs"],
                      "band": speed_data.band(r["elapsed_ms"], r["algo"]) if r["passed"] else "",
                      "flagged": bool(r["flagged"]), "cleared": bool(r["cleared"]), "note": r["flag_note"],
                      "pastes": r["paste_count"], "code": r["code"],
                      "when": datetime.fromisoformat(r["started_at"]).astimezone(SGT).strftime("%d %b %H:%M")})
    return render_template("teacher_speed.html", items=items)

@app.route("/teacher/speed/<int:aid>/toggle", methods=["POST"])
@teacher_required
def teacher_speed_toggle(aid):
    db = get_db()
    row = db.execute("SELECT flagged FROM speed_attempts WHERE id=?", (aid,)).fetchone()
    if row and row["flagged"]:
        db.execute("UPDATE speed_attempts SET cleared=1-cleared WHERE id=?", (aid,))
    elif row:
        db.execute("UPDATE speed_attempts SET flagged=1, cleared=0, flag_note='Held by teacher' WHERE id=?", (aid,))
    db.commit()
    return redirect(url_for("teacher_speed"))

# ---------------- timed competition ----------------
def _comp_view(preview):
    db = get_db()
    u = current_user()
    now = datetime.now(SGT)
    roster = _roster_lookup(db)
    board = comp.standings(db, _roster_lookup, _norm_email)
    cls = roster.get(_norm_email(u["email"]), (None, None))[1]
    w = comp.window_for_class(cls) if not preview else None
    return db, u, now, board, cls, w

def _tile_band(ms, limit_ms):
    """Competition tiles only: green at or under the limit, orange up to and including 1 minute over, red beyond.
    (The practice boards keep speed_data.band, where exactly limit+1:00 is red.)"""
    if ms is None: return "todo"
    if ms <= limit_ms: return "green"
    return "orange" if ms <= limit_ms + 60000 else "red"

def _comp_tiles(db, uid):
    """Compact tile data for the sprint: every drill, coloured by the student's best valid in-clock time
    (green within the drill's limit, orange within one minute over, red beyond, grey = no finished lap yet)."""
    bests = {}
    if uid:
        for p in comp.standings(db, _roster_lookup, _norm_email):
            if p["uid"] == uid:
                bests = p["bests"]
    tiles = []
    for x in speed_data.ALGOS:
        b = bests.get(x["slug"])
        tiles.append({"slug": x["slug"], "title": x["title"], "group": x["group"], "limit_min": x["limit_min"],
                      "best": b, "band": _tile_band(b, x["limit_ms"])})
    return tiles

@app.route("/comp")
@login_required
def comp_page():
    u = current_user()
    if u["role"] == "teacher":
        return redirect(url_for("teacher_comp"))
    db = get_db()
    now = datetime.now(SGT)
    cls = _roster_lookup(db).get(_norm_email(u["email"]), (None, None))[1]
    w = comp.student_window(cls, now)
    if not w:
        abort(404)
    board = comp.standings(db, _roster_lookup, _norm_email)
    joined = comp.get_join(db, u["id"])
    pend = comp.personal_end(w, joined) if joined else None
    left = int((pend - now).total_seconds()) if pend else 0
    return render_template("comp.html", c=comp, w=w, board=board, me=u["id"], preview=False, joined=bool(joined),
                           done=bool(joined) and left <= 0, capped=bool(pend) and pend == w["end"] and joined is not None,
                           end_iso=pend.isoformat() if pend else "", left_s=max(left, 0),
                           cutoff=w["end"].strftime("%H:%M"), tiles=_comp_tiles(db, u["id"]))

@app.route("/comp/join", methods=["POST"])
@login_required
def comp_join():
    u = current_user()
    if u["role"] == "teacher":
        abort(403)
    db = get_db()
    now = datetime.now(SGT)
    cls = _roster_lookup(db).get(_norm_email(u["email"]), (None, None))[1]
    if not comp.student_window(cls, now):
        abort(404)
    db.execute("INSERT OR IGNORE INTO comp_joins(user_id, joined_at) VALUES(?,?)", (u["id"], now.isoformat()))
    db.commit()
    return redirect(url_for("comp_page"))

def _lastday_render(preview):
    u = current_user()
    db = get_db()
    now = datetime.now(SGT)
    rows = lastday.board(db, _roster_lookup, _norm_email, speed_data.ALGOS, _tile_band)
    return render_template("lastday.html", ld=lastday, rows=rows, algos=speed_data.ALGOS, me=u["id"], preview=preview,
                           state="open" if lastday.is_open(now) else ("upcoming" if now < lastday.OPENS else "closed"),
                           opens=lastday.OPENS.strftime("%a %-d %b %H:%M"), closes=lastday.CLOSES.strftime("%a %-d %b %H:%M"))

@app.route("/lastday")
@login_required
def lastday_page():
    u = current_user()
    if u["role"] == "teacher":
        return redirect(url_for("teacher_lastday"))
    db = get_db()
    cls = _roster_lookup(db).get(_norm_email(u["email"]), (None, None))[1]
    if cls not in lastday.CLASS_ORDER or not lastday.is_open(datetime.now(SGT)):
        abort(404)
    return _lastday_render(False)

@app.route("/teacher/lastday")
@teacher_required
def teacher_lastday():
    return _lastday_render(True)

@app.route("/teacher/comp")
@teacher_required
def teacher_comp():
    db = get_db()
    now = datetime.now(SGT)
    board = comp.standings(db, _roster_lookup, _norm_email)
    wins = [{"label": w["label"], "start": w["start"].strftime("%a %-d %b %H:%M"), "end": w["end"].strftime("%H:%M"),
             "mins": int((w["end"] - w["start"]).total_seconds() // 60), "state": comp.state(w, now)} for w in comp.WINDOWS]
    return render_template("comp.html", c=comp, w=comp.WINDOWS[0], board=board, me=0, preview=True,
                           wins=wins, now=now.strftime("%a %-d %b %H:%M"), end_iso="", left_s=comp.PERSONAL_MIN * 60,
                           joined=False, done=False, capped=False, cutoff="", tiles=_comp_tiles(db, 0))

@app.route("/teacher/comp/override", methods=["POST"])
@teacher_required
def teacher_comp_override():
    db = get_db()
    try:
        uid = int(request.form.get("uid", ""))
    except ValueError:
        abort(400)
    raw = request.form.get("partial", "").strip()
    if raw == "":
        db.execute("DELETE FROM comp_override WHERE user_id=?", (uid,))
    else:
        try:
            val = max(0.0, min(float(raw), 9.99))
        except ValueError:
            abort(400)
        db.execute("INSERT INTO comp_override(user_id, partial) VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET partial=excluded.partial", (uid, val))
    db.commit()
    return redirect(url_for("teacher_comp"))

@app.route("/feedback", methods=["POST"])
@login_required
def send_feedback():
    db = get_db()
    u = current_user()
    data = request.get_json(force=True, silent=True) or {}
    qref = str(data.get("qref", ""))[:40].strip()
    qlabel = str(data.get("qlabel", ""))[:200].strip()
    qurl = str(data.get("qurl", ""))[:200].strip()
    if not qurl.startswith("/") or qurl.startswith("//"):
        qurl = ""
    msg = " ".join(str(data.get("message", "")).split())[:1000]
    words = [w.strip(".,!?;:") for w in msg.lower().split() if w.strip(".,!?;:")]
    letters = re.sub(r"[^a-z]", "", msg.lower())
    err = ""
    if not qref or not qlabel:
        err = "Something went wrong identifying this question - please reload and try again."
    elif len(msg) < 12 or len(words) < 3 or len(set(letters)) < 4 or all(w in TRIVIAL_WORDS for w in words):
        err = FB_SHORT_ERR
    if not err:
        last = db.execute("SELECT message FROM feedback WHERE user_id=? ORDER BY id DESC LIMIT 1",
                          (u["id"],)).fetchone()
        if last and last["message"] == msg:
            err = "You have already sent that exact message."
    if not err:
        since = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
        cnt = db.execute("SELECT COUNT(*) c FROM feedback WHERE user_id=? AND created_at>=?",
                         (u["id"], since)).fetchone()["c"]
        if cnt >= 5:
            err = "You have sent several notes in the last few minutes - please wait a little before sending more."
    if err:
        return {"ok": False, "error": err}
    db.execute("INSERT INTO feedback(user_id,qref,qlabel,qurl,message,created_at) VALUES(?,?,?,?,?,?)",
               (u["id"], qref, qlabel, qurl, msg, datetime.now(timezone.utc).isoformat()))
    db.commit()
    return {"ok": True}

@app.route("/teacher/feedback/<int:fid>/ack", methods=["POST"])
@teacher_required
def feedback_ack(fid):
    # toggle: mark a note useful (+FB_USEFUL_XP XP to the student) or undo
    db = get_db()
    row = db.execute("SELECT useful FROM feedback WHERE id=?", (fid,)).fetchone()
    if not row:
        abort(404)
    if row["useful"]:
        db.execute("UPDATE feedback SET useful=0, useful_at='' WHERE id=?", (fid,))
    else:
        db.execute("UPDATE feedback SET useful=1, useful_at=? WHERE id=?",
                   (datetime.now(timezone.utc).isoformat(), fid))
    db.commit()
    return redirect(url_for("teacher") + "#feedback")

# ---------------- teacher tier 3 authoring ----------------

def _t3_form():
    form = {"topic": request.form.get("topic", "").strip(),
            "title": request.form.get("title", "").strip(),
            "intro": request.form.get("intro", "").strip(), "parts": []}
    ins = request.form.getlist("part_instruction")
    st = request.form.getlist("part_starter")
    te = request.form.getlist("part_tests")
    mo = request.form.getlist("part_model")
    for i in range(len(ins)):
        if ins[i].strip() or st[i].strip() or te[i].strip() or mo[i].strip():
            form["parts"].append({"instruction": ins[i].strip(), "starter": st[i],
                                  "tests": te[i], "model": mo[i]})
    errs = []
    if not form["topic"]:
        errs.append("Topic is required.")
    if not form["title"]:
        errs.append("A title is required.")
    if not form["parts"]:
        errs.append("Add at least one part.")
    if len(form["parts"]) > MAX_T3_PARTS:
        errs.append(f"At most {MAX_T3_PARTS} parts.")
    for i, p in enumerate(form["parts"], 1):
        if not p["instruction"]:
            errs.append(f"Part {i}: instruction is required.")
        if not p["tests"].strip():
            errs.append(f"Part {i}: tests are required (Python asserts run after the student's code).")
        if not p["model"].strip():
            errs.append(f"Part {i}: model answer is required.")
    return form, errs

def _t3_part_stats(db, qid):
    return db.execute(
        """SELECT p.ord, p.instruction,
                  COUNT(DISTINCT CASE WHEN a.passed=1 THEN a.user_id END) passed_users,
                  COUNT(DISTINCT a.user_id) tried_users, COUNT(a.id) attempts
           FROM t3_parts p LEFT JOIN t3_attempts a ON a.part_id=p.id
           WHERE p.question_id=? GROUP BY p.ord ORDER BY p.ord""", (qid,)).fetchall()

@app.route("/teacher/t3")
@teacher_required
def t3_admin():
    db = get_db()
    qs = [{"q": q, "stats": _t3_part_stats(db, q["id"])} for q in
          db.execute("SELECT * FROM t3_questions ORDER BY id").fetchall()]
    return render_template("t3admin.html", qs=qs)

@app.route("/teacher/t3/new", methods=["GET", "POST"])
@teacher_required
def t3_new():
    db = get_db()
    if request.method == "POST":
        form, errs = _t3_form()
        if not errs:
            cur = db.execute("INSERT INTO t3_questions(topic,title,intro,created_at) VALUES(?,?,?,?)",
                             (form["topic"], form["title"], form["intro"],
                              datetime.now(timezone.utc).isoformat()))
            qid = cur.lastrowid
            for i, p in enumerate(form["parts"], 1):
                db.execute("INSERT INTO t3_parts(question_id,ord,instruction,starter,tests,model) VALUES(?,?,?,?,?,?)",
                           (qid, i, p["instruction"], p["starter"], p["tests"], p["model"]))
            db.commit()
            return redirect(url_for("t3_admin", saved=form["title"]))
        return render_template("t3form.html", form=form, errs=errs, qid=None,
                               nblocks=max(3, len(form["parts"]) + 1)), 400
    form = {"topic": "", "title": "", "intro": "",
            "parts": [{"instruction": "", "starter": "", "tests": "", "model": ""} for _ in range(3)]}
    return render_template("t3form.html", form=form, errs=[], qid=None, nblocks=3)

@app.route("/teacher/t3/<int:qid>/edit", methods=["GET", "POST"])
@teacher_required
def t3_edit(qid):
    db = get_db()
    q = db.execute("SELECT * FROM t3_questions WHERE id=?", (qid,)).fetchone()
    if not q:
        abort(404)
    parts = db.execute("SELECT * FROM t3_parts WHERE question_id=? ORDER BY ord", (qid,)).fetchall()
    natt = db.execute(
        """SELECT COUNT(*) c FROM t3_attempts a JOIN t3_parts p ON p.id=a.part_id
           WHERE p.question_id=?""", (qid,)).fetchone()["c"]
    if request.method == "POST":
        form, errs = _t3_form()
        if natt and len(form["parts"]) < len(parts):
            errs.append("Students already have attempts here - you can edit or add parts, but not remove any.")
        if not errs:
            db.execute("UPDATE t3_questions SET topic=?,title=?,intro=? WHERE id=?",
                       (form["topic"], form["title"], form["intro"], qid))
            if natt:
                for i, p in enumerate(form["parts"], 1):
                    if i <= len(parts):
                        db.execute("UPDATE t3_parts SET instruction=?,starter=?,tests=?,model=? WHERE id=?",
                                   (p["instruction"], p["starter"], p["tests"], p["model"], parts[i - 1]["id"]))
                    else:
                        db.execute("INSERT INTO t3_parts(question_id,ord,instruction,starter,tests,model) VALUES(?,?,?,?,?,?)",
                                   (qid, i, p["instruction"], p["starter"], p["tests"], p["model"]))
            else:
                db.execute("DELETE FROM t3_parts WHERE question_id=?", (qid,))
                for i, p in enumerate(form["parts"], 1):
                    db.execute("INSERT INTO t3_parts(question_id,ord,instruction,starter,tests,model) VALUES(?,?,?,?,?,?)",
                               (qid, i, p["instruction"], p["starter"], p["tests"], p["model"]))
            db.commit()
            return redirect(url_for("t3_admin", saved=form["title"]))
        return render_template("t3form.html", form=form, errs=errs, qid=qid,
                               nblocks=max(len(form["parts"]) + 1, 3), natt=natt), 400
    form = {"topic": q["topic"], "title": q["title"], "intro": q["intro"],
            "parts": [{"instruction": p["instruction"], "starter": p["starter"] or "",
                       "tests": p["tests"], "model": p["model"]} for p in parts]}
    return render_template("t3form.html", form=form, errs=[], qid=qid,
                           nblocks=max(len(parts) + 1, 3), natt=natt)


# Study-buddy agents preview (teacher-only, fake data; see buddy.py)
import buddy
buddy.init(app, DB_PATH, current_user, grade_theory)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
