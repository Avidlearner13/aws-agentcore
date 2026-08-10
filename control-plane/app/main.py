"""Control-plane API + UI for the claims-adjudication platform.

- Hosts a small **agent registry** (the local stand-in for the MCP-exposed registry).
- Phase 1: run each specialist individually (`/api/run/{agent}`).
- Phase 2: adjudicate a claim end-to-end via a selectable orchestrator (`/api/adjudicate`).
PDF→text extraction happens here (control-plane), keeping the agents text-in / JSON-out.

Env (all optional, sensible local defaults):
  INTAKE_URL COVERAGE_URL RISK_URL ORCH_CLAUDE_URL   agent /invocations endpoints
  PORT                                               this server's port (default 8770)
"""

from __future__ import annotations

import asyncio
import base64
import hmac
import io
import json
import os
import re
import time
import uuid
from pathlib import Path

from urllib.parse import quote

import boto3
import httpx
from authlib.integrations.starlette_client import OAuth
from botocore.config import Config
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from pypdf import PdfReader
from starlette.middleware.sessions import SessionMiddleware

REGION = os.environ.get("AWS_REGION", "us-east-1")

ROOT = Path(__file__).resolve().parent.parent.parent
SAMPLES_DIR = ROOT / "samples"
CLAIMS_DIR = SAMPLES_DIR / "claims"
STATIC_DIR = Path(__file__).resolve().parent / "static"

# --- Agent registry --------------------------------------------------------------
# Derived from agents/<name>/agent.yaml, which is the single source of truth for what
# an agent is. Each target has a localhost `url` (local dev) and an optional AgentCore
# `arn` (env). When the ARN is set we invoke via the AgentCore data plane
# (InvokeAgentRuntime); otherwise localhost HTTP.
MANIFEST_DIR = ROOT / "agents"


def _load_registry() -> tuple[dict, dict]:
    """Build the specialist + orchestrator registries from agents/*/agent.yaml."""
    import yaml

    agents: dict[str, dict] = {}
    orchestrators: dict[str, dict] = {}
    if not MANIFEST_DIR.is_dir():
        return agents, orchestrators
    for path in sorted(MANIFEST_DIR.glob("*/agent.yaml")):
        try:
            doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:  # noqa: BLE001 - a malformed manifest must not take the console down
            continue
        spec = doc.get("spec") or {}
        console = spec.get("console") or {}
        key = console.get("key")
        if not key:
            continue
        entry = {
            "framework": (spec.get("source") or {}).get("framework"),
            "url": os.environ.get(console.get("urlEnv", ""),
                                  f"http://127.0.0.1:{console.get('localPort')}/invocations"),
            "arn": os.environ.get(console.get("arnEnv", "")),
        }
        label = console.get("label") or (doc.get("metadata") or {}).get("displayName")
        if console.get("group") == "orchestrator":
            orchestrators[key] = {**entry, "label": label}
        else:
            agents[key] = {**entry, "role": label}
    return agents, orchestrators


AGENTS, ORCHESTRATORS = _load_registry()

# Fallback for images built before infra/ was copied in. Keeps an already-deployed
# container working; a rebuilt image reads the manifests above instead.
if not AGENTS:
    AGENTS = {
        "intake": {"framework": "gcp-adk", "role": "Intake & Document Intelligence",
                   "url": os.environ.get("INTAKE_URL", "http://127.0.0.1:8772/invocations"),
                   "arn": os.environ.get("INTAKE_ARN")},
        "coverage": {"framework": "claude-agent-sdk", "role": "Coverage & Adjudication",
                     "url": os.environ.get("COVERAGE_URL", "http://127.0.0.1:8771/invocations"),
                     "arn": os.environ.get("COVERAGE_ARN")},
        "risk": {"framework": "langchain", "role": "Risk, Fraud & Compliance",
                 "url": os.environ.get("RISK_URL", "http://127.0.0.1:8773/invocations"),
                 "arn": os.environ.get("RISK_ARN")},
    }
if not ORCHESTRATORS:
    ORCHESTRATORS = {
        "claude": {"framework": "claude-agent-sdk", "label": "Claude SDK supervisor",
                   "url": os.environ.get("ORCH_CLAUDE_URL", "http://127.0.0.1:8774/invocations"),
                   "arn": os.environ.get("ORCH_CLAUDE_ARN")},
    }

