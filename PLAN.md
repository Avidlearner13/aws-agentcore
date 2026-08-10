# Agent-Core Platform — Architecture & Build Plan

> Reference plan derived from `PRD.md`. Living document — update as decisions land.
> Status: **DRAFT for review** · Owner: anup.iit@gmail.com · Last updated: 2026-06-22

---

## 1. Goal

Build a **framework-agnostic enterprise agentic-AI platform for an insurance company**, using
**AWS Bedrock AgentCore** as the backbone and an **Angular console** on top.

This is a **proof-of-concept** with two things to prove:

1. **Multi-framework compatibility** — onboard and run a **Claude Agent SDK** agent, a **GCP ADK**
   agent, and a **LangChain** agent on the same AgentCore platform, doing the *same task*.
2. **Orchestrator → workers multi-agent** — a supervisor agent delegating to worker agents within a
   single framework (recommended: **Claude Agent SDK**; alternative: **LangGraph supervisor**).

Cross-cutting capabilities to demonstrate: **agent lifecycle (create / reuse / clone)**, **memory
(short + long term)**, a **policy repository (governance)**, an **MCP Gateway**, and **per-agent
runtime observability**.

---

## 2. Use cases (insurance domain)

### Phase 1 — Multi-framework bake-off: "Policy Document Comparison"
Identical input/output across all three frameworks, so we can compare apples-to-apples.

- **Input:** two policy PDFs (e.g. current vs. renewal, or customer policy vs. competitor quote).
- **Output:** structured diff — coverages, limits, deductibles, exclusions, premium deltas.
- **Why this task:** deterministic-ish, document-heavy, and easy to score → ideal for a framework
  bake-off (accuracy, latency, cost shown side-by-side in the UI).

### Phase 2 — Orchestrator → workers: "Claims Triage / FNOL copilot"
A supervisor classifies an incoming claim (First Notice of Loss) and delegates to workers:

| Worker | Job | Key tool(s) |
|---|---|---|
| Coverage-verification | Confirm the claim is covered | Policy-lookup (Gateway) |
| Document-extraction | Pull facts from claim docs/images | Doc store + Code Interpreter |
| Fraud-signal | Flag anomalies | Fraud-scoring API (Gateway) |
| Comms-drafting | Draft claimant response | KB retrieval + LLM |

Exercises short-term memory (per-claim session), long-term memory (customer/policy history), and
policies (PII redaction, tool-auth approval gates on writes).

### Backlog
- **KB Q&A** over underwriting/claims manuals (RAG via Gateway + Memory).
- **A2A cross-framework collaboration** (stretch): an agent in one framework calling an agent in
  another.

---

## 3. System architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│  Angular Console (UI)                                                  │
│  Registry · Run/Compare · Runtime view · Memory · Policies · Gateway   │
└───────────────▲──────────────────────────────────────────────────────┘
                │ REST/WebSocket
┌───────────────┴──────────────────────────────────────────────────────┐
│  Control Plane API (our backend)                                       │
│  - Agent registry & blueprints (create/reuse/clone)                    │
│  - Policy engine (enforce governance + tool-auth)                      │
│  - Run orchestration & comparison                                      │
│  - Observability aggregation (per-agent runtime)                       │
└───────────────▲──────────────────────────────────────────────────────┘
                │ AWS SDK (bedrock-agentcore + bedrock-agentcore-control)
┌───────────────┴──────────────────────────────────────────────────────┐
│  AWS Bedrock AgentCore                                                  │
│  Runtime · Memory · Gateway (MCP) · Identity · Observability · Tools   │
│   ┌──────────────┐ ┌──────────────┐ ┌──────────────┐                   │
│   │ Claude SDK   │ │ GCP ADK      │ │ LangChain    │  (each = a        │
│   │ agent runtime│ │ agent runtime│ │ agent runtime│   Runtime+Endpoint)│
│   └──────────────┘ └──────────────┘ └──────────────┘                   │
└────────────────────────────────────────────────────────────────────────┘
                │
        Internal insurance APIs (you provide) → exposed as MCP tools via Gateway
