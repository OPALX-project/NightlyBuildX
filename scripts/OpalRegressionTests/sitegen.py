import html
import json
import os
import pathlib
import datetime


ASSETS_DIRNAME = "assets"


def _write_text(path: str, content: str) -> None:
    pathlib.Path(os.path.dirname(path)).mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def write_report_assets(report_root: str) -> None:
    assets_dir = os.path.join(report_root, ASSETS_DIRNAME)
    pathlib.Path(assets_dir).mkdir(parents=True, exist_ok=True)

    css = """
:root{
  --bg:#0b0f17; --panel:#0f172a; --panel2:#0b1220; --text:#e5e7eb; --muted:#94a3b8;
  --ok:#22c55e; --bad:#f59e0b; --broken:#ef4444; --border:#1f2a44; --link:#60a5fa;
  --shadow: 0 8px 30px rgba(0,0,0,.35);
  --mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono","Courier New", monospace;
  --sans: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, "Apple Color Emoji","Segoe UI Emoji";
}
@media (prefers-color-scheme: light){
  :root{ --bg:#f7fafc; --panel:#ffffff; --panel2:#f1f5f9; --text:#0f172a; --muted:#475569;
    --ok:#16a34a; --bad:#d97706; --broken:#dc2626; --border:#e2e8f0; --link:#2563eb;
    --shadow: 0 8px 30px rgba(15,23,42,.12);
  }
}
*{ box-sizing:border-box; }
html,body{ height:100%; }
body{
  margin:0; padding:0;
  font-family: var(--sans);
  background: radial-gradient(1200px 800px at 20% -10%, rgba(96,165,250,.25), transparent 55%),
              radial-gradient(1000px 700px at 90% 0%, rgba(34,197,94,.18), transparent 55%),
              var(--bg);
  color: var(--text);
}
a{ color: var(--link); text-decoration:none; }
a:hover{ text-decoration:underline; }
.wrap{ max-width: 1200px; margin: 0 auto; padding: 28px 18px 60px; }
.topbar{
  display:flex; align-items:flex-end; justify-content:space-between; gap:14px;
  margin-bottom:18px;
}
.title{
  font-size: 22px; font-weight: 700; letter-spacing:.2px;
}
.subtitle{ color: var(--muted); margin-top:6px; font-size: 13px; }
.card{
  background: linear-gradient(180deg, rgba(255,255,255,.06), rgba(255,255,255,0)) , var(--panel);
  border: 1px solid var(--border);
  border-radius: 14px;
  box-shadow: var(--shadow);
}
.grid{
  display:grid;
  grid-template-columns: 1.2fr .8fr;
  gap: 14px;
  margin-top: 14px;
}
@media (max-width: 900px){ .grid{ grid-template-columns:1fr; } }
.p{ padding: 16px; }
.kpis{
  display:grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
}
@media (max-width: 560px){ .kpis{ grid-template-columns: repeat(2, 1fr); } }
.kpi{ padding: 12px 12px 10px; background: var(--panel2); border:1px solid var(--border); border-radius: 12px; }
.kpi .label{ color: var(--muted); font-size: 12px; }
.kpi .value{ font-family: var(--mono); font-size: 18px; margin-top: 6px; }
.pill{
  display:inline-flex; align-items:center; gap:8px;
  padding: 5px 10px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: rgba(255,255,255,.04);
  font-size: 12px;
  color: var(--muted);
}
.dot{ width:10px; height:10px; border-radius:999px; }
.dot.ok{ background: var(--ok); }
.dot.bad{ background: var(--bad); }
.dot.broken{ background: var(--broken); }
.toolbar{
  display:flex; gap:10px; align-items:center; flex-wrap:wrap;
  margin-top: 12px;
}
input[type="search"]{
  width: 100%;
  max-width: 460px;
  padding: 10px 12px;
  border-radius: 12px;
  border: 1px solid var(--border);
  background: var(--panel2);
  color: var(--text);
  outline: none;
}
.tests{ margin-top: 12px; }
details{
  border-top: 1px solid var(--border);
}
summary{
  list-style:none;
  cursor:pointer;
  padding: 12px 16px;
  display:flex; align-items:center; justify-content:space-between; gap:12px;
}
summary::-webkit-details-marker{ display:none; }
.simname{ font-family: var(--mono); font-size: 13px; }
.desc{ color: var(--muted); font-size: 12px; margin-top: 4px; }
.summary-left{ display:flex; flex-direction:column; gap:2px; }
.summary-right{ display:flex; align-items:center; gap:10px; flex-wrap:wrap; justify-content:flex-end; }
.badge{
  font-family: var(--mono);
  font-size: 12px;
  padding: 3px 9px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: rgba(255,255,255,.04);
}
.badge.ok{ border-color: color-mix(in srgb, var(--ok), var(--border) 65%); }
.badge.bad{ border-color: color-mix(in srgb, var(--bad), var(--border) 65%); }
.badge.broken{ border-color: color-mix(in srgb, var(--broken), var(--border) 65%); }
.inner{ padding: 0 16px 14px; }
table{
  width:100%;
  border-collapse: collapse;
  font-size: 13px;
  overflow:hidden;
  border: 1px solid var(--border);
  border-radius: 12px;
}
th,td{ padding: 8px 10px; border-bottom: 1px solid var(--border); vertical-align:top; }
th{ text-align:left; color: var(--muted); font-weight:600; background: var(--panel2); }
tr:last-child td{ border-bottom:none; }
.state{
  font-family: var(--mono);
  font-size: 12px;
}
.state.passed{ color: var(--ok); }
.state.failed{ color: var(--bad); }
.state.broken{ color: var(--broken); }
.plots{
  display:grid;
  grid-template-columns: repeat(2, minmax(0,1fr));
  gap: 10px;
  margin-top: 12px;
}
@media (max-width: 900px){ .plots{ grid-template-columns:1fr; } }
.plotcard{ border: 1px solid var(--border); border-radius: 12px; overflow:hidden; background: var(--panel2); }
.plotcard img{ width:100%; display:block; }
.plotcap{ padding: 8px 10px; font-size: 12px; color: var(--muted); font-family: var(--mono); }
.footer{ margin-top: 22px; color: var(--muted); font-size: 12px; }
"""
    _write_text(os.path.join(assets_dir, "style.css"), css.strip() + "\n")

    js = """
function setupFilter(){
  const q = document.getElementById('q');
  if(!q) return;
  const items = Array.from(document.querySelectorAll('[data-sim]'));
  const norm = s => (s||'').toLowerCase();
  const apply = () => {
    const needle = norm(q.value);
    for(const el of items){
      const hay = norm(el.getAttribute('data-sim')) + ' ' + norm(el.getAttribute('data-desc'));
      el.style.display = hay.includes(needle) ? '' : 'none';
    }
  };
  q.addEventListener('input', apply);
  apply();
}
document.addEventListener('DOMContentLoaded', setupFilter);
"""
    _write_text(os.path.join(assets_dir, "app.js"), js.strip() + "\n")


