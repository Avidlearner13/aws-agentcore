# Build Log

Step-by-step record of what was built/changed, newest entries appended at the bottom.
Format: `## [date] — title` · what · why · result/verification · next.

See `PLAN.md` for architecture/decisions, `PRD.md` for the original brief, and **`STATUS.md`**
for the color-coded mermaid status map (built / in-progress / planned) — keep it in sync with the
entries here.

---

## 2026-06-22 — Project planning & environment setup

### Planning
- **What:** Captured requirements via Q&A and wrote `PLAN.md` (architecture, use cases, agent
  lifecycle, per-agent runtime view, policy repository, MCP-exposed agent registry, roadmap,
  decisions log).
- **Why:** Greenfield repo with only a one-paragraph `PRD.md`; needed a shared reference before building.
- **Result:** `PLAN.md` complete and reviewed through several decision rounds (see its §14 decisions log).

### Key decisions (mirror of PLAN.md §14)
- Backbone = **AWS Bedrock AgentCore** + custom **Angular** console; purpose = **POC**.
- Domain = **insurance**; Phase 1 = policy-document comparison (3 frameworks, same task);
  Phase 2 = claims-triage orchestrator→workers (Claude Agent SDK).
- Agent **registry exposed via MCP Gateway** ("agents as tools") → registry-driven orchestration + A2A.
- Platform runs **100% on AWS**; laptop is **editor only** (no dev box); builds via **CodeBuild**.
- Hosting: control-plane API + Angular UI on **ECS Fargate**; agents on **AgentCore Runtime**.
- Baseline **CPython 3.12** for deployed containers; **no-GIL rejected** as baseline.
- Region = **us-east-1**.

### Environment
- **What:** Verified toolchain and built per-component Python venvs.
- **Detail:**
  - Python available: 3.14.0 (default) and 3.10 installed. Chose **3.10 locally** (3.14 too new for
    framework wheels). Node v25.2.1 present. AWS CLI v2 **2.35.10** installed (by user), verified on PATH.
  - Created 4 isolated venvs (per-component, to avoid cross-framework dep conflicts) and installed:
    - `control-plane/.venv` — boto3, **bedrock-agentcore 1.15.0**, bedrock-agentcore-starter-toolkit 0.3.9, fastapi 0.138, uvicorn, pydantic 2.13, pyyaml. ✅
    - `agents/claude-sdk/.venv` — **claude-agent-sdk 0.2.107**, anthropic 0.111 [bedrock], mcp 1.28, bedrock-agentcore. ✅
    - `agents/langchain/.venv` — **langchain 1.3.11**, **langgraph 1.2.6**, langchain-aws 1.6, langchain-community 0.4.2, bedrock-agentcore. ✅
    - `agents/gcp-adk/.venv` — **google-adk 2.3.0**, google-genai 2.9, bedrock-agentcore. ✅
- **Why:** Validate that all three frameworks + the AgentCore SDK install cleanly before building.
- **Result:** All four installs exited 0 on Python 3.10. Wheels cached for fast rebuild on 3.12.
- **Files created:** `control-plane/requirements.txt`, `agents/{claude-sdk,gcp-adk,langchain}/requirements.txt`, `.gitignore`, `PLAN.md`, `PRD.md` (pre-existing), `BUILDLOG.md`.

### Open / next
- [ ] AWS creds via `aws configure --profile agentcore` (user) → then verify Bedrock + deploy.
- [x] Start Track B scaffolding: Claude SDK policy-comparison agent + AgentCore entrypoint + Dockerfile.

---

## 2026-06-22 — Claude SDK agent slice (Phase 1: policy comparison)

- **What:** Built the first vertical slice — the Claude Agent SDK policy-comparison agent,
  packaged for AgentCore Runtime.
- **How (verified against installed SDKs):** introspected `claude_agent_sdk` and
  `bedrock_agentcore` to use real APIs — `query(*, prompt, options)` async stream,
  `ClaudeAgentOptions(system_prompt, model, max_turns, allowed_tools, setting_sources, agents=...)`,
  and `BedrockAgentCoreApp().entrypoint`. Confirmed `AgentDefinition` exists for Phase-2 subagents.