```

### AgentCore component mapping
| Component | Use | Likely API surface (verify vs. current SDK) |
|---|---|---|
| **Runtime** | Host each agent (container, framework-agnostic); session isolation | `CreateAgentRuntime`, `CreateAgentRuntimeEndpoint`, `InvokeAgentRuntime` |
| **Memory** | Short-term (session events) + long-term strategies | `CreateMemory`, `CreateEvent`/`ListEvents`, `RetrieveMemoryRecords` |
| **Gateway** | Turn internal insurance APIs/Lambdas into MCP tools | `CreateGateway`, `CreateGatewayTarget` |
| **Identity** | Per-agent identity + OAuth to downstream systems | Workload identity, OAuth credential providers |
| **Observability** | OTEL traces → CloudWatch GenAI Observability | OTEL exporter + CloudWatch / Transaction Search |
| **Built-in tools** | Code Interpreter (calcs), Browser (lookups) | AgentCore tool runtimes |

> Runtime contract: each agent container serves `/invocations` + `/ping` on port 8080 (or use the
> `bedrock-agentcore` SDK `BedrockAgentCoreApp` + the `agentcore` starter-toolkit CLI to package).

---

## 4. Agent lifecycle workflow (create / reuse / clone)

A **Blueprint** layer in our control plane sits above AgentCore runtimes so agents are reusable.

### Data model
```
Blueprint (versioned template)
  id, name, framework {claude-sdk | gcp-adk | langchain},
  model, system_prompt, tool_bindings[], memory_namespaces[],
  policy_set_ref, runtime_image_ref, env, version

AgentInstance (a deployed agent)
  id, blueprint_id + version, agentcore_runtime_arn, endpoint,
  status, owner, created_at, tags