def _count_states(sim):
    counts = {"passed": 0, "failed": 0, "broken": 0}
    for t in sim.get("tests", []):
        s = t.get("state")
        if s in counts:
            counts[s] += 1
    return counts


def _escape(s):
    return html.escape(s if s is not None else "")


def write_run_report(report_root: str, run_dir: str, results: dict) -> None:
    rel_assets = os.path.relpath(os.path.join(report_root, ASSETS_DIRNAME), run_dir)
    title = "OPALX regression tests"

    started = results.get("started_at") or ""
    timestamp = results.get("timestamp") or ""
    rev_code = (results.get("revisions") or {}).get("code_full", "")
    rev_tests = (results.get("revisions") or {}).get("tests_full", "")
    summary = results.get("summary") or {}

    sims_html = []
    for sim in results.get("simulations", []):
        simname = sim.get("name", "")
        desc = sim.get("description", "")
        counts = _count_states(sim)
        badge = "ok" if (counts["failed"] == 0 and counts["broken"] == 0) else ("broken" if counts["broken"] else "bad")

        rows = []
        plot_cards = []
        for t in sim.get("tests", []):
            var = t.get("var", "")
            mode = t.get("mode", "")
            eps = t.get("eps", "")
            delta = t.get("delta", "")
            state = t.get("state", "")
            plot = t.get("plot")
            rows.append(
                "<tr>"
                f"<td class='simname'>{_escape(var)}</td>"
                f"<td class='simname'>{_escape(mode)}</td>"
                f"<td class='simname'>{_escape(eps)}</td>"
                f"<td class='simname'>{_escape(delta)}</td>"
                f"<td class='state {state}'>{_escape(state)}</td>"
                "</tr>"
            )
            if plot:
                plot_rel = _escape(plot)
                plot_cards.append(
                    "<div class='plotcard'>"
                    f"<a href='{plot_rel}'><img loading='lazy' src='{plot_rel}' alt='plot'></a>"
                    f"<div class='plotcap'>{_escape(simname)} · {_escape(var)}</div>"
                    "</div>"
                )

        log_link = ""
        if sim.get("log_relpath"):
            log_link = f"<span class='pill'><span class='dot ok'></span><a href='{_escape(sim.get('log_relpath'))}'>log</a></span>"

        sims_html.append(
            f"<details class='sim card' data-sim='{_escape(simname)}' data-desc='{_escape(desc)}'>"
            "<summary>"
            "<div class='summary-left'>"
            f"<div class='simname'>{_escape(simname)}</div>"
            f"<div class='desc'>{_escape(desc)}</div>"
            "</div>"
            "<div class='summary-right'>"
            f"<span class='badge {badge}'>passed:{counts['passed']} failed:{counts['failed']} broken:{counts['broken']}</span>"
            f"{log_link}"
            "</div>"
            "</summary>"
            "<div class='inner'>"
            "<table>"
            "<thead><tr><th>Variable</th><th>Mode</th><th>Eps</th><th>Delta</th><th>State</th></tr></thead>"
            "<tbody>"
            + "".join(rows) +
            "</tbody></table>"
            + (("<div class='plots'>" + "".join(plot_cards) + "</div>") if plot_cards else "") +
            "</div>"
            "</details>"
        )

    html_doc = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_escape(title)} · { _escape(timestamp) }</title>
  <link rel="stylesheet" href="{_escape(os.path.join(rel_assets, 'style.css'))}">
  <script defer src="{_escape(os.path.join(rel_assets, 'app.js'))}"></script>