_ac_client = None
_logs_client = None

OBS_DASHBOARD_URL = (f"https://console.aws.amazon.com/cloudwatch/home?region={REGION}"
                     "#gen-ai-observability/agent-core")


def _agentcore():
    global _ac_client
    if _ac_client is None:
        _ac_client = boto3.client(
            "bedrock-agentcore", region_name=REGION,
            config=Config(read_timeout=900, connect_timeout=20, retries={"max_attempts": 1}),
        )
    return _ac_client


def _logs():
    global _logs_client
    if _logs_client is None:
        _logs_client = boto3.client("logs", region_name=REGION)
    return _logs_client


def _runtime_id(arn: str | None) -> str | None:
    """intake-Qh80tlHMU7 from arn:...:runtime/intake-Qh80tlHMU7"""
    return arn.split("/")[-1] if arn else None

# Representative claim_record so Phase-1 Coverage/Risk panels can run standalone.
CANONICAL_CLAIM_RECORD = {
    "claim_id": "CLM-2026-44817", "policy_number": "EHS-HO3-0099821-A",
    "claimant": {"name": "Jordan & Sam Avery", "is_policyholder": True, "contact": "(217) 555-0148"},
    "loss": {"date_of_loss": "2026-03-14", "reported_date": "2026-03-15", "peril_category": "water",
             "cause": "burst supply pipe under kitchen sink",
             "description": "Supply line burst while insured away; ~6-8h water damage to kitchen "
                            "flooring, lower cabinets, area rug. Internal plumbing failure, not flood/backup.",
             "location": "742 Birchwood Lane, Springfield, IL 62704"},
    "line_items": [
        {"description": "Hardwood flooring repair/replacement", "category": "dwelling", "claimed_amount": 8500},
        {"description": "Lower kitchen cabinets", "category": "dwelling", "claimed_amount": 4200},
        {"description": "Water extraction & drying", "category": "mitigation", "claimed_amount": 3100},
        {"description": "Area rug", "category": "contents", "claimed_amount": 900},
    ],
    "total_claimed": 16700, "attachments": [], "extraction_notes": "Prompt reporting; sudden loss.",
}

app = FastAPI(title="Agent-Core Control Plane", version="0.3.0")

# --- Optional Google sign-in gate -------------------------------------------------
# Enabled only when GOOGLE_CLIENT_ID is set (so local dev runs ungated). Restricts
# access to ALLOWED_EMAILS (default the single demo account). The app does the OAuth
# itself (Authlib) so it works behind CloudFront's HTTPS domain without a custom domain.
AUTH_ENABLED = bool(os.environ.get("GOOGLE_CLIENT_ID"))
ALLOWED_EMAILS = {e.strip().lower() for e in
                  os.environ.get("ALLOWED_EMAILS", "anup.iit@gmail.com").split(",") if e.strip()}
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")  # e.g. https://xxxx.cloudfront.net
SESSION_SECRET = os.environ.get("SESSION_SECRET", "dev-insecure-change-me")
_PUBLIC_PATHS = {"/login", "/auth/callback", "/logout", "/healthz"}

# Simpler alternative: HTTP Basic Auth (single shared credential). Active when both env vars are set.
BASIC_AUTH_USER = os.environ.get("BASIC_AUTH_USER")
BASIC_AUTH_PASS = os.environ.get("BASIC_AUTH_PASS")
BASIC_ENABLED = bool(BASIC_AUTH_USER and BASIC_AUTH_PASS)


def _check_basic(request: Request) -> bool:
    hdr = request.headers.get("Authorization", "")
    if not hdr.startswith("Basic "):
        return False
    try:
        user, _, pw = base64.b64decode(hdr[6:]).decode("utf-8", "replace").partition(":")
    except Exception:  # noqa: BLE001
        return False
    return (hmac.compare_digest(user, BASIC_AUTH_USER or "")
            and hmac.compare_digest(pw, BASIC_AUTH_PASS or ""))

oauth = OAuth()
if AUTH_ENABLED:
    oauth.register(
        name="google",
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_id=os.environ["GOOGLE_CLIENT_ID"],
        client_secret=os.environ.get("GOOGLE_CLIENT_SECRET", ""),
        client_kwargs={"scope": "openid email profile"},
    )


