"""LastLapCP - gamified A-level H2 Computing (9569) revision app.
Flask + SQLite + Jinja. Mobile-first. Google sign-in with an email allowlist.
All secrets/identity data come from env vars, never from the repo."""
import json
import os
import re
import random
import sqlite3
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import (Flask, abort, g, redirect, render_template, request,
                   session, url_for)
from authlib.integrations.flask_client import OAuth
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
CREATE TABLE IF NOT EXISTS roster(
  email TEXT PRIMARY KEY, name TEXT, class TEXT
);
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
    topics = [r["topic"] for r in db.execute("SELECT DISTINCT topic FROM questions ORDER BY topic")]
    users = {u["email"]: u for u in db.execute("SELECT * FROM users WHERE role='student'").fetchall()}

    def row_for(name, email):
        u = users.get(email)
        if not u:
            return {"name": name, "email": email, "signed_in": False}
        st = user_stats(db, u["id"])
        last = db.execute("SELECT MAX(created_at) m FROM attempts WHERE user_id=?", (u["id"],)).fetchone()["m"]
        return {"name": name, "email": email, "signed_in": True, "stats": st,
                "by_topic": {m["topic"]: m for m in st["mastery"]},
                "last": (datetime.fromisoformat(last).astimezone(SGT).strftime("%d %b %H:%M") if last else "-")}

    roster = [{"name": r["name"], "norm": _norm_email(r["email"]), "class": r["class"]}
              for r in db.execute("SELECT name,email,class FROM roster").fetchall()]
    if not roster:
        roster = ROSTER_ENV
    if roster:
        groups = []
        for label, classes in ROSTER_GROUPS:
            members = [r for r in roster if r["class"] in classes]
            rows = [row_for(r["name"], r["norm"]) for r in members]
            rows.sort(key=lambda r: (not r["signed_in"], -(r["stats"]["xp"] if r["signed_in"] else 0)))
            groups.append({"label": label, "rows": rows})
        return render_template("teacher.html", groups=groups, topics=topics, roster=True)

    rows = [row_for(u["name"] or u["email"], u["email"]) for u in users.values()]
    rows = [r for r in rows if r["signed_in"]]
    rows.sort(key=lambda r: -r["stats"]["xp"])
    return render_template("teacher.html", groups=[{"label": "Signed-in students", "rows": rows}],
                           topics=topics, roster=False)

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

init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))


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
        "explanation": request.form.get("explanation", "").strip(),
        "misconception": request.form.get("misconception", "").strip(),
        "opts": opts,
    }
    errs = []
    if not form["topic"]:
        errs.append("Topic is required.")
    if form["qtype"] not in ("mcq", "checkbox"):
        errs.append("Type must be mcq or checkbox.")
    if not form["stem"]:
        errs.append("The question stem is required.")
    if not form["explanation"]:
        errs.append("The Why explanation is required.")
    if len(opts) < 2:
        errs.append("At least two options are required.")
    elif any(not o["text"] for o in opts):
        errs.append("Every option needs text.")
    nc = sum(1 for o in opts if o["correct"])
    if form["qtype"] == "mcq" and nc != 1:
        errs.append("An MCQ needs exactly one correct option ticked.")
    if form["qtype"] == "checkbox" and nc < 2:
        errs.append("A checkbox question needs at least two correct options ticked.")
    return form, errs

def _insert_question(db, form):
    cur = db.execute(
        "INSERT INTO questions(topic,paper,qtype,stem,explanation,misconception) VALUES(?,?,?,?,?,?)",
        (form["topic"], form["paper"], form["qtype"], form["stem"], form["explanation"], form["misconception"]))
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
            "misconception": "", "opts": [{"text": "", "correct": False} for _ in range(4)]}
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
                "UPDATE questions SET topic=?,paper=?,qtype=?,stem=?,explanation=?,misconception=? WHERE id=?",
                (form["topic"], form["paper"], form["qtype"], form["stem"],
                 form["explanation"], form["misconception"], qid))
            for o, row in zip(form["opts"], opts):
                db.execute("UPDATE options SET text=?, is_correct=? WHERE id=?",
                           (o["text"], 1 if o["correct"] else 0, row["id"]))
            db.commit()
            return redirect(url_for("bank_edit", qid=qid, saved=1))
        return render_template("qform.html", form=form, errs=errs, topics=_topics(db),
                               qid=qid, natt=natt, saved=None), 400
    form = {"topic": q["topic"], "paper": q["paper"], "qtype": q["qtype"], "stem": q["stem"],
            "explanation": q["explanation"], "misconception": q["misconception"] or "",
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
