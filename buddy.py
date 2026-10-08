"""Study-buddy agents: PREVIEW. Teacher-only, fake data, local model through a private relay.
Gated to BUDDY_PREVIEW_EMAILS (default: the app owner). Everyone else gets a 404.
Tables are all bd_*; nothing here reads or writes student attempts, XP or marks."""
import json
import os
import re
import sqlite3
import threading
import time
import urllib.request
from datetime import datetime, timezone

from flask import Blueprint, abort, jsonify, redirect, render_template_string, request, url_for

bp = Blueprint("buddy", __name__, url_prefix="/buddy")

def _norm_email(e):
    e = (e or "").strip().lower()
    local, sep, domain = e.partition("@")
    if sep and domain in ("gmail.com", "googlemail.com"):
        return local.replace(".", "") + "@gmail.com"
    return e


PREVIEW_EMAILS = {_norm_email(e) for e in os.environ.get(
    "BUDDY_PREVIEW_EMAILS", "soongchee.gi@gmail.com").split(",") if e.strip()}
OLLAMA_URL = os.environ.get("BUDDY_OLLAMA_URL", "http://10.233.98.0:11435")
OLLAMA_MODEL = os.environ.get("BUDDY_MODEL", "qwen3.8:27b")
TOKEN_PATH = os.environ.get("BUDDY_TOKEN_PATH", "/data/.ollama_relay_token")
MAX_QUEUE = 12          # total waiting jobs
PER_AGENT_QUEUED = 1    # one waiting/running job per agent
JOB_TIMEOUT = 150       # seconds per model call
MAX_TAUGHT = 40         # taught points per agent per question
MAX_TEXT = 3000         # characters of student teaching text per submit
FAKE_NAMES = ["Demo Aiden", "Demo Bella", "Demo Chen", "Demo Dewi", "Demo Emil"]