- **Files created:**
  - `agents/claude-sdk/policy_comparison.py` — core logic; returns normalized envelope
    `{framework, model, diff, raw, meta}` (shared shape across all 3 framework agents).
  - `agents/claude-sdk/app.py` — AgentCore entrypoint (`@app.entrypoint async def invoke`).
  - `agents/claude-sdk/Dockerfile` — linux/arm64 (AgentCore requirement), Python 3.12,
    `CLAUDE_CODE_USE_BEDROCK=1`.
  - `agents/claude-sdk/samples/policy_a.txt`, `policy_b.txt` — local test fixtures.
  - `agents/claude-sdk/README.md` — run/deploy notes.
- **Why:** Highest-leverage first build — also the Phase-2 orchestrator framework. No AWS creds
  needed to author; deploy-ready once creds land.
- **Verification:** Code written against introspected signatures; **not yet executed** (needs
  Bedrock creds). To verify: run `app.py` locally with `AWS_PROFILE=agentcore` and POST the samples.
- **Decisions/assumptions to confirm:**
  - AgentCore Runtime container arch = **linux/arm64** (pinned in Dockerfile).
  - Default model = `us.anthropic.claude-sonnet-4-5-...` Bedrock inference profile (override via env/payload).
  - Open: whether `claude_agent_sdk`'s bundled CLI needs Node.js in the arm64 image (noted in Dockerfile).
- **Cleanup:** removed `_introspect.py` scratch file.

### Open / next
- [x] AWS creds → verify Bedrock model access + run the agent locally end-to-end.
- [ ] Control-plane FastAPI skeleton + agent-registry data model (PLAN.md §4).
- [ ] `infra/` CDK stack (ECR, Fargate, AgentCore resources).
- [ ] Replicate the policy-comparison task in `agents/gcp-adk` and `agents/langchain`.

---

## 2026-06-22 — AWS access + Claude agent verified end-to-end

- **What:** Wired up AWS, enabled the model, and proved the Claude SDK agent runs against Bedrock.
- **AWS setup:**
  - Created IAM user `agentcore-dev` (AdministratorAccess for POC) + access key; configured CLI
    profile `agentcore` (us-east-1). Identity: account **<ACCOUNT_ID>**, `user/agentcore-dev`.
  - Verified `sts get-caller-identity` ✅ (after fixing a mistyped secret → `SignatureDoesNotMatch`).
- **Bedrock model access:**
  - Listed Anthropic models + Claude inference profiles in us-east-1.
  - **Sonnet 4.6 was gated:** `get-foundation-model-availability` → `agreementAvailability:
    NOT_AVAILABLE`; converse → `ResourceNotFoundException: use case details not submitted`.
  - Determined via CLI probing that the **Anthropic use-case form** is the gate (undocumented blob
    for `put-use-case-for-model-access`); recommended the **console** for that one legal step
    (no root needed — admin user suffices). **User submitted the form + accepted the agreement.**
  - Re-verified: direct converse to `us.anthropic.claude-sonnet-4-6` → "OK" ✅.
- **Agent verification (the "confidence in individual agents" milestone, Claude):**
  - Debugged two red herrings: `max_turns=1` caused an error result; then a 404 that turned out to
    be the model-access gate (not the prompt). Captured CLI stderr to find the real cause each time.
  - Confirmed the bundled Claude Code CLI runs on Windows (no Node needed locally).
  - **Full `compare_policies` run on Sonnet 4.6:** `is_error=False`, 1 turn, ~$0.095,
    `DIFF PARSED OK=True` — produced a faithful structured diff of the two sample policies.
- **Code change:** `agents/claude-sdk/policy_comparison.py` default model → `us.anthropic.claude-sonnet-4-6`
  (env `CLAUDE_MODEL` still overrides).
- **Notes/learnings:**
  - The Claude Code CLI adds ~17–18k cached input tokens of harness context per call (its system
    prompt) → ~$0.06–0.10/call even for small tasks. Acceptable for POC; note for cost dashboards.
  - `us.` inference profiles route cross-region; model access must hold across the profile's regions.
