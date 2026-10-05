import sys, json
sys.path.insert(0, '/home/sandbox/lastlapcp/analysis')
from papers_data import YEARS, TOPIC_ORDER
from collections import Counter

COLORS = {
 "Algorithms": "#3b82f6", "Data structures": "#22c55e", "Recursion": "#a855f7",
 "OOP": "#f97316", "Number representation": "#eab308", "Databases": "#14b8a6",
 "Networks and web": "#ef4444", "Web applications": "#ec4899", "Ethics": "#8b5cf6",
 "Testing": "#64748b",
}

p1c, p2c = Counter(), Counter()
for _, _, q1, q2 in YEARS:
    for _, ts in q1:
        for t, _ in ts: p1c[t] += 1
    for _, ts in q2:
        for t, _ in ts: p2c[t] += 1

def chip(t, d):
    return f'<div class="chip" style="border-left-color:{COLORS[t]}"><span class="t">{t}</span><span class="d">{d}</span></div>'

def qtable(qs):
    rows = []
    for label, ts in qs:
        rows.append(f'<tr><td class="qn">{label}</td><td>{"".join(chip(t,d) for t,d in ts)}</td></tr>')
    return '<table class="qt"><thead><tr><th class="qn">Q</th><th>Topics</th></tr></thead><tbody>' + "".join(rows) + "</tbody></table>"

year_sections = []
for name, anchor, q1, q2 in YEARS:
    year_sections.append(f'''
<section class="year" id="y{anchor}">
<h2>{name}</h2>
<div class="papers">
<div class="paper"><h3>Paper 1 - Written</h3>{qtable(q1)}</div>
<div class="paper"><h3>Paper 2 - Lab-based</h3>{qtable(q2)}</div>
</div>
</section>''')

freq_rows = []
for t in sorted(TOPIC_ORDER, key=lambda t: -(p1c[t]+p2c[t])):
    freq_rows.append(f'<tr><td><span class="dot" style="background:{COLORS[t]}"></span>{t}</td><td class="n">{p1c[t]} / 6</td><td class="n">{p2c[t]} / 6</td></tr>')

nav = " ".join(f'<a href="#y{a}">{n}</a>' for n, a, _, _ in YEARS)

html = f'''<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>9569 Past Paper Topics (2020-2024 + Specimen)</title>
<style>
:root {{ --bg:#0f2540; --card:#ffffff; --ink:#1e293b; --mut:#64748b; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); font-family:-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif; color:var(--ink); }}
.wrap {{ max-width:1100px; margin:0 auto; padding:24px 16px 60px; }}
header h1 {{ color:#fff; font-size:22px; margin:0 0 6px; }}
header p {{ color:#cbd5e1; font-size:13px; margin:4px 0; line-height:1.5; }}
nav {{ margin:14px 0 4px; }}
nav a {{ color:#93c5fd; text-decoration:none; margin-right:14px; font-size:14px; font-weight:600; }}
nav a:hover {{ text-decoration:underline; }}
.card {{ background:var(--card); border-radius:12px; padding:16px 18px; margin:18px 0; box-shadow:0 2px 8px rgba(0,0,0,.25); }}
h2 {{ font-size:18px; margin:2px 0 10px; }}
h3 {{ font-size:14px; margin:0 0 8px; color:var(--mut); text-transform:uppercase; letter-spacing:.04em; }}
.papers {{ display:grid; grid-template-columns:1fr 1fr; gap:16px; }}
@media (max-width:820px) {{ .papers {{ grid-template-columns:1fr; }} }}
table {{ border-collapse:collapse; width:100%; }}
.qt th {{ text-align:left; font-size:12px; color:var(--mut); border-bottom:2px solid #e2e8f0; padding:4px 6px; }}
.qt td {{ border-bottom:1px solid #eef2f7; padding:7px 6px; vertical-align:top; }}
.qt td.qn {{ font-weight:700; width:34px; }}
.qt th.qn {{ width:34px; }}
.chip {{ border-left:4px solid #999; background:#f8fafc; border-radius:6px; padding:5px 9px; margin:0 0 5px; }}
.chip .t {{ font-weight:700; font-size:13px; display:block; }}
.chip .d {{ font-size:12px; color:var(--mut); }}
.ft {{ width:auto; margin:0 auto; }}
.ft td, .ft th {{ border-bottom:1px solid #eef2f7; padding:7px 16px 7px 6px; font-size:14px; }}
.ft th {{ color:var(--mut); font-size:12px; text-align:left; border-bottom:2px solid #e2e8f0; }}
.ft td.n, .ft th.n {{ text-align:center; font-weight:700; }}
.dot {{ display:inline-block; width:10px; height:10px; border-radius:3px; margin-right:8px; }}
.note {{ font-size:12.5px; color:var(--mut); line-height:1.55; }}
@media print {{ body {{ background:#fff; }} header h1 {{ color:#000; }} header p, nav a {{ color:#333; }} .card {{ box-shadow:none; border:1px solid #ddd; break-inside:avoid; }} }}
</style></head>
<body><div class="wrap">
<header>
<h1>H2 Computing 9569 - Past Paper Topic Map</h1>
<p>Topics examined question by question in the <b>2020-2024 A-Level papers and the specimen paper</b>. Topics are grouped under the current 9569 syllabus ("For Examination from 2020", four sections: Algorithms &amp; Data Structures; Programming; Data &amp; Information; Computer Networks).</p>
<p><b>Syllabus version:</b> all papers below are the outgoing syllabus examined 2020-2026. A revised 9569 syllabus is first examined in <b>2027</b> (adds new content such as artificial intelligence), so use this map for pattern-spotting, not as a guarantee of the 2027+ mix.</p>
<nav>{nav}</nav>
</header>

<section class="card" id="freq">
<h2>Topic frequency across the 6 papers</h2>
<table class="ft"><thead><tr><th>Topic</th><th class="n">Paper 1</th><th class="n">Paper 2</th></tr></thead>
<tbody>{"".join(freq_rows)}</tbody></table>
<p class="note">Counts are questions/tasks in which the topic appears at all (a question can carry several topics). 6 papers each: specimen + 2020-2024.</p>
</section>

{"".join(f'<div class="card">{s}</div>' for s in year_sections)}

<section class="card note">
<b>Notes.</b> Topics only - question text is not reproduced. "Number representation" covers data representation and validation/check digits; "Networks and web" covers protocols, packet switching and security; Paper 2 is lab-based (Python/Jupyter, SQLite, Flask) so its tasks always involve programming constructs in addition to the topics listed. Sources: 2020-2024 GCE A-Level 9569 papers and the 9569 specimen paper (For Examination from 2020).
</section>
</div></body></html>'''

open('/home/sandbox/lastlapcp/analysis/papers.html', 'w').write(html)
print(len(html), "bytes written")