_deps = {}
_workers = {}
_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS bd_agents(
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, fake INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS bd_taught(
  id INTEGER PRIMARY KEY, agent_id INTEGER NOT NULL, qid INTEGER NOT NULL, point TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_bd_taught ON bd_taught(agent_id, qid);
CREATE TABLE IF NOT EXISTS bd_jobs(
  id INTEGER PRIMARY KEY, agent_id INTEGER NOT NULL, qid INTEGER NOT NULL, status TEXT NOT NULL,
  enqueued_at TEXT NOT NULL, started_at TEXT DEFAULT '', finished_at TEXT DEFAULT '',
  answer TEXT DEFAULT '', result TEXT DEFAULT '', error TEXT DEFAULT '', secs REAL DEFAULT 0,
  hidden INTEGER NOT NULL DEFAULT 0, flagged INTEGER NOT NULL DEFAULT 0, flag_note TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS bd_msgs(
  id INTEGER PRIMARY KEY, job_id INTEGER, from_agent INTEGER NOT NULL, to_agent INTEGER NOT NULL,
  text TEXT NOT NULL, created_at TEXT NOT NULL, hidden INTEGER NOT NULL DEFAULT 0, flagged INTEGER NOT NULL DEFAULT 0);
"""

# Agent-to-agent messages are templates filled only with structured values (name, topic, counts).
# No model-written text ever reaches another agent or a student's feed.
TEMPLATES = {
    "high": [
        "{to}, I just got {g} of {t} key points on {topic}. Teaching me really works - try it with yours!",
        "{to}, {topic} went well for me ({g}/{t}). Happy to compare notes any time.",
    ],
    "mid": [
        "{to}, I got {g} of {t} on {topic}. A few points are still missing, so my human is topping me up.",
        "{to}, {topic} was a decent try for me ({g}/{t}). Keep going, every point you teach counts.",
    ],
    "low": [
        "{to}, {topic} was tough for me ({g}/{t}) because I have not been taught much yet. No stress, we both keep learning.",
        "{to}, I only had {g} of {t} on {topic} this round. Next round will be better!",
    ],
}


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _db():
    c = sqlite3.connect(_deps["db_path"], timeout=10)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA busy_timeout=8000")
    return c


def _theory(c, qid):
    r = c.execute("""SELECT q.id, q.title, p.instruction, p.model, p.rubric FROM t3_questions q
                     JOIN t3_parts p ON p.question_id=q.id AND p.ord=1
                     WHERE q.id=? AND q.kind='theory' AND p.rubric<>''""", (qid,)).fetchone()
    if not r:
        return None
    return {"id": r["id"], "topic": r["title"].replace("Theory: ", ""), "instruction": r["instruction"],
            "model": r["model"], "rubric": json.loads(r["rubric"])}


def _topics(c):
    return c.execute("""SELECT q.id, q.title FROM t3_questions q JOIN t3_parts p ON p.question_id=q.id AND p.ord=1
                        WHERE q.kind='theory' AND p.rubric<>'' ORDER BY q.id""").fetchall()


def init(app, db_path, current_user, grade_theory):
    _deps.update(db_path=db_path, current_user=current_user, grade=grade_theory)
    c = sqlite3.connect(db_path)
    c.executescript(SCHEMA)
    c.commit()
    c.close()
    app.register_blueprint(bp)


# ---------------- gate ----------------

@bp.before_request
def _gate():
    u = _deps["current_user"]()
    if not u:
        return redirect(url_for("login"))
    if u["role"] != "teacher" or _norm_email(u["email"]) not in PREVIEW_EMAILS:
        abort(404)
    _ensure_worker()


# ---------------- model + worker ----------------

def _token():
    try:
        return open(TOKEN_PATH).read().strip()
    except OSError:
        return ""


def _ask_model(name, taught, instruction):
    facts = "\n".join("- " + t for t in taught) or "(nothing yet)"
    system = ("You are " + name + ", a study-buddy agent for a student. Your student has taught you ONLY the "
              "facts listed below. Answer the exam question using ONLY those facts, as short bullet points "
              "starting with '- ', one fact per bullet, in your own words. Never add a fact that is not in "
              "the list. If nothing in the list is relevant, reply exactly: - I have not been taught this yet.")
    body = {"model": OLLAMA_MODEL, "stream": False, "think": False,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": "Taught facts:\n" + facts + "\n\nQuestion: " + instruction}],
            "options": {"temperature": 0.2, "num_predict": 300, "num_ctx": 4096}}
    req = urllib.request.Request(OLLAMA_URL + "/api/chat", data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "Authorization": "Bearer " + _token()})
    with urllib.request.urlopen(req, timeout=JOB_TIMEOUT) as r:
        out = json.loads(r.read())
    text = (out.get("message", {}).get("content") or "").strip()
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    return text[:1500]


def _band(g, t):
    f = g / t if t else 0
    return "high" if f >= 0.7 else ("mid" if f >= 0.35 else "low")


def _post_message(c, job_id, agent_id, topic, g, t):
    others = c.execute("SELECT id, name FROM bd_agents WHERE id<>? ORDER BY id", (agent_id,)).fetchall()
    if not others:
        return
    to = others[job_id % len(others)]
    tpl = TEMPLATES[_band(g, t)]
    me = c.execute("SELECT name FROM bd_agents WHERE id=?", (agent_id,)).fetchone()["name"]
    text = tpl[job_id % len(tpl)].format(to=to["name"], g=g, t=t, topic=topic)
    c.execute("INSERT INTO bd_msgs(job_id,from_agent,to_agent,text,created_at) VALUES(?,?,?,?,?)",
              (job_id, agent_id, to["id"], text, _now()))


def _run_one():
    c = _db()
    try:
        c.execute("UPDATE bd_jobs SET status='failed', error='timed out (stale)', finished_at=? "
                  "WHERE status='running' AND started_at<>'' AND (strftime('%s','now')-strftime('%s',started_at))>?",
                  (_now(), JOB_TIMEOUT + 30))
        c.commit()
        cur = c.execute("""UPDATE bd_jobs SET status='running', started_at=? WHERE id=(
                             SELECT id FROM bd_jobs WHERE status='queued' ORDER BY id LIMIT 1)
                           AND NOT EXISTS (SELECT 1 FROM bd_jobs WHERE status='running')""", (_now(),))
        c.commit()
        if cur.rowcount != 1:
            return False
        job = c.execute("SELECT * FROM bd_jobs WHERE status='running' ORDER BY id LIMIT 1").fetchone()
        t0 = time.time()
        try:
            q = _theory(c, job["qid"])
            ag = c.execute("SELECT * FROM bd_agents WHERE id=?", (job["agent_id"],)).fetchone()
            taught = [r["point"] for r in c.execute(
                "SELECT point FROM bd_taught WHERE agent_id=? AND qid=? ORDER BY id", (job["agent_id"], job["qid"]))]
            answer = _ask_model(ag["name"], taught, q["instruction"])
            res = _deps["grade"](answer, q["rubric"])
            flagged = 1 if res["reds"] else 0
            c.execute("UPDATE bd_jobs SET status='done', finished_at=?, answer=?, result=?, secs=?, flagged=?, flag_note=? WHERE id=?",
                      (_now(), answer, json.dumps(res), round(time.time() - t0, 1), flagged,
                       "auto: rubric marked a wrong statement" if flagged else "", job["id"]))
            _post_message(c, job["id"], job["agent_id"], q["topic"], res["greens"], res["total"])
        except Exception as e:  # noqa: BLE001
            c.execute("UPDATE bd_jobs SET status='failed', finished_at=?, error=?, secs=? WHERE id=?",
                      (_now(), str(e)[:300], round(time.time() - t0, 1), job["id"]))
        c.commit()
        return True
    finally:
        c.close()


def _loop():
    while True:
        try:
            if not _run_one():
                time.sleep(1.5)
        except Exception:  # noqa: BLE001
            time.sleep(3)


def _ensure_worker():
    pid = os.getpid()
    with _lock:
        if pid not in _workers:
            t = threading.Thread(target=_loop, daemon=True, name="buddy-worker")
            t.start()
            _workers[pid] = t


# ---------------- views ----------------

CSS = """<style>
.bd{max-width:640px;margin:0 auto;padding:12px}.bd h1{font-size:1.3rem;margin:.2rem 0;color:#fff}
.bd .card{background:#fff;border:1px solid #d6dbe6;border-radius:12px;padding:12px;margin:10px 0}
.bd .warn{background:#fff4d6;border-color:#e6c460}.bd textarea{width:100%;min-height:130px;font:inherit;padding:8px;box-sizing:border-box}
.bd select,.bd button,.bd input{font:inherit;padding:8px 10px;margin:4px 0}.bd button{border-radius:8px;border:0;background:#1a3a6b;color:#fff}
.bd button.sec{background:#e8ecf5;color:#1a3a6b}.bd button.red{background:#b3261e}
.bd .g{color:#1b7a3a}.bd .o{color:#b26a00}.bd .r{color:#b3261e}.bd .x{color:#777}.bd small{color:#555}
.bd .pill{display:inline-block;padding:1px 8px;border-radius:99px;background:#e8ecf5;font-size:.8rem}
.bd .msg{border-left:3px solid #1a3a6b;padding:4px 8px;margin:6px 0}
</style>"""

PAGE = ("{% extends 'base.html' %}{% block title %}Study buddy preview{% endblock %}{% block content %}"
        + CSS + "<div class='bd'>{% block bd %}{% endblock %}</div>{% endblock %}")


def _render(body, **kw):
    tpl = ("{% extends 'base.html' %}{% block title %}Study buddy preview{% endblock %}{% block content %}"
           + CSS + "<div class='bd'><div class='card warn'><b>PREVIEW</b> - teacher-only, fake data only, "
           "local model. Students cannot see this.</div>" + body + "</div>{% endblock %}")
    return render_template_string(tpl, **kw)


def _queue_info(c):
    q = c.execute("SELECT COUNT(*) n FROM bd_jobs WHERE status='queued'").fetchone()["n"]
    run = c.execute("SELECT COUNT(*) n FROM bd_jobs WHERE status='running'").fetchone()["n"]
    avg = c.execute("SELECT AVG(secs) a FROM (SELECT secs FROM bd_jobs WHERE status='done' ORDER BY id DESC LIMIT 8)").fetchone()["a"] or 8
    return {"queued": q, "running": run, "avg": round(avg, 1)}


def _job_view(c, j):
    d = dict(j)
    d["agent"] = c.execute("SELECT name FROM bd_agents WHERE id=?", (j["agent_id"],)).fetchone()["name"]
    d["res"] = json.loads(j["result"]) if j["result"] else None
    if j["status"] == "queued":
        d["pos"] = c.execute("SELECT COUNT(*) n FROM bd_jobs WHERE status IN ('queued','running') AND id<=?", (j["id"],)).fetchone()["n"]
    return d


def _my_agent(c):
    a = c.execute("SELECT * FROM bd_agents WHERE fake=0 ORDER BY id LIMIT 1").fetchone()
    if not a:
        c.execute("INSERT INTO bd_agents(name,fake,created_at) VALUES('My buddy',0,?)", (_now(),))
        c.commit()
        a = c.execute("SELECT * FROM bd_agents WHERE fake=0 ORDER BY id LIMIT 1").fetchone()
    return a


@bp.route("/")
def home():
    c = _db()
    me = _my_agent(c)
    qi = _queue_info(c)
    topics = _topics(c)
    msgs = c.execute("""SELECT m.*, a.name fn FROM bd_msgs m JOIN bd_agents a ON a.id=m.from_agent
                        WHERE m.hidden=0 ORDER BY m.id DESC LIMIT 12""").fetchall()
    jobs = [_job_view(c, j) for j in c.execute("SELECT * FROM bd_jobs WHERE hidden=0 ORDER BY id DESC LIMIT 10")]
    nfake = c.execute("SELECT COUNT(*) n FROM bd_agents WHERE fake=1").fetchone()["n"]
    out = _render("""
<h1>Study buddy agents</h1>
<div class='card'><b>Queue</b> <span class='pill'>{{qi.running}} running</span> <span class='pill'>{{qi.queued}} waiting</span>
 <small>model {{model}}, one request at a time, about {{qi.avg}}s each. Cap {{cap}} waiting.</small></div>
<div class='card'><b>Teach {{me.name}}</b><br><small>Pick a Paper 1 topic, type what you know as bullets. The existing rubric checks each bullet; only confirmed points are stored.</small>
<form method='get' action='{{url_for("buddy.agent_page", aid=me.id, qid=0)}}' onsubmit="this.action=this.action.replace(/\\/0$/, '/'+this.qid.value);"><select name='qid'>
{% for t in topics %}<option value='{{t.id}}'>{{t.title}}</option>{% endfor %}</select> <button>Open</button></form></div>
<div class='card'><b>Demo class ({{nfake}} fake agents)</b><br><small>Fake names, canned taught points from model answers. No student data.</small>
<form method='post' action='{{url_for("buddy.demo_seed")}}'><button class='sec'>{{ 'Re-seed' if nfake else 'Create' }} fake agents</button></form>
{% if nfake %}<form method='post' action='{{url_for("buddy.demo_run")}}'><select name='qid'>{% for t in topics %}<option value='{{t.id}}'>{{t.title}}</option>{% endfor %}</select>
<button>Run all fake agents (queue)</button></form>{% endif %}</div>
<div class='card'><b>Recent attempts</b> <small><a href='{{url_for("buddy.home")}}'>refresh</a></small>
{% for j in jobs %}<div>#{{j.id}} {{j.agent}}: <b>{{j.status}}</b>{% if j.status=='queued' %} (waiting, place {{j.pos}}){% endif %}
{% if j.res %} {{j.res.greens}}/{{j.res.total}} points{% if j.res.reds %}, <span class='r'>{{j.res.reds}} wrong</span>{% endif %}{% endif %}
{% if j.error %}<small class='r'> {{j.error}}</small>{% endif %}</div>{% else %}<small>None yet.</small>{% endfor %}</div>
<div class='card'><b>Buddy room</b> <small>templated messages only</small>
{% for m in msgs %}<div class='msg'><small>{{m.fn}}</small><br>{{m.text}}</div>{% else %}<small>Nothing yet.</small>{% endfor %}</div>
<div class='card'><a href='{{url_for("buddy.teacher")}}'>Teacher view: hide / flag</a></div>
{% if qi.queued or qi.running %}<meta http-equiv='refresh' content='6'>{% endif %}
""", me=me, qi=qi, topics=topics, msgs=msgs, jobs=jobs, nfake=nfake, model=OLLAMA_MODEL, cap=MAX_QUEUE)
    c.close()
    return out


@bp.route("/a/<int:aid>/<int:qid>")
def agent_page(aid, qid):
    c = _db()
    q = _theory(c, qid)
    ag = c.execute("SELECT * FROM bd_agents WHERE id=?", (aid,)).fetchone()
    if not q or not ag:
        abort(404)
    taught = [r["point"] for r in c.execute("SELECT point FROM bd_taught WHERE agent_id=? AND qid=? ORDER BY id", (aid, qid))]
    cov = _deps["grade"]("\n".join(taught), q["rubric"]) if taught else None
    job = c.execute("SELECT * FROM bd_jobs WHERE agent_id=? AND qid=? AND hidden=0 ORDER BY id DESC LIMIT 1", (aid, qid)).fetchone()
    jv = _job_view(c, job) if job else None
    qi = _queue_info(c)
    flash = request.args.get("m", "")
    fb = json.loads(request.args.get("fb", "[]")) if request.args.get("fb") else []
    out = _render("""
<h1>{{ag.name}}: {{q.topic}}</h1>
<div class='card'><b>Question</b><br>{{q.instruction}}</div>
{% if flash %}<div class='card'>{{flash}}</div>{% endif %}
<div class='card'><b>Teach {{ag.name}}</b>
{% if cov %}<br><small>Agent knows {{cov.greens}} of {{cov.total}} rubric points ({{taught|length}} stored bullets).</small>{% else %}<br><small>Nothing taught yet.</small>{% endif %}
<form method='post' action='{{url_for("buddy.teach", aid=ag.id, qid=q.id)}}'><textarea name='text' maxlength='{{maxtext}}' placeholder='- A stack is LIFO...'></textarea>
<button>Teach</button></form>
{% for f in fb %}<div class='{{ {"green":"g","orange":"o","red":"r","grey":"x"}[f.v] }}'>{{ {"green":"Stored","orange":"Partly right, not stored","red":"Wrong, not stored","grey":"Not a tracked point, not stored"}[f.v] }}: {{f.t}}{% if f.f %}<br><small>{{f.f}}</small>{% endif %}</div>{% endfor %}
{% if taught %}<hr><small>Stored points</small><ul>{% for t in taught %}<li>{{t}}</li>{% endfor %}</ul>{% endif %}</div>
<div class='card'><b>Ask {{ag.name}} to attempt it</b><br><small>Uses only what it was taught, marked by the same rubric.</small>
<form method='post' action='{{url_for("buddy.run", aid=ag.id, qid=q.id)}}'><button>Queue attempt</button></form>
{% if jv %}<hr><div><b>Attempt #{{jv.id}}: {{jv.status}}</b>
{% if jv.status=='queued' %}<br>Waiting in queue, place {{jv.pos}} (about {{ (jv.pos * qi.avg)|round|int }}s).{% endif %}
{% if jv.status=='running' %}<br>Thinking now...{% endif %}
{% if jv.error %}<br><span class='r'>{{jv.error}}</span>{% endif %}
{% if jv.res %}<br>Score: <b>{{jv.res.greens}}/{{jv.res.total}}</b> key points{% if jv.res.reds %}, <span class='r'>{{jv.res.reds}} wrong</span>{% endif %} <small>({{jv.secs}}s)</small>
{% for r in jv.res.results %}<div class='{{ {"green":"g","orange":"o","red":"r","grey":"x"}[r.verdict] }}'>{{r.text}}{% if r.feedback %}<br><small>{{r.feedback}}</small>{% endif %}</div>{% endfor %}
{% if jv.res.missed %}<small>Not yet taught: {{jv.res.missed|length}} point(s). Teach more and try again.</small>{% endif %}{% endif %}</div>{% endif %}</div>
<div class='card'><a href='{{url_for("buddy.home")}}'>Back</a></div>
{% if jv and jv.status in ('queued','running') %}<meta http-equiv='refresh' content='5'>{% endif %}
""", ag=ag, q=q, taught=taught, cov=cov, jv=jv, qi=qi, flash=flash, fb=fb, maxtext=MAX_TEXT)
    c.close()
    return out


@bp.route("/teach/<int:aid>/<int:qid>", methods=["POST"])
def teach(aid, qid):
    c = _db()
    q = _theory(c, qid)
    if not q:
        abort(404)
    text = (request.form.get("text") or "")[:MAX_TEXT]
    res = _deps["grade"](text, q["rubric"])
    have = {re.sub(r"\W+", " ", r["point"].lower()).strip() for r in c.execute(
        "SELECT point FROM bd_taught WHERE agent_id=? AND qid=?", (aid, qid))}
    n_have = len(have)
    stored = 0
    for r in res["results"]:
        if r["verdict"] == "green":
            key = re.sub(r"\W+", " ", r["text"].lower()).strip()
            if key not in have and n_have + stored < MAX_TAUGHT:
                c.execute("INSERT INTO bd_taught(agent_id,qid,point,created_at) VALUES(?,?,?,?)",
                          (aid, qid, r["text"][:300], _now()))
                have.add(key)
                stored += 1
    c.commit()
    c.close()
    fb = [{"v": r["verdict"], "t": r["text"][:200], "f": r["feedback"][:200]} for r in res["results"]][:12]
    return redirect(url_for("buddy.agent_page", aid=aid, qid=qid, m="Stored %d new point(s)." % stored, fb=json.dumps(fb)))


@bp.route("/run/<int:aid>/<int:qid>", methods=["POST"])
def run(aid, qid):
    c = _db()
    msg = _enqueue(c, aid, qid)
    c.commit()
    c.close()
    return redirect(url_for("buddy.agent_page", aid=aid, qid=qid, m=msg))


def _enqueue(c, aid, qid):
    if not _theory(c, qid):
        return "Unknown topic."
    if c.execute("SELECT 1 FROM bd_jobs WHERE agent_id=? AND status IN ('queued','running')", (aid,)).fetchone():
        return "This agent already has an attempt waiting."
    if c.execute("SELECT COUNT(*) n FROM bd_jobs WHERE status='queued'").fetchone()["n"] >= MAX_QUEUE:
        return "Queue is full (%d waiting). Try again shortly." % MAX_QUEUE
    c.execute("INSERT INTO bd_jobs(agent_id,qid,status,enqueued_at) VALUES(?,?,'queued',?)", (aid, qid, _now()))
    return "Queued."


@bp.route("/demo/seed", methods=["POST"])
def demo_seed():
    c = _db()
    topics = _topics(c)
    c.execute("DELETE FROM bd_taught WHERE agent_id IN (SELECT id FROM bd_agents WHERE fake=1)")
    c.execute("DELETE FROM bd_msgs WHERE from_agent IN (SELECT id FROM bd_agents WHERE fake=1) OR to_agent IN (SELECT id FROM bd_agents WHERE fake=1)")
    c.execute("DELETE FROM bd_jobs WHERE agent_id IN (SELECT id FROM bd_agents WHERE fake=1)")
    c.execute("DELETE FROM bd_agents WHERE fake=1")
    for i, name in enumerate(FAKE_NAMES):
        cur = c.execute("INSERT INTO bd_agents(name,fake,created_at) VALUES(?,1,?)", (name, _now()))
        aid = cur.lastrowid
        for t in topics:
            q = _theory(c, t["id"])
            lines = [re.sub(r"^\s*[-*]\s*", "", ln).strip() for ln in q["model"].splitlines() if ln.strip()]
            k = [1, 2, 3, 4, 6][i]
            for ln in lines[:k]:
                c.execute("INSERT INTO bd_taught(agent_id,qid,point,created_at) VALUES(?,?,?,?)", (aid, t["id"], ln[:300], _now()))
    c.commit()
    c.close()
    return redirect(url_for("buddy.home"))


@bp.route("/demo/run", methods=["POST"])
def demo_run():
    c = _db()
    qid = int(request.form.get("qid") or 0)
    for a in c.execute("SELECT id FROM bd_agents WHERE fake=1 ORDER BY id").fetchall():
        _enqueue(c, a["id"], qid)
    c.commit()
    c.close()
    return redirect(url_for("buddy.home"))


@bp.route("/teacher")
def teacher():
    c = _db()
    jobs = [_job_view(c, j) for j in c.execute("SELECT * FROM bd_jobs WHERE status IN ('done','failed') ORDER BY id DESC LIMIT 25")]
    msgs = c.execute("""SELECT m.*, a.name fn, b.name tn FROM bd_msgs m JOIN bd_agents a ON a.id=m.from_agent
                        JOIN bd_agents b ON b.id=m.to_agent ORDER BY m.id DESC LIMIT 25""").fetchall()
    out = _render("""
<h1>Teacher view</h1><div class='card'><small>Hidden items disappear from the student-facing feed. Flags are for your review; wrong statements found by the rubric are flagged automatically.</small></div>
<div class='card'><b>Attempts</b>
{% for j in jobs %}<div style='margin:8px 0;opacity:{{ 0.45 if j.hidden else 1 }}'>#{{j.id}} {{j.agent}} <span class='pill'>{{j.status}}</span>
{% if j.flagged %}<span class='pill r'>flagged</span>{% endif %}{% if j.hidden %}<span class='pill'>hidden</span>{% endif %}
{% if j.res %} {{j.res.greens}}/{{j.res.total}}{% endif %}<br><small>{{j.answer[:300]}}{{j.error}}{% if j.flag_note %} | {{j.flag_note}}{% endif %}</small>
<form method='post' action='{{url_for("buddy.moderate", kind="job", oid=j.id)}}'><button name='act' value='hide' class='sec'>{{ 'Unhide' if j.hidden else 'Hide' }}</button>
<button name='act' value='flag' class='sec'>{{ 'Unflag' if j.flagged else 'Flag' }}</button></form></div>{% else %}<small>None yet.</small>{% endfor %}</div>
<div class='card'><b>Agent messages</b>
{% for m in msgs %}<div class='msg' style='opacity:{{ 0.45 if m.hidden else 1 }}'><small>{{m.fn}} to {{m.tn}}{% if m.flagged %} (flagged){% endif %}{% if m.hidden %} (hidden){% endif %}</small><br>{{m.text}}
<form method='post' action='{{url_for("buddy.moderate", kind="msg", oid=m.id)}}'><button name='act' value='hide' class='sec'>{{ 'Unhide' if m.hidden else 'Hide' }}</button>
<button name='act' value='flag' class='sec'>{{ 'Unflag' if m.flagged else 'Flag' }}</button></form></div>{% else %}<small>None yet.</small>{% endfor %}</div>
<div class='card'><a href='{{url_for("buddy.home")}}'>Back</a></div>""", jobs=jobs, msgs=msgs)
    c.close()
    return out


@bp.route("/moderate/<kind>/<int:oid>", methods=["POST"])
def moderate(kind, oid):
    tbl = {"job": "bd_jobs", "msg": "bd_msgs"}.get(kind)
    if not tbl:
        abort(404)
    col = "hidden" if request.form.get("act") == "hide" else "flagged"
    c = _db()
    c.execute("UPDATE %s SET %s = 1 - %s WHERE id=?" % (tbl, col, col), (oid,))
    c.commit()
    c.close()
    return redirect(url_for("buddy.teacher"))


@bp.route("/api/status")
def status():
    c = _db()
    out = _queue_info(c)
    c.close()
    return jsonify(out)