- **Verification status:** Claude agent core logic = ✅ verified against live Bedrock. Not yet
  deployed to AgentCore Runtime (next: local `app.py` server test, then deploy).

### Open / next
- [x] Smoke-test `app.py` AgentCore server locally (POST to /invocations).
- [x] Replicate the policy-comparison task in `agents/gcp-adk` and `agents/langchain`.
- [ ] Control-plane agent-registry data model (PLAN.md §4) — viewer slice built; registry next.
- [ ] `infra/` CDK stack (ECR, Fargate, AgentCore resources).

---

## 2026-06-22 — All 3 agents verified + PDF support + web UI

- **All three individual agents now work end-to-end on Bedrock Sonnet 4.6** (the "confidence in
  individual agents" milestone):
  - **Claude SDK** (`agents/claude-sdk`) — verified earlier.
  - **GCP ADK** (`agents/gcp-adk`) — built by a background subagent. Uses `LiteLlm(model=
    "bedrock/us.anthropic.claude-sonnet-4-6")` + `LlmAgent` + `InMemoryRunner`; added `litellm` to
    the venv/requirements. Smoke test passed (parsed diff, token usage + latency in meta; ADK exposes
    no cost field). Benign SSL/event-loop teardown warning on Win/3.10 only — gone on Linux/3.12.
  - **LangChain** (`agents/langchain`) — built by a background subagent. Uses
    `ChatBedrockConverse(model_id="us.anthropic.claude-sonnet-4-6")` + System/Human messages +
    `ainvoke`. Smoke test passed (parsed diff, token usage + Bedrock latency in meta).
  - All three return the SAME envelope `{framework, model, diff, raw, meta}` → ready for the Phase-1
    bake-off. (Used 2 parallel background subagents to build ADK + LangChain while main built the UI.)
- **AgentCore server validated:** `app.py` runs the AgentCore contract locally; `/ping` → Healthy,
  `/invocations` → the envelope directly. Made the port configurable via `PORT` env.
- **Elaborate sample policies as PDFs:** `tools/generate_policies.py` (reportlab) generates
  `samples/policy_a.pdf` + `policy_b.pdf` — multi-section HO-3 homeowners policies (declarations,
  Coverages A–F, deductibles, endorsements, perils, exclusions, conditions), Plan A vs renewal Plan B.
- **Web UI (agent viewer):** `control-plane/app/main.py` (FastAPI) + `app/static/index.html`.
  - `GET /` serves the viewer; `GET /api/samples` lists sample PDFs; `POST /api/compare` extracts
    PDF text (pypdf) and proxies to the agent `/invocations` (mirrors UI→control-plane→AgentCore).
  - Added deps: `python-multipart`, `pypdf`, `reportlab`.
  - **Verified end-to-end:** picking the two sample PDFs → 16 coverages, premium $1,842→$2,176
    (+18.1%). Round-trip ~57s for the elaborate policies (more output tokens).
- **Ports (unique, per request):** agent **8771**, control-plane UI **8770** (both env-configurable
  via `PORT` / `AGENT_URL`).
- **Running locally now:** agent server (bg) on 8771, control-plane (bg) on 8770 → open
  http://127.0.0.1:8770.

---

## 2026-06-22 — Story pivot: distinct specialist roles + cross-framework orchestration

Reframed the platform (approved plan: `~/.claude/plans/for-gcp-adk-...md`). The three frameworks no
longer do the same task — each is a **distinct specialist**, and Phase 2 **orchestrates all three**
toward one goal: **Intelligent Claims Adjudication** (FNOL → decision). AgentCore = the substrate;
the **orchestrator is an agent** (runtime-selectable framework), not AgentCore itself.

- **Shared contracts:** `shared/contracts.md` — `claim_record`, `coverage_determination`,
  `risk_assessment`, `adjudication_package`, common envelope, per-agent payloads, local port map.
- **Three specialists refactored (3 parallel subagents, each verified live on Sonnet 4.6):**
  - **Intake & Document Intelligence** (GCP ADK, `agents/gcp-adk/intake.py`) — FNOL+policy → `claim_record`.
    Verified: policy #, $16,700 total, water peril, 4 line items.
  - **Coverage & Adjudication** (Claude SDK, `agents/claude-sdk/coverage.py`) — `claim_record`+policy →
    coverage determination. Verified: eligible $15,700, $1,000 deductible.
  - **Risk, Fraud & Compliance** (LangChain, `agents/langchain/risk.py`) — `claim_record` → fraud score
    + RAG over `samples/kb/`. Verified: score 28, low, cites G-12/G-30/R-05.
  - Old `policy_comparison.py` removed from each; envelope now `{framework, model, result, raw, meta}`.
- **Sample claim data:** `tools/generate_claim.py` → `samples/claims/fnol_form.pdf` +
  `repair_estimate.pdf` (burst-pipe water claim). Fixed loss date to fall within Plan A's term
  (was 2026-09-14 → now 2026-03-14; ADK Intake caught the original expiry mismatch). KB in `samples/kb/`.
- **Orchestrator (Claude SDK):** `agents/orchestrator-claude/` (own venv). Calls specialists via HTTP
  `/invocations` ("agents as tools"), then synthesizes the `adjudication_package` + human-approval gate.
  Pluggable by design (control-plane picks the orchestrator → runtime-selectable, M-E adds more).
- **Control-plane rewritten** (`control-plane/app/main.py`): agent **registry** (`/api/registry`),
  Phase-1 `/api/run/{agent}`, Phase-2 `/api/adjudicate?orchestrator=`, PDF→text extraction.
- **UI rewritten** (`app/static/index.html`): two tabs — Phase-1 specialist cards (run each, see its
  distinct output + runtime) and Phase-2 adjudication (orchestrator dropdown, pipeline view, decision
  + drafted customer letter + approval gate + specialist outputs).
- **Ports:** control-plane 8770, Coverage 8771, Intake 8772, Risk 8773, Orchestrator 8774 (all bg, live).
- **Verified end-to-end:**
  - Orchestrator direct: Intake(gcp-adk,17.5s) → Coverage(claude,54.9s) → Risk(langchain,19.8s) →
    **decision APPROVE, payout $15,700, approval_required, total ~123s**.
  - Control-plane: `/api/registry` ✓, `/api/run/risk` ✓ (15s), serves UI at http://127.0.0.1:8770.

### Open / next
- [x] Visually QA the UI (user reviewed; fixed input-panel layout + added "View input"/source-doc viewers).
- [skip] M-E (extra orchestrators) — one orchestrator is enough; pivoted to real AgentCore deployment.

---

## 2026-06-23 — Ownership briefing doc, then FIRST agent on real AgentCore Runtime

**Ownership doc:** wrote `docs/ownership-and-shared-responsibility.{md,pdf}` (IS vs AI Platform vs App
vs Risk/Compliance) — roles legend, layered model, the "seams", two kinds of guardrails
(infra vs AI/behavioral; Bedrock Guardrails enablement ≠ authorship), and a 15-row RACI. PDF via
`tools/generate_ownership_doc.py` (reportlab). For the user's IS-ownership conversation.

**First real AgentCore deployment** (pivot from local — user: "move to agentcore"):
- Deployed **Intake (GCP ADK)** to **AgentCore Runtime** via the `bedrock-agentcore-starter-toolkit`
  `agentcore` CLI (configure → deploy → invoke); **container build via CodeBuild** (no local Docker).
- **Windows gotchas (apply to every agentcore cmd):** `PYTHONIOENCODING=utf-8` (CLI prints emojis;
  cp1252 crashes), `AGENTCORE_SUPPRESS_RECOMMENDATION=1`; PowerShell flags CLI stderr as error even on
  success (check real exit code). `direct_code_deploy` needs local `uv`+`zip` (Windows gaps) → used container.
- **First build failed = Docker Hub 429 rate limit** on `python:3.12-slim`. **Fix:** base image → ECR
  Public `public.ecr.aws/docker/library/python:3.12-slim` in **all 4 Dockerfiles**; rebuild 45s. Also
  fixed langchain Dockerfile stale `COPY policy_comparison.py` → `risk.py`.
- **Auto-created in account <ACCOUNT_ID> / us-east-1:** runtime + CodeBuild IAM roles, ECR repo, S3
  source bucket, CodeBuild project, **AgentCore Memory** `intake_mem-uMLb0ZDUzN` (STM 30-day), and the
  **Runtime + DEFAULT endpoint**.
- **Intake ARN:** `arn:aws:bedrock-agentcore:us-east-1:<ACCOUNT_ID>:runtime/intake-Qh80tlHMU7`
- **AC-3 verified (data plane):** boto3 `bedrock-agentcore.invoke_agent_runtime` + sample FNOL/policy
  → 200, framework gcp-adk, correct claim_record ($16,700, water, 4 items), ~16.5s. Exec role had
  Bedrock access out of the box.
- **Clarified for user:** AgentCore agents = authenticated AWS-API invoke, **not a public URL**; a
  public URL = control-plane+UI on **ECS Fargate + ALB** calling agents privately. AWS AgentCore
  console = ops view (runtimes/sessions/memory/gateways/identity/observability), distinct from our UI.

---

## 2026-06-23 — Full multi-agent pipeline running on real AgentCore (AC-4)

All four agents deployed to **AgentCore Runtime**; the orchestrator drives the whole pipeline
cross-runtime. **Nothing runs on localhost.**

- **Deployed runtimes (us-east-1, acct <ACCOUNT_ID>), all container/CodeBuild, each with its own
  Memory + auto observability (logs+traces):**
  - Intake (GCP ADK): `arn:aws:bedrock-agentcore:us-east-1:<ACCOUNT_ID>:runtime/intake-Qh80tlHMU7`
  - Risk (LangChain): `…runtime/risk-6E7mYl67hr` — KB bundled into image (`/app/kb`), KB_DIR made file-relative.
  - Coverage (Claude SDK): `…runtime/coverage-OOtx7ZBLo1` — **bundled Claude Code CLI subprocess WORKS in the arm64 container** (the big unknown — cleared).
  - Orchestrator (Claude SDK): `…runtime/orchestrator-jSuJgQFRjV`.
- **Dockerfile fixes for deploy:** all base images → `public.ecr.aws/docker/library/python:3.12-slim`
  (Docker Hub 429); langchain `COPY risk.py`, claude-sdk `COPY coverage.py`; created orchestrator Dockerfile.
- **Orchestrator repointed to AgentCore:** `orchestrate.py` now calls specialists via
  `bedrock-agentcore.invoke_agent_runtime` when `<NAME>_ARN` env is set (boto3, `asyncio.to_thread`),
  else localhost HTTP. Deployed with `INTAKE_ARN/COVERAGE_ARN/RISK_ARN` env.
- **IAM:** attached inline policy `InvokeSpecialistRuntimes` (bedrock-agentcore:InvokeAgentRuntime on
  the 3 specialist ARNs + `/*`) to the orchestrator execution role
  `AmazonBedrockAgentCoreSDKRuntime-us-east-1-11376b7e2a`.
- **Verified each on AgentCore data plane (boto3 invoke_agent_runtime):**
  - Intake → correct claim_record ($16,700, water, 4 items).
  - Risk → fraud 18/low, cites G-30/G-12/R-05 from the bundled KB.
  - Coverage → covered, eligible $15,700, deductible $1,000.
  - **Orchestrator (full pipeline) → 182.9s, decision APPROVE, $15,700, approval_required; steps show
    intake(gcp-adk)/coverage(claude-sdk)/risk(langchain) each ok on their own runtime.**
- **Windows/CLI notes:** every `agentcore` cmd needs `PYTHONIOENCODING=utf-8` +
  `AGENTCORE_SUPPRESS_RECOMMENDATION=1`; toolkit venv Scripts on PATH (uv); data-plane invoke needs a
  long boto3 `read_timeout` (used 900s) since the chain cold-starts several runtimes.

---

## 2026-06-23 — AC-6: public URL live on AWS App Runner (auth pending)

The control-plane + UI is deployed to **AWS App Runner** with a public HTTPS URL, driving the private
AgentCore agents. Chose App Runner over Fargate+ALB+CloudFront — auto-HTTPS on `awsapprunner.com`,
no domain/cert/VPC needed (cleanest fit for the Gmail-login requirement).

- **Public URL:** **<APP_RUNNER_URL>** (service `agent-core-console`).
- **Image build (no local Docker):** ECR repo `agent-core-control-plane`; CodeBuild project
  `agent-core-control-plane-builder` (role `agent-core-cp-codebuild`); `control-plane/Dockerfile`
  (context=repo root, copies control-plane/ + samples/) + `control-plane/buildspec.yml`.
- **Bugs fixed during deploy:**
  1. **Windows `Compress-Archive` writes ZIP entries with backslashes** → Linux CodeBuild saw flat
     filenames, COPY failed. Fix: build the zip with **Python zipfile + forward-slash arcnames**.
  2. **uvicorn bound `127.0.0.1`** → App Runner health check unreachable → `CREATE_FAILED`. Fix:
     bind `0.0.0.0` (`main.py` `HOST` env, default 0.0.0.0). Rebuilt + recreated service.
- **App Runner config:** image port 8080, instance role `agent-core-apprunner-instance`
  (bedrock-agentcore:InvokeAgentRuntime on all 4 runtime ARNs), access role
  `agent-core-apprunner-access` (ECR pull), env = AWS_REGION + the 4 ARNs. Health check `/healthz`.
- **Verified live:** `/healthz`, `/`, `/api/registry` all 200 over HTTPS (forced-resolve from here
  due to stale local DNS; public DNS resolves globally).
- **Google sign-in gate (code):** `main.py` has app-level Authlib Google OAuth behind `GOOGLE_CLIENT_ID`
  (off when unset → local ungated), restricting to `ALLOWED_EMAILS` (default `anup.iit@gmail.com`).
  Routes `/login`, `/auth/callback`, `/logout`, `/healthz` public; SessionMiddleware. **Currently the
  App Runner service is UNGATED** (no Google client yet).
- **Redirect URI for Google client:** `<APP_RUNNER_URL>/auth/callback`.

### AC-6 finish — DONE (switched Google OAuth → HTTP Basic Auth at user's request)
- User preferred a simple username/password over Google sign-in → added **HTTP Basic Auth** gate to
  `main.py` (`BASIC_AUTH_USER`/`BASIC_AUTH_PASS` env; `/healthz` open). Password stored in Secrets
  Manager `agent-core/console-password`; instance role granted `GetSecretValue`.
- App Runner env: `BASIC_AUTH_USER` (plain) + `BASIC_AUTH_PASS` (RuntimeEnvironmentSecrets → secret).
- **Gotcha:** `update-service` did NOT re-pull the `:latest` image (tag string unchanged), so the old
  image ran without the gate → had to run **`apprunner start-deployment`** to force a fresh pull.
- **VERIFIED live:** no creds → 401, wrong creds → 401, correct creds → 200, `/healthz` → 200.
- ✅ **Public gated demo:** <APP_RUNNER_URL> (user `anuproy2026`).
- Google OAuth code remains in `main.py` behind `GOOGLE_CLIENT_ID` (unused); the placeholder secret
  `agent-core/google-oauth-client-secret` is unused (can be deleted).

---

## 2026-06-23 — UI: AgentCore runtime badges + live CloudWatch logs (observability surfacing)

Answered "where is observability" + "show it's running on AgentCore" by surfacing AgentCore's
auto-provisioned telemetry in the console (the Platform-layer obs view).
- **control-plane** (`main.py`): `/api/registry` now returns `region`, `on_agentcore`,
  `observability_dashboard` (GenAI Observability URL). New **`GET /api/logs/{agent}`** pulls recent
  events from that agent's runtime log group `/aws/bedrock-agentcore/runtimes/<id>-DEFAULT` via
  CloudWatch Logs `filter_log_events` + a deep link to the log group.
- **UI** (`index.html`): header shows "running on AWS Bedrock AgentCore (region) · Observability ↗";
  each agent card shows an **AgentCore runtime badge** (region + runtime id) and a **"Live runtime
  logs (AgentCore → CloudWatch)"** expander.
- **IAM:** added `read-runtime-logs` inline policy (logs:FilterLogEvents/GetLogEvents/Describe*) to
  the App Runner instance role.
- **Deploy:** rebuilt image (CodeBuild) → resume service (was PAUSED) → `start-deployment` to pull
  new image. **Verified:** `/api/logs/coverage` returned real runtime logs ("Invocation completed
  successfully (40.570s)", requestId/sessionId) from `coverage-OOtx7ZBLo1`.
- Note: observability "build" = AgentCore auto-provisions logs+OTEL traces per runtime (substrate);
  this is the product view on top. Service is RUNNING again (resumed for deploy) — pause when idle.
- **Follow-up:** added a dedicated **Observability tab** in the UI (a 3rd tab) — one panel per runtime
  (Intake/Coverage/Risk/Orchestrator) with runtime id + live CloudWatch logs + "Refresh all" +
  GenAI dashboard link. Rebuilt image + start-deployment; verified the tab is in the served page.
- **Insights (not just logs):** added `GET /api/metrics` — parses each runtime's CloudWatch
  "Invocation completed (Xs)" logs into invocation count, avg/p95/max latency, session count,
  last-seen, busiest agent; UI Observability tab now shows KPI cards + a per-runtime table above the
  logs. Verified live: 24 invocations / 22 sessions / avg 46.6s; orchestrator avg ~161s (full pipeline).

## 2026-06-23 — Fix: Phase-2 adjudication "upstream request timeout" on App Runner

- **Symptom:** UI Phase-2 → "Unexpected token 'u', \"upstream r\"... is not valid JSON".
- **Cause:** App Runner caps inbound HTTP ~120s; the orchestration pipeline runs ~150-180s, so the
  gateway returned plain-text `upstream request timeout` (not JSON).
- **Fix (async job pattern):** `POST /api/adjudicate` now starts a background `asyncio` task and
  returns `{job_id}` instantly; new `GET /api/adjudicate/{job_id}` returns running|done|error; the UI
  polls every 4s (`ADJ_JOBS` in-memory). Each request is short → no gateway timeout.
- **Verified live through App Runner:** POST→job_id→poll→done in ~110s, decision APPROVE $15,700,
  steps intake/coverage/risk all ok.
- (Single App Runner instance at this traffic keeps the in-memory job consistent across polls.)

## (earlier) AC-5

- [x] **AC-5 done:** control-plane repointed to AgentCore — `main.py` `_invoke()` uses
      `invoke_agent_runtime` when `<NAME>_ARN`/`ORCH_CLAUDE_ARN` env set (localhost fallback). Restarted
      locally wired to the 4 ARNs; `/api/run/intake` verified hitting the AgentCore runtime (200, correct
      claim_record, local agent servers stopped). Local UI at :8770 now drives the deployed pipeline.
- [ ] Public URL: containerize control-plane + UI → **ECS Fargate + ALB** (agents stay private).
- [ ] Product-grade per-agent **runtime/observability view** in the UI (on top of AgentCore telemetry).
- [ ] Later: Bedrock Knowledge Base for RAG; Gateway (MCP) for registry+tools; CDK to codify it all.

## 2026-06-25 — Governance layer: certification-gated deployment (the "Money Shot")

Implements `Demo-Plan-MoneyShot-CertGated-2026-06-25.md` as the policy/governance milestone
(`STATUS.md` "Policy engine"; `PLAN.md §7`). Design spec: **`GOVERNANCE-PLAN.md`**.

- **What.** A new control-plane router **`control-plane/app/governance.py`** turns the platform from a
  *router* into a *gate*. Same Coverage agent, two doors: **raw AgentCore** (`/api/raw/execute`, no
  checks) vs the **cert-gated platform** (`/api/agents/{id}/execute`, R-01 validator). An agent only
  runs on the platform if it holds a cryptographically signed certificate earned via a BUILD pipeline.
- **BUILD pipeline** (`POST /api/agents/submit` → background job, polled at `/api/pipeline/{id}`,
  reusing the `ADJ_JOBS` pattern): capability-validation (vs `policies/allowlist.yaml`) → risk scoring
  (tier 1-3) → **live eval** against the real agent (accuracy on golden claim, prompt-injection
  resistance, capability conformance) → **certification** (sign → store) → register CERTIFIED.
- **R-01 validator** blocks with the demo's exact reasons: `NO_CERTIFICATE_FOUND`,
  `CERTIFICATE_REVOKED`, `CERTIFICATE_EXPIRED`, `SIGNATURE_INVALID`. Plus `/revoke`, `/status`,
  `/certs/{id}`, `/seed-expired`, `/governance/config`.
- **Pluggable** (mirrors the "ARN-or-localhost" idiom): signing = **AWS KMS** if `CERT_SIGNING_KEY_ID`
  set, else a **local RSA-2048** keypair under `control-plane/.governance/` (real, verifiable
  signature either way). Storage = **DynamoDB** if `CERT_TABLE` set, else a local JSON store.
  Re-certification clears any prior revocation; signed cert is immutable (revocation/expiry tracked
  outside the signed blob).
- **Agent change:** Coverage agent (`agents/claude-sdk/coverage.py` + `app.py`) now accepts an optional
  `system_prompt`, so the demo "bad" agent is a **real degraded run** of the live agent (fails accuracy)
  rather than a faked score. (Needs a Coverage redeploy to use the override on AgentCore; works
  immediately locally.)
- **UI:** new **🔐 Governance — Cert Gate** tab, written for non-technical "techno-manager" audiences —
  a 4-step "how it works" strip, a raw-vs-platform split with big **✅ runs / ⛔ blocked** verdict
  banners and plain-English meanings, the live BUILD pipeline, and plain-language eval labels
  ("Gives correct answers / Resists manipulation / Stays within approved powers"). Technical JSON is
  tucked into "Technical detail" expanders.
- **Verified (offline, stubbed agent via TestClient):** all 5 scenarios + a tamper test — **17/17
  assertions pass**. S1 uncertified→BLOCKED; S2 good→CERTIFIED (tier 2, signature verifies)→EXECUTED;
  S3 degraded→accuracy 0%→REJECTED→BLOCKED; S4 revoke→BLOCKED while raw still runs; S5 expired→BLOCKED;
  TAMPER (altered signed field)→SIGNATURE_INVALID.
- **Deploy notes:** Dockerfile now also `COPY policies` (allow-list needed in the image). `.gitignore`
  ignores `.governance/` (local key + store). For production: provision a KMS signing key + DynamoDB
  table + S3 Object Lock and set `CERT_SIGNING_KEY_ID`/`CERT_TABLE`/`CERT_BUCKET`.

### How to run the demo locally
1. Start the 4 agents (or set the `*_ARN` env so the gate invokes AgentCore). For a pure local run,
   start at least the Coverage agent (`agents/claude-sdk` → `python app.py`, port 8771) and export
   `COVERAGE_URL=http://127.0.0.1:8771/invocations` for the control-plane.
2. `cd control-plane/app && python main.py` → open http://127.0.0.1:8770 → **🔐 Governance** tab.
3. Walk the scenarios top-to-bottom: ① Invoke raw (runs) vs Execute claims-coverage-v1 (BLOCKED) →
   ② Submit GOOD (certifies) then Execute (runs) → ③ Submit BAD (rejected) → ④ Revoke then Execute
   (blocked) while Raw still runs → ⑤ Seed expired, pick v0, Execute (blocked).
- **Next:** redeploy Coverage with the `system_prompt` override; provision KMS/DynamoDB/S3 for prod
  signing; lock the AgentCore exec role so raw is only reachable via R-01 (closes the bypass shown
  side-by-side); Phase 2 = **R-06 runtime capability enforcement**.
