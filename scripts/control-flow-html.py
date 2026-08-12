"""Render the declared control flow as a two-column vertical timeline.

Left column  - what happens, and the value that step produces.
Right column - the IAM decision that has to pass for it to happen.

Generated from agents/*/agent.yaml, so it cannot drift from the manifests.

    python scripts/control-flow-html.py     ->  infra/control-flow.html
"""
from __future__ import annotations

import html
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "infra" / "control-flow.html"
PHASES = [
    ("provision", "Provision - operator", "Infra team, one-time: roles, runtime, memory, registries"),
    ("release", "Release - developer", "The daily loop: new code against existing infrastructure"),
    ("invoke", "Invoke - runtime", "No human principal; the workload's own identities"),
    ("teardown", "Teardown - operator", "Remove the resources"),
]


def esc(x) -> str:
    return html.escape(str(x if x is not None else ""))


def collect() -> dict:
    agents = {}
    for p in sorted((ROOT / "agents").glob("*/agent.yaml")):
        doc = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        meta, spec = doc.get("metadata", {}), doc.get("spec", {})
        agents[meta["name"]] = {
            "displayName": meta.get("displayName", meta["name"]),
            "framework": (spec.get("source") or {}).get("framework"),
            "model": (spec.get("model") or {}).get("id"),
            "controls": spec.get("controls") or {},
        }
    return agents


def render_step(entry: dict) -> str:
    step = entry.get("step", "")
    num, _, slug = step.partition("-")
    principal = entry.get("principal")
    principals = principal if isinstance(principal, list) else [principal]
    actions = entry.get("actions") or []
    resource = entry.get("resource")
    resources = resource if isinstance(resource, list) else ([resource] if resource else [])
    audit = entry.get("audit", "")

    acts = ("".join(f'<code class="act">{esc(a)}</code>' for a in actions)
            if actions else '<span class="none">no IAM grant required</span>')
    extra = "".join(
        f'<div class="also"><code class="act warn">{esc(x["action"])}</code>'
        f'<div class="why">{esc(x.get("why", ""))}</div></div>'
        for x in entry.get("alsoRequires") or []
    )
    badge = ('<span class="badge ok">audited</span>' if audit == "cloudtrail"
             else '<span class="badge no">no audit record</span>' if audit == "none" else "")
    produces = (f'<div class="produces"><span>yields</span> {esc(entry["produces"])}</div>'
                if entry.get("produces") else "")
    fails = (f'<div class="fails"><span>if denied</span> {esc(entry["failsAs"])}</div>'
             if entry.get("failsAs") else "")
    note = f'<div class="note">{esc(entry["note"])}</div>' if entry.get("note") else ""

    return f"""
    <div class="row">
      <div class="left">
        <div class="card">
          <h4>{esc(slug.replace('-', ' '))}</h4>
          {produces}{note}
        </div>
      </div>
      <div class="spine"><span class="dot">{esc(num)}</span></div>
      <div class="right">
        <div class="card iam">
          <div class="who">{" ".join(f'<code class="pr">{esc(p)}</code>' for p in principals)}{badge}</div>
          <div class="acts">{acts}</div>
          {"".join(f'<div class="res">{esc(r)}</div>' for r in resources)}
          {extra}{fails}
        </div>
      </div>
    </div>"""


def main() -> int:
    agents = collect()
    sections = []
    for name, a in agents.items():
        blocks = []
        for key, title, subtitle in PHASES:
            entries = a["controls"].get(key) or []
            if not entries:
                continue
            steps = "".join(render_step(e) for e in
                            sorted(entries, key=lambda e: int(str(e.get("step", "0")).split("-")[0])))
            blocks.append(f"""
      <section class="phase" data-phase="{key}">
        <div class="phase-head"><h3>{esc(title)}</h3><p>{esc(subtitle)}</p></div>
        {steps}
      </section>""")
        sections.append(f"""
    <div class="agent" id="agent-{esc(name)}" hidden>
      <div class="agent-head">
        <h2>{esc(a['displayName'])}</h2>
        <div class="meta"><code>{esc(a['framework'])}</code><code>{esc(a['model'])}</code></div>
      </div>
      {"".join(blocks)}
    </div>""")

    tabs = "".join(f'<button class="tab" data-agent="{esc(n)}">{esc(n)}</button>'
                   for n in agents)
    counts = {n: sum(len(v or []) for v in a["controls"].values()) for n, a in agents.items()}

    doc = f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Agent-Core - IAM control flow</title>
<style>
:root {{
  --bg:#f7f7f5; --panel:#fff; --ink:#1a1a19; --muted:#6b6b66; --line:#e2e2dd;
  --accent:#2f6f4e; --warn:#a8541b; --danger:#9b2c2c; --code:#f0f0ec;
}}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{
  --bg:#131513; --panel:#1b1e1b; --ink:#e8e8e4; --muted:#9a9a93; --line:#2c302c;
  --accent:#7fc4a0; --warn:#d99a5b; --danger:#e08585; --code:#22261f;
}} }}
:root[data-theme="dark"] {{
  --bg:#131513; --panel:#1b1e1b; --ink:#e8e8e4; --muted:#9a9a93; --line:#2c302c;
  --accent:#7fc4a0; --warn:#d99a5b; --danger:#e08585; --code:#22261f;
}}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--ink);
  font:15px/1.55 ui-sans-serif,-apple-system,"Segoe UI",Roboto,sans-serif; }}