</head>
<body>
  <div class="wrap">
    <div class="topbar">
      <div>
        <div class="title">{_escape(title)}</div>
        <div class="subtitle">Run <span class="simname">{_escape(timestamp)}</span> · started <span class="simname">{_escape(started)}</span></div>
        <div class="subtitle">code <span class="simname">{_escape(rev_code[:12])}</span> · tests <span class="simname">{_escape(rev_tests[:12])}</span></div>
      </div>
      <div class="pill"><span class="dot ok"></span><a href="../index.html">overview</a></div>
    </div>

    <div class="grid">
      <div class="card p">
        <div class="kpis">
          <div class="kpi"><div class="label">total</div><div class="value">{summary.get('total','-')}</div></div>
          <div class="kpi"><div class="label">passed</div><div class="value">{summary.get('passed','-')}</div></div>
          <div class="kpi"><div class="label">failed</div><div class="value">{summary.get('failed','-')}</div></div>
          <div class="kpi"><div class="label">broken</div><div class="value">{summary.get('broken','-')}</div></div>
        </div>
        <div class="toolbar">
          <input id="q" type="search" placeholder="Filter simulations (name/description)…" autocomplete="off">
          <span class="pill"><span class="dot ok"></span>passed</span>
          <span class="pill"><span class="dot bad"></span>failed</span>
          <span class="pill"><span class="dot broken"></span>broken</span>
        </div>
      </div>
      <div class="card p">
        <div class="subtitle">Artifacts</div>
        <div style="margin-top:10px; display:flex; flex-direction:column; gap:8px;">
          <span class="pill"><span class="dot ok"></span><a href="results.json">results.json</a></span>
          <span class="pill"><span class="dot ok"></span><a href="plots/">plots/</a></span>
          <span class="pill"><span class="dot ok"></span><a href="logs/">logs/</a></span>
        </div>
        <div class="footer" style="margin-top:14px;">
          Generated {html.escape(datetime.datetime.now().isoformat(timespec='seconds'))}
        </div>
      </div>
    </div>

    <div class="tests card" style="margin-top:14px;">
      {''.join(sims_html) if sims_html else '<div class="p">No simulations executed.</div>'}
    </div>
  </div>
</body>
</html>
"""
    _write_text(os.path.join(run_dir, "index.html"), html_doc)


def update_overview(report_root: str) -> None:
    runs_dir = os.path.join(report_root, "runs")
    pathlib.Path(runs_dir).mkdir(parents=True, exist_ok=True)
    run_names = []
    for entry in sorted(os.listdir(runs_dir), reverse=True):
        p = os.path.join(runs_dir, entry)
        if os.path.isdir(p) and os.path.isfile(os.path.join(p, "results.json")):
            run_names.append(entry)

    # Build overview cards by reading summary only
    cards = []
    for run in run_names[:200]:
        rpath = os.path.join(runs_dir, run, "results.json")
        try:
            with open(rpath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue
        s = (data.get("summary") or {})
        badge = "ok" if (s.get("failed", 0) == 0 and s.get("broken", 0) == 0) else ("broken" if s.get("broken", 0) else "bad")
        cards.append(
            "<div class='card p' style='display:flex; align-items:center; justify-content:space-between; gap:12px;'>"
            f"<div><div class='simname'>{_escape(run)}</div><div class='subtitle'>total {s.get('total','-')} · passed {s.get('passed','-')} · failed {s.get('failed','-')} · broken {s.get('broken','-')}</div></div>"
            f"<div style='display:flex; gap:10px; align-items:center;'><span class='badge {badge}'>status</span>"
            f"<span class='pill'><span class='dot ok'></span><a href='runs/{_escape(run)}/index.html'>open</a></span></div>"
            "</div>"
        )

    index = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>OPALX regression report</title>
  <link rel="stylesheet" href="{ASSETS_DIRNAME}/style.css">
  <script defer src="{ASSETS_DIRNAME}/app.js"></script>
</head>
<body>
  <div class="wrap">
    <div class="topbar">
      <div>
        <div class="title">OPALX regression report</div>
        <div class="subtitle">Report root: <span class="simname">{_escape(report_root)}</span></div>
      </div>
      <div class="pill"><span class="dot ok"></span><a href="runs/">runs/</a></div>
    </div>
    <div class="card p">
      <div class="subtitle">Most recent runs</div>
      <div style="margin-top:12px; display:grid; grid-template-columns: 1fr; gap: 10px;">
        {''.join(cards) if cards else '<div class="subtitle">No runs yet. Execute `run_tests --build <...>` to generate one.</div>'}
      </div>
      <div class="footer">Updated {html.escape(datetime.datetime.now().isoformat(timespec='seconds'))}</div>
    </div>
  </div>
</body>
</html>
"""
    _write_text(os.path.join(report_root, "index.html"), index)