```

### Workflows
- **Create new:** author a Blueprint → build/push container → `CreateAgentRuntime` +
  `CreateAgentRuntimeEndpoint` → register `AgentInstance`. UI: "New Agent" wizard.
- **Reuse (run):** an existing `AgentInstance` is invoked with a new session — runtime is inherently
  multi-session/isolated, so "reuse" = new `InvokeAgentRuntime` session, no redeploy. UI: "Run".
- **Clone:** copy a Blueprint → tweak (model/prompt/tools/policies) → deploy as a new
  `AgentInstance`. UI: "Clone & edit". Used to create variants or new agents fast.
- **Version:** Blueprints are versioned; redeploy bumps an AgentInstance to a new runtime version.

This satisfies "reuse an agent **and** create a new one" with a single registry-driven flow.

---

## 5. Per-agent runtime view (observability workflow)

Each `AgentInstance` gets a **Runtime detail page** answering: is it running, what is it doing now,
how fast/expensive, and what did it touch.

- **Status & sessions:** live/idle, active session count, last invocation time.
- **Live invocation:** current trace (steps, tool calls, sub-agent calls), streamed via WebSocket.
- **Performance:** latency (p50/p95), token usage, $ cost per run and rolling.
- **Memory activity:** reads/writes per namespace, with policy badges (e.g. "PII redacted").
- **Tool activity:** which Gateway tools were called, success/failure, any approval gates hit.
- **Logs & traces:** link-through to the full OTEL trace / CloudWatch.

**Data path:** agent runtimes emit OTEL → CloudWatch; the control plane aggregates per
`AgentInstance` and exposes a normalized `/agents/{id}/runtime` API the Angular page consumes
(polling + WebSocket for live runs).

---

## 6. Memory design
- **Short-term:** per-session events (the active claim/comparison) via Memory events.
- **Long-term strategies:** `SEMANTIC` (customer/policy history), `SUMMARIZATION` (past
  interactions), `USER_PREFERENCE` (handler preferences). Configurable per Blueprint.
- **Namespacing:** memories scoped by tenant/customer/agent for isolation + RBAC.

---

## 7. Policy repository (governance)
Versioned policies (YAML/JSON in-repo), enforced by a control-plane middleware layer on every
memory write and tool call.

| Policy type | What it does |
|---|---|
| **Data governance** | PII redaction (SSN/claimant data) before memory writes; retention TTL per namespace; right-to-be-forgotten delete |
| **Tool authorization** | Which agent may call which Gateway tool; human-in-the-loop approval gates on write/financial actions |
| **Guardrails** | Bedrock Guardrails — denied topics, insurance-regulatory content safety, prompt-injection defense |
| **Access control** | RBAC over memory namespaces and tools (per agent/tenant) |
| **Audit** | Every tool call + memory access logged for compliance |

Repo layout: `policies/<domain>/<policy>.yaml`, referenced by `policy_set_ref` on each Blueprint.

---

## 8. MCP Gateway / tools (you provide the APIs)
Expose internal insurance systems as MCP tools via Gateway targets:
- Policy lookup, claims DB, document store (S3), KB retrieval, fraud scoring.
- Plus AgentCore built-ins: Code Interpreter, Browser.

**Needed from you (placeholders for now):** API specs (OpenAPI/Smithy or Lambda ARNs), auth method,
sample data. Until provided, we mock these so the demo runs end-to-end.

### 8a. Agent Registry on MCP ("agents as tools")
The **Blueprint/AgentInstance registry (§4) is itself exposed through the MCP Gateway**, so agents
are discoverable and callable like any other tool:

- **Registry-discovery tools:** `list_agents`, `describe_agent(id)` — return available agents,
  their capabilities, and input/output schemas (sourced from the Blueprint).
- **Agent-invocation tool:** `invoke_agent(id, input, session?)` — a thin Gateway target that maps
  to `InvokeAgentRuntime` on that AgentInstance's endpoint.
- **Why it matters:** the orchestrator discovers its workers at runtime via MCP instead of
  hard-wiring them, and a Claude-SDK agent can invoke a LangChain/ADK agent through the *same* MCP
  surface — enabling **cross-framework A2A** with no bespoke glue.
- **Governance:** these agent-invocation tools are subject to the same tool-authorization +
  approval-gate policies (§7) — e.g. which orchestrator may invoke which worker.

---

## 9. Angular console — modules
1. **Agent Registry / Onboarding** — list Blueprints & instances; New / Clone / Reuse wizards.
2. **Run & Compare** — pick task, run across the 3 frameworks, side-by-side results + bake-off.
3. **Agent Runtime** — per-agent live runtime view (§5).
4. **Memory Browser** — short/long-term records by namespace, with policy badges.
5. **Policy Repository** — CRUD + versions; attach to Blueprints/namespaces/tools.
6. **MCP Gateway Catalog** — registered tools, who may call them.
7. **Orchestration View** — live orchestrator→workers graph.

---

## 10. Multi-agent orchestration (the two proofs)
- **Proof A — multi-framework:** Run console fans the same input to all three AgentInstances,
  collects normalized outputs + traces + cost → comparison table.
- **Proof B — orchestrator→workers:** Claims-triage supervisor (Claude Agent SDK) discovers and
  delegates to worker agents **via the MCP-exposed registry (§8a)** rather than hard-wired calls;
  orchestration view animates the graph live. Same MCP surface enables cross-framework A2A.

---

## 11. Tech stack & repo structure (proposed)
```
agent-core/
  ui/                 Angular console
  control-plane/      Backend API (Python FastAPI or Node) + AWS SDK calls
  agents/
    claude-sdk/       Claude Agent SDK agent (Phase 1 task + Phase 2 orchestrator/workers)
    gcp-adk/          GCP ADK agent (Phase 1 task)
    langchain/        LangChain agent (Phase 1 task)
  gateway/            MCP Gateway targets + tool definitions (mocks until APIs arrive)
  policies/           Versioned policy repository (YAML)
  infra/              IaC (CDK/Terraform) for AgentCore resources
  PRD.md  PLAN.md