@app.middleware("http")
async def _auth_gate(request: Request, call_next):
    if request.url.path in _PUBLIC_PATHS:
        return await call_next(request)
    # Mode 1: HTTP Basic Auth (simplest — single shared credential).
    if BASIC_ENABLED:
        if _check_basic(request):
            return await call_next(request)
        return Response(status_code=401, headers={"WWW-Authenticate": 'Basic realm="Agent-Core Console"'})
    # Mode 2: Google sign-in (email allowlist).
    if AUTH_ENABLED:
        user = (request.session.get("user") or "").lower()
        if user and user in ALLOWED_EMAILS:
            return await call_next(request)
        if request.url.path.startswith("/api/"):
            return JSONResponse({"detail": "authentication required"}, status_code=401)
        return RedirectResponse("/login")
    # Mode 3: no auth configured (local dev).
    return await call_next(request)


# SessionMiddleware added AFTER the gate so it wraps it (session is loaded before the gate runs).
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET, same_site="lax",
                   https_only=AUTH_ENABLED)


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


@app.get("/login")
async def login(request: Request):
    if not AUTH_ENABLED:
        return RedirectResponse("/")
    redirect_uri = (PUBLIC_BASE_URL + "/auth/callback") if PUBLIC_BASE_URL \
        else str(request.url_for("auth_callback"))
    return await oauth.google.authorize_redirect(request, redirect_uri)


@app.get("/auth/callback", name="auth_callback")
async def auth_callback(request: Request):
    token = await oauth.google.authorize_access_token(request)
    info = token.get("userinfo") or {}
    email = (info.get("email") or "").lower()
    if not info.get("email_verified") or email not in ALLOWED_EMAILS:
        return HTMLResponse(
            f"<h3>Access denied for {email or 'this account'}.</h3>"
            "<p>This demo is restricted. <a href='/logout'>Try another account</a>.</p>",
            status_code=403)
    request.session["user"] = email
    return RedirectResponse("/")


@app.get("/logout")
async def logout(request: Request):
    request.session.pop("user", None)
    return RedirectResponse("/login")