header {{ padding:28px 24px 16px; border-bottom:1px solid var(--line); }}
h1 {{ margin:0 0 6px; font-size:22px; letter-spacing:-.01em; }}
header p {{ margin:0; color:var(--muted); max-width:70ch; }}
.tabs {{ display:flex; gap:6px; flex-wrap:wrap; padding:14px 24px; border-bottom:1px solid var(--line); }}
.tab {{ background:var(--panel); color:var(--ink); border:1px solid var(--line);
  padding:6px 14px; border-radius:999px; cursor:pointer; font:inherit; font-size:13px; }}
.tab[aria-selected="true"] {{ background:var(--accent); border-color:var(--accent); color:var(--bg); font-weight:600; }}
main {{ padding:8px 24px 60px; max-width:1180px; margin:0 auto; }}
.agent-head {{ padding:22px 0 6px; }}
.agent-head h2 {{ margin:0 0 6px; font-size:18px; }}
.meta code {{ font-size:12px; margin-right:6px; }}
.phase-head {{ margin:26px 0 10px; padding-top:16px; border-top:1px solid var(--line); }}
.phase-head h3 {{ margin:0; font-size:15px; text-transform:uppercase; letter-spacing:.07em; color:var(--accent); }}
.phase-head p {{ margin:2px 0 0; color:var(--muted); font-size:13px; }}
.colhead {{ display:grid; grid-template-columns:1fr 54px 1fr; gap:0 14px;
  font-size:11px; text-transform:uppercase; letter-spacing:.09em; color:var(--muted); padding:6px 0; }}
.colhead div:nth-child(3) {{ text-align:left; }}
.row {{ display:grid; grid-template-columns:1fr 54px 1fr; gap:0 14px; align-items:stretch; }}
.spine {{ position:relative; display:flex; justify-content:center; }}
.spine::before {{ content:""; position:absolute; top:0; bottom:0; width:2px; background:var(--line); }}
.dot {{ position:relative; z-index:1; width:26px; height:26px; border-radius:50%;
  background:var(--accent); color:var(--bg); display:grid; place-items:center;
  font-size:12px; font-weight:700; margin-top:14px; }}
.card {{ background:var(--panel); border:1px solid var(--line); border-radius:10px;
  padding:12px 14px; margin:10px 0; }}
.card h4 {{ margin:0; font-size:14px; text-transform:capitalize; }}
.produces, .fails, .note, .why {{ font-size:12.5px; color:var(--muted); margin-top:6px; }}
.produces span, .fails span {{ display:inline-block; font-size:10.5px; text-transform:uppercase;
  letter-spacing:.08em; padding:1px 6px; border-radius:4px; margin-right:6px; }}
.produces span {{ background:var(--code); color:var(--accent); }}
.fails span {{ background:var(--code); color:var(--danger); }}
code {{ background:var(--code); padding:2px 6px; border-radius:5px;
  font:12px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace; }}
.act {{ display:inline-block; margin:3px 4px 0 0; }}
.act.warn {{ color:var(--warn); border:1px dashed var(--warn); }}
.pr {{ color:var(--accent); font-weight:600; }}
.who {{ display:flex; gap:6px; align-items:center; flex-wrap:wrap; }}
.res {{ margin-top:7px; font-size:12px; color:var(--muted); word-break:break-all; }}
.res::before {{ content:"on "; color:var(--muted); }}
.none {{ color:var(--muted); font-size:12.5px; font-style:italic; }}
.badge {{ margin-left:auto; font-size:10.5px; text-transform:uppercase; letter-spacing:.07em;
  padding:2px 7px; border-radius:999px; white-space:nowrap; }}
.badge.ok {{ background:color-mix(in srgb, var(--accent) 18%, transparent); color:var(--accent); }}
.badge.no {{ background:color-mix(in srgb, var(--danger) 16%, transparent); color:var(--danger); }}
.also {{ margin-top:8px; padding-top:8px; border-top:1px dashed var(--line); }}
@media (max-width:760px) {{
  .row, .colhead {{ grid-template-columns:1fr; }}
  .spine {{ display:none; }}
  .card.iam {{ margin-top:0; border-left:3px solid var(--accent); }}
}}
</style></head><body>
<header>
  <h1>IAM control flow</h1>
  <p>Each row is one authorization decision, in the order it is evaluated.
     Left is what happens and the value it yields; right is the IAM check that
     must pass for it to happen. Generated from <code>agents/*/agent.yaml</code>.</p>
</header>
<div class="tabs" role="tablist">{tabs}</div>
<main>
  <div class="colhead"><div>What happens</div><div></div><div>IAM control</div></div>
  {"".join(sections)}
</main>
<script>
const counts = {json.dumps(counts)};
const tabs = [...document.querySelectorAll('.tab')];
function show(name) {{
  document.querySelectorAll('.agent').forEach(a => a.hidden = (a.id !== 'agent-' + name));
  tabs.forEach(t => t.setAttribute('aria-selected', String(t.dataset.agent === name)));
  location.hash = name;
}}
tabs.forEach(t => {{
  t.textContent = t.dataset.agent + ' \\u00b7 ' + counts[t.dataset.agent] + ' steps';
  t.onclick = () => show(t.dataset.agent);
}});
show(location.hash.slice(1) in counts ? location.hash.slice(1) : tabs[0].dataset.agent);
</script>
</body></html>"""

    OUT.write_text(doc, encoding="utf-8")
    total = sum(counts.values())
    print(f"wrote {OUT.relative_to(ROOT)}  ({len(agents)} agents, {total} steps)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
