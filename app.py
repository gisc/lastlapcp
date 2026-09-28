"""LastLapCP - gamified A-level H2 Computing (9569) revision app.
Flask + SQLite + Jinja. Mobile-first. Google sign-in with an email allowlist.
All secrets/identity data come from env vars, never from the repo."""
import json
import os
import random
import sqlite3
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import (Flask, abort, g, redirect, render_template, request,
                   session, url_for)
from authlib.integrations.flask_client import OAuth

SGT = timezone(timedelta(hours=8))
DB_PATH = os.environ.get("DATABASE_PATH", "/data/lastlapcp.db")
def _norm_email(e):
    e = e.strip().lower()
    local, sep, domain = e.partition("@")
    if sep and domain in ("gmail.com", "googlemail.com"):
        local = local.replace(".", "")
        return local + "@gmail.com"
    return e

TEACHER_EMAILS = {_norm_email(e) for e in os.environ.get("TEACHER_EMAILS", "").split(",") if e.strip()}
ALLOWED_EMAILS = {_norm_email(e) for e in os.environ.get("ALLOWED_EMAILS", "").split(",") if e.strip()} | TEACHER_EMAILS

app = Flask(__name__)
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
  misconception TEXT DEFAULT '');
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
"""

def seed_questions(db):
    if db.execute("SELECT COUNT(*) c FROM questions").fetchone()["c"]:
        return
    seed_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seed_questions.json")
    with open(seed_path, encoding="utf-8") as f:
        bank = json.load(f)
    for q in bank:
        cur = db.execute(
            "INSERT INTO questions(topic,paper,qtype,stem,explanation,misconception) VALUES(?,?,?,?,?,?)",
            (q["topic"], q["paper"], q["qtype"], q["stem"], q["explanation"], q.get("misconception", "")))
        qid = cur.lastrowid
        for i, opt in enumerate(q["options"]):
            db.execute("INSERT INTO options(question_id,ord,text,is_correct) VALUES(?,?,?,?)",
                       (qid, i, opt["text"], 1 if opt["correct"] else 0))
    db.commit()

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.executescript(SCHEMA)
    db.row_factory = sqlite3.Row
    seed_questions(db)
    db.close()

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
    dates = {r["d"] for r in db.execute(
        "SELECT DISTINCT date(created_at, '+8 hours') d FROM attempts WHERE user_id=?", (uid,))}
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
    return {"xp": row["xp"], "attempts": row["n"], "correct": row["c"],
            "streak": streak, "mastery": mastery}

def pick_question(db, uid, topic=None):
    params, where = [], ""
    if topic:
        where, params = "AND q.topic=?", [topic]
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

# ---------------- routes ----------------

@app.route("/")
def home():
    u = current_user()
    if not u:
        return redirect(url_for("login"))
    db = get_db()
    stats = user_stats(db, u["id"])
    topics = [r["topic"] for r in db.execute("SELECT DISTINCT topic FROM questions ORDER BY topic")]
    return render_template("home.html", u=u, stats=stats, topics=topics)

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

@app.route("/login/callback")
def auth_callback():
    token = google.authorize_access_token()
    info = token.get("userinfo") or {}
    email = _norm_email(info.get("email") or "")
    if not email:
        return render_template("denied.html", reason="Google did not return an email address."), 403
    if ALLOWED_EMAILS and email not in ALLOWED_EMAILS:
        return render_template("denied.html",
            reason="This account is not on the LastLapCP class list. Ask your teacher to add it."), 403
    db = get_db()
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
    qid = pick_question(get_db(), session["uid"], topic)
    if qid is None:
        return render_template("quiz.html", empty=True, topic=topic)
    return redirect(url_for("question", qid=qid, topic=topic or ""))

@app.route("/q/<int:qid>")
@login_required
def question(qid):
    topic = request.args.get("topic") or ""
    q, opts = load_question(get_db(), qid)
    if not q:
        abort(404)
    opts = list(opts)
    random.shuffle(opts)
    return render_template("quiz.html", q=q, opts=opts, topic=topic, empty=False, feedback=None)

@app.route("/q/<int:qid>", methods=["POST"])
@login_required
def answer(qid):
    topic = request.form.get("topic", "")
    db = get_db()
    u = current_user()
    q, opts = load_question(db, qid)
    if not q:
        abort(404)
    correct_ids = {o["id"] for o in opts if o["is_correct"]}
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
    return render_template("quiz.html", q=q, opts=opts, topic=topic, empty=False,
                           feedback={"correct": correct, "xp": xp, "chosen": chosen,
                                     "correct_ids": correct_ids}, stats=stats)

@app.route("/teacher")
@teacher_required
def teacher():
    db = get_db()
    students = db.execute("SELECT * FROM users WHERE role='student' ORDER BY name").fetchall()
    topics = [r["topic"] for r in db.execute("SELECT DISTINCT topic FROM questions ORDER BY topic")]
    rows = []
    for s in students:
        st = user_stats(db, s["id"])
        last = db.execute("SELECT MAX(created_at) m FROM attempts WHERE user_id=?", (s["id"],)).fetchone()["m"]
        by_topic = {m["topic"]: m for m in st["mastery"]}
        rows.append({"name": s["name"] or s["email"], "email": s["email"], "stats": st,
                     "by_topic": by_topic,
                     "last": (datetime.fromisoformat(last).astimezone(SGT).strftime("%d %b %H:%M") if last else "-")})
    rows.sort(key=lambda r: -r["stats"]["xp"])
    return render_template("teacher.html", rows=rows, topics=topics)

@app.route("/healthz")
def healthz():
    return {"ok": True}

@app.errorhandler(403)
def forbidden(e):
    return render_template("denied.html", reason="Teachers only."), 403

init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