def _extract_pdf_text(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    return "\n".join((p.extract_text() or "") for p in reader.pages).strip()


def _policy_text(sample_id: str | None, upload: bytes | None, filename: str | None) -> str:
    if upload:
        return _extract_pdf_text(upload) if (filename or "").lower().endswith(".pdf") \
            else upload.decode("utf-8", errors="replace")
    pid = (sample_id or "policy_a").replace("/", "").replace("\\", "")
    pdf, txt = SAMPLES_DIR / f"{pid}.pdf", SAMPLES_DIR / f"{pid}.txt"
    if pdf.exists():
        return _extract_pdf_text(pdf.read_bytes())
    if txt.exists():
        return txt.read_text(encoding="utf-8")
    raise HTTPException(404, f"Unknown policy sample '{pid}'")


def _fnol_text(upload: bytes | None, filename: str | None) -> str:
    if upload:
        return _extract_pdf_text(upload) if (filename or "").lower().endswith(".pdf") \
            else upload.decode("utf-8", errors="replace")
    # default bundled FNOL bundle (form + estimate)
    parts = []
    for name in ("fnol_form.pdf", "repair_estimate.pdf"):
        p = CLAIMS_DIR / name
        if p.exists():
            parts.append(f"--- {name} ---\n{_extract_pdf_text(p.read_bytes())}")
    if not parts:
        raise HTTPException(404, "No bundled FNOL sample found")
    return "\n\n".join(parts)


async def _invoke(target: dict, payload: dict) -> tuple[dict, int]:
    """Invoke a registry target — via AgentCore (if it has an `arn`) or local HTTP."""
    started = time.perf_counter()
    arn = target.get("arn")
    if arn:
        def _do() -> bytes:
            r = _agentcore().invoke_agent_runtime(
                agentRuntimeArn=arn, qualifier="DEFAULT",
                runtimeSessionId=uuid.uuid4().hex + uuid.uuid4().hex,
                contentType="application/json", accept="application/json",
                payload=json.dumps(payload).encode("utf-8"),
            )
            return r["response"].read()
        result = json.loads(await asyncio.to_thread(_do))
    else:
        async with httpx.AsyncClient(timeout=300) as client:
            resp = await client.post(target["url"], json=payload)
            resp.raise_for_status()
            result = resp.json()
    return result, round((time.perf_counter() - started) * 1000)


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse((STATIC_DIR / "index.html").read_text(encoding="utf-8"))


# --- Governance layer (certification-gated deployment, R-01 + BUILD pipeline) ---------
# Mounted here so the gate reuses the exact same `_invoke` plumbing as the rest of the platform.
try:                       # works both as a package (app.main) and as a script (python main.py)
    from . import governance  # noqa: E402
except ImportError:
    import governance  # type: ignore  # noqa: E402

app.include_router(governance.make_router(
    invoke=_invoke, agents=AGENTS, orchestrators=ORCHESTRATORS,
    claim_record=CANONICAL_CLAIM_RECORD, policy_text_fn=_policy_text,
))


@app.get("/api/registry")
def registry(request: Request) -> dict:
    on_agentcore = any(a.get("arn") for a in AGENTS.values())
    return {"agents": AGENTS, "orchestrators": ORCHESTRATORS, "region": REGION,
            "on_agentcore": on_agentcore,
            "user": (request.session.get("user") if hasattr(request, "session") else None),
            "observability_dashboard": OBS_DASHBOARD_URL if on_agentcore else None}


def _runtime_targets():
    """(name, framework, arn) for all 4 runtimes — 3 specialists + the orchestrator."""
    out = [(k, a.get("framework"), a.get("arn")) for k, a in AGENTS.items()]
    out += [(k, o.get("framework"), o.get("arn")) for k, o in ORCHESTRATORS.items()]
    return out


@app.get("/api/metrics")
def metrics(hours: int = 24) -> dict:
    """Derive insights from each AgentCore runtime's CloudWatch logs: invocation count,
    latency (avg/p95/max), sessions, last-seen — plus overall KPIs."""
    start = int((time.time() - max(1, hours) * 3600) * 1000)
    runtimes, total_inv, all_lat, all_sessions = [], 0, [], set()
    for name, fw, arn in _runtime_targets():
        rid = _runtime_id(arn)
        rec = {"agent": name, "framework": fw, "runtime_id": rid, "invocations": 0,
               "avg_latency_s": None, "p95_latency_s": None, "max_latency_s": None,
               "sessions": 0, "last_seen": None}
        if rid:
            group = f"/aws/bedrock-agentcore/runtimes/{rid}-DEFAULT"
            lats, sess, last = [], set(), 0
            try:
                token = None
                while True:
                    kw = {"logGroupName": group, "startTime": start,
                          "filterPattern": '"Invocation completed"', "limit": 1000}
                    if token:
                        kw["nextToken"] = token
                    r = _logs().filter_log_events(**kw)
                    for e in r.get("events", []):
                        m = e.get("message", "")
                        dm = re.search(r"\(([\d.]+)s\)", m)
                        if dm:
                            lats.append(float(dm.group(1)))
                        sm = re.search(r'"sessionId":\s*"([^"]+)"', m)
                        if sm:
                            sess.add(sm.group(1)); all_sessions.add(sm.group(1))
                        last = max(last, e.get("timestamp", 0))
                    token = r.get("nextToken")
                    if not token or len(lats) > 3000:
                        break
            except Exception:  # noqa: BLE001
                pass
            rec["invocations"] = len(lats); total_inv += len(lats); all_lat += lats
            rec["sessions"] = len(sess)
            if lats:
                s = sorted(lats)
                rec["avg_latency_s"] = round(sum(lats) / len(lats), 2)
                rec["p95_latency_s"] = round(s[min(len(s) - 1, int(len(s) * 0.95))], 2)
                rec["max_latency_s"] = round(max(lats), 2)
            if last:
                rec["last_seen"] = time.strftime("%Y-%m-%d %H:%M:%SZ", time.gmtime(last / 1000))
        runtimes.append(rec)
    overall = {
        "total_invocations": total_inv,
        "total_sessions": len(all_sessions),
        "avg_latency_s": round(sum(all_lat) / len(all_lat), 2) if all_lat else None,
        "busiest": max(runtimes, key=lambda x: x["invocations"])["agent"] if total_inv else None,
        "window_hours": hours,
    }
    return {"runtimes": runtimes, "overall": overall, "region": REGION,
            "dashboard_url": OBS_DASHBOARD_URL}


@app.get("/api/logs/{agent}")
def agent_logs(agent: str, minutes: int = 30) -> dict:
    """Pull recent CloudWatch logs straight from the agent's AgentCore runtime — live proof
    the agent is running on AgentCore, surfaced in the console (the Platform-layer obs view)."""
    target = AGENTS.get(agent) or ORCHESTRATORS.get(agent)
    if not target:
        raise HTTPException(404, f"Unknown agent '{agent}'")
    arn = target.get("arn")
    rid = _runtime_id(arn)
    if not rid:
        return {"agent": agent, "on_agentcore": False,
                "lines": ["(local mode — this agent is not on AgentCore, so there are no "
                          "AgentCore CloudWatch logs)"]}
    group = f"/aws/bedrock-agentcore/runtimes/{rid}-DEFAULT"
    start = int((time.time() - max(1, minutes) * 60) * 1000)
    lines: list[str] = []
    try:
        resp = _logs().filter_log_events(logGroupName=group, startTime=start, limit=100)
        for e in resp.get("events", []):
            ts = time.strftime("%H:%M:%S", time.gmtime(e["timestamp"] / 1000))
            lines.append(f"{ts}  {e['message'].rstrip()}")
    except Exception as e:  # noqa: BLE001 - log group may not exist until first invocation
        lines = [f"(no log events yet, or logs not accessible: {type(e).__name__}: {e})"]
    return {
        "agent": agent, "on_agentcore": True, "runtime_id": rid, "region": REGION,
        "log_group": group, "lines": lines[-80:] or ["(no log events in the selected window)"],
        "console_url": (f"https://console.aws.amazon.com/cloudwatch/home?region={REGION}"
                        f"#logsV2:log-groups/log-group/{quote(group, safe='')}"),
        "dashboard_url": OBS_DASHBOARD_URL,
    }


@app.get("/api/document/{kind}")
def document(kind: str, id: str = "policy_a") -> dict:
    """Expose the raw inputs so the UI can show what each agent actually receives."""
    if kind == "fnol":
        return {"kind": "fnol", "format": "text", "text": _fnol_text(None, None)}
    if kind == "policy":
        return {"kind": "policy", "format": "text", "text": _policy_text(id, None, None)}
    if kind == "claim":
        return {"kind": "claim", "format": "json", "json": CANONICAL_CLAIM_RECORD}
    if kind == "kb":
        files = sorted((SAMPLES_DIR / "kb").glob("*.md"))
        text = "\n\n".join(f"### {p.name}\n{p.read_text(encoding='utf-8')}" for p in files)
        return {"kind": "kb", "format": "text", "text": text or "(no KB files)"}
    raise HTTPException(404, f"Unknown document kind '{kind}'")


@app.get("/api/samples")
def samples() -> dict:
    policies = [{"id": p.stem, "label": p.stem.replace("_", " ").title()}
                for p in sorted(SAMPLES_DIR.glob("*.pdf"))]
    claims = [{"id": p.stem, "label": p.stem.replace("_", " ").title()}
              for p in sorted(CLAIMS_DIR.glob("*.pdf"))]
    return {"policies": policies, "claims": claims}


@app.post("/api/run/{agent}")
async def run_agent(
    agent: str,
    policy_sample: str | None = Form(default="policy_a"),
    policy_file: UploadFile | None = File(default=None),
    fnol_file: UploadFile | None = File(default=None),
) -> JSONResponse:
    """Phase-1: run a single specialist with representative inputs resolved server-side."""
    if agent not in AGENTS:
        raise HTTPException(404, f"Unknown agent '{agent}'")
    pol_bytes = await policy_file.read() if policy_file else None
    policy_text = _policy_text(policy_sample, pol_bytes, policy_file.filename if policy_file else None)

    if agent == "intake":
        fnol_bytes = await fnol_file.read() if fnol_file else None
        payload = {"fnol_text": _fnol_text(fnol_bytes, fnol_file.filename if fnol_file else None),
                   "policy_text": policy_text}
    elif agent == "coverage":
        payload = {"claim_record": CANONICAL_CLAIM_RECORD, "policy_text": policy_text}
    else:  # risk
        payload = {"claim_record": CANONICAL_CLAIM_RECORD}

    result, ms = await _invoke(AGENTS[agent], payload)
    return JSONResponse({"agent": agent, "registry": AGENTS[agent],
                         "input": payload, "result": result, "elapsed_ms": ms})


# Phase-2 adjudication runs ~2-3 min (Coverage + orchestrator), which exceeds the App Runner
# request timeout. So POST starts a background job and returns immediately; the UI polls GET.
ADJ_JOBS: dict = {}


async def _run_adjudication(job_id: str, orch_key: str, target: dict, payload: dict) -> None:
    """Drive Intake → Coverage → Risk here (recording each step live), then ask the orchestrator
    to synthesize the final decision. Surfacing per-step progress requires the control-plane to
    see each specialist finish, so it runs them rather than the orchestrator (which would be a
    single opaque call). The orchestrator still owns the decision via its synthesize-only mode."""
    started = time.perf_counter()

    def _set(**kw):
        ADJ_JOBS[job_id] = {**ADJ_JOBS.get(job_id, {}), **kw}

    def _record(agent: str, env: dict, ms: int) -> dict:
        result = (env or {}).get("result")
        ADJ_JOBS[job_id]["steps"].append(
            {"agent": agent, "framework": AGENTS[agent]["framework"],
             "status": "error" if (env or {}).get("error") else "ok", "duration_ms": ms})
        # Stash each specialist's output so the UI can show the data passing between agents, live.
        ADJ_JOBS[job_id].setdefault("outputs", {})[agent] = result
        return result

    try:
        fnol_text, policy_text = payload["fnol_text"], payload["policy_text"]
        _set(status="running", steps=[], current="intake", outputs={})

        intake_env, ms = await _invoke(AGENTS["intake"], {"fnol_text": fnol_text, "policy_text": policy_text})
        claim_record = _record("intake", intake_env, ms)

        _set(current="coverage")
        cov_env, ms = await _invoke(AGENTS["coverage"], {"claim_record": claim_record, "policy_text": policy_text})
        coverage = _record("coverage", cov_env, ms)

        _set(current="risk")
        risk_env, ms = await _invoke(AGENTS["risk"], {"claim_record": claim_record})
        risk = _record("risk", risk_env, ms)

        _set(current="synthesize")
        result, _ = await _invoke(target, {"claim_record": claim_record, "coverage": coverage,
                                            "risk": risk, "steps": ADJ_JOBS[job_id]["steps"]})
        elapsed = round((time.perf_counter() - started) * 1000)
        _set(status="done", current=None, data={
            "orchestrator": orch_key, "registry": target, "result": result, "elapsed_ms": elapsed})
    except Exception as e:  # noqa: BLE001
        ADJ_JOBS[job_id] = {"status": "error", "error": f"{type(e).__name__}: {e}"}


@app.post("/api/adjudicate")
async def adjudicate(
    orchestrator: str = Form(default="claude"),
    policy_sample: str | None = Form(default="policy_a"),
    policy_file: UploadFile | None = File(default=None),
    fnol_file: UploadFile | None = File(default=None),
) -> JSONResponse:
    """Phase-2: start a full claim adjudication; returns a job_id to poll."""
    if orchestrator not in ORCHESTRATORS:
        raise HTTPException(404, f"Unknown orchestrator '{orchestrator}'")
    pol_bytes = await policy_file.read() if policy_file else None
    fnol_bytes = await fnol_file.read() if fnol_file else None
    payload = {"fnol_text": _fnol_text(fnol_bytes, fnol_file.filename if fnol_file else None),
               "policy_text": _policy_text(policy_sample, pol_bytes,
                                           policy_file.filename if policy_file else None)}
    job_id = uuid.uuid4().hex
    ADJ_JOBS[job_id] = {"status": "running", "steps": [], "current": "intake", "outputs": {}}
    if len(ADJ_JOBS) > 30:  # keep memory bounded
        for k in list(ADJ_JOBS)[:-20]:
            ADJ_JOBS.pop(k, None)
    asyncio.create_task(_run_adjudication(job_id, orchestrator, ORCHESTRATORS[orchestrator], payload))
    return JSONResponse({"job_id": job_id, "status": "running"})


@app.get("/api/adjudicate/{job_id}")
def adjudicate_status(job_id: str) -> JSONResponse:
    job = ADJ_JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "unknown job id")
    return JSONResponse(job)


if __name__ == "__main__":
    import uvicorn

    # 0.0.0.0 so the container is reachable by App Runner's health check / router.
    uvicorn.run(app, host=os.environ.get("HOST", "0.0.0.0"), port=int(os.environ.get("PORT", "8770")))