```
> Control-plane language TBD (Python recommended — best AgentCore SDK + agent tooling support).

---

## 11a. Development & runtime topology (cloud-first, no dev box)
**Principle: the platform runs 100% on AWS; the laptop is only an editor.** Code is edited locally,
but nothing *executes* locally — builds run in CodeBuild, and all runtime is in AWS.

- **Dev model:** edit locally → push → **CodeBuild** builds images → deploy. No EC2/dev box.
- **Baseline Python:** **CPython 3.12 (standard, GIL present)** for all deployed containers. Local
  venvs (currently 3.10) are for IDE/linting/quick tests only; Dockerfiles pin 3.12 for parity.
- **No-GIL rejected as baseline:** free-threaded Python is 3.13t/3.14t (not 3.12); C-extension deps
  (pydantic-core, grpc, awscrt, cryptography, numpy) aren't reliably free-threaded yet, and we don't
  need it — multi-agent parallelism comes from separate Runtime containers/processes, and the
  control-plane is async I/O-bound.

### Deployment topology (where each layer runs)
| Layer | Compute | Notes |
|---|---|---|
| Agents (Claude SDK / ADK / LangChain / orchestrator) | **AgentCore Runtime** | Managed serverless containers; you don't manage EC2/Fargate |
| Control-plane API (FastAPI) | **ECS Fargate** | Serverless containers behind an ALB |
| Angular UI | **ECS Fargate** (or S3+CloudFront static) | Decide at build time |
| Images | **ECR**, built by **CodeBuild** | No local Docker required |
| State (registry, policies) | DynamoDB / S3 (TBD) | Plus AgentCore Memory for agent state |

## 12. Roadmap (POC milestones)
- **M0 — Foundations:** AWS access verified, region chosen, repo skeleton, IaC bootstrap.
- **M1 — Single agent on Runtime:** Claude SDK agent deployed; invoke end-to-end; runtime view v1.
- **M2 — Registry + lifecycle:** Blueprints; create/reuse/clone; onboard ADK + LangChain agents.
- **M3 — Memory + Gateway:** short/long-term memory; first Gateway tools (mock insurance APIs).
- **M4 — Phase 1 proof:** Policy-comparison bake-off across 3 frameworks in the Run & Compare UI.
- **M5 — Policies:** policy repository + enforcement (PII redaction, tool-auth gates, audit).
- **M6 — Phase 2 proof:** Claims-triage orchestrator→workers + live orchestration view.
- **M7 — Polish:** observability/cost dashboards, demo script, hardening.

---

## 13. Prerequisites / open items
- [x] **Region** = us-east-1.
- [x] **AWS CLI v2** installed (2.35.10).
- [x] **Dev model** = edit locally, run everything in AWS (no dev box); **Python 3.12** baseline.
- [x] **Hosting** = control-plane + UI on ECS Fargate; agents on AgentCore Runtime.
- [x] **Agent venvs validated** on 3.10 (will rebuild on 3.12 on the EC2 box).
- [ ] **AWS credentials** → `aws configure --profile agentcore` (you run it; keys never in chat).
- [ ] Confirm **Bedrock Claude model access** enabled in us-east-1.
- [ ] **GCP ADK** project ready, and **LangChain/LangSmith** key — or use mocks for POC.
- [ ] **Internal insurance APIs** specs + auth + sample data (or proceed with mocks).
- [ ] Confirm **control-plane language** (Python recommended).
- [ ] Confirm **Phase 2 orchestrator framework** (recommend Claude Agent SDK).

---

## 14. Decisions log
| Date | Decision |
|---|---|
| 2026-06-22 | Backbone = AWS Bedrock AgentCore + custom Angular UI |
| 2026-06-22 | Purpose = POC to prove the concept |
| 2026-06-22 | Two-phase agent story: multi-framework compatibility, then orchestrator→workers |
| 2026-06-22 | Domain = insurance; Phase 1 = policy doc comparison, Phase 2 = claims triage/FNOL |
| 2026-06-22 | UI stack = Angular |
| 2026-06-22 | Agent lifecycle via Blueprint registry: create / reuse / clone |
| 2026-06-22 | Per-agent runtime view required → observability aggregation in control plane |
| 2026-06-22 | Policies: data governance + tool-auth + guardrails + RBAC + audit |
| 2026-06-22 | Agent registry exposed via MCP Gateway ("agents as tools") → registry-driven orchestration + cross-framework A2A |
| 2026-06-22 | Platform runs 100% on AWS; laptop is editor only (no dev box). Build via CodeBuild |
| 2026-06-22 | Hosting: control-plane API + Angular UI on ECS Fargate; agents on AgentCore Runtime |
| 2026-06-22 | Baseline = CPython 3.12 (standard). No-GIL/free-threaded rejected as baseline (ecosystem + not needed) |
| 2026-06-22 | Agent dependency sets validated on Py3.10: claude-agent-sdk 0.2.107, google-adk 2.3.0, langchain 1.3.11/langgraph 1.2.6, bedrock-agentcore 1.15.0 |
```
