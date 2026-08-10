# AgentCore Certifier — High-Level Block Flow

> The **certifier microservice** (`control-plane/app/governance.py`) is a control-plane gate that
> sits *in front of* AWS Bedrock AgentCore. An agent runs freely on **raw AgentCore**, but on **the
> platform** it is BLOCKED unless it carries a valid, cryptographically signed certificate — earned
> by passing a BUILD pipeline, and killable by revocation or expiry (the **R-01** gate).

## Block flow

> Rendered with AWS service icons. To export with icons, pass the Iconify logos pack:
> `mmdc --iconPacks @iconify-json/logos -i docs/certifier-flow.md -o docs/certifier-flow.svg`

```mermaid
flowchart TB
  classDef build  fill:#1f7a1f,stroke:#0d3d0d,color:#fff;
  classDef gate   fill:#c79100,stroke:#7a5800,color:#fff;
  classDef ext    fill:#3a3f44,stroke:#22262a,color:#ddd;

  USER["Developer / Platform UI"]:::ext

  %% ---------------- BUILD PIPELINE (earn the cert) ----------------
  subgraph BUILD["BUILD pipeline — POST /api/agents/submit (background job, polled via /api/pipeline/{id})"]
    direction TB
    M["1 · Manifest intake<br/>agent_id, framework, target,<br/>capabilities, risk_inputs"]:::build
    CAP["2 · Capability validation<br/>tools/models/data/framework ⊆ allowlist.yaml"]:::build
    RISK["3 · Risk scoring<br/>3·PII + 3·external + 2·write → Tier 1-3"]:::build
    EVAL["4 · Live eval (runs the REAL agent)<br/>① accuracy ≥0.80  ② guardrail/injection =1.0  ③ capability =1.0"]:::build
    SIGN["5 · Issue certificate<br/>assemble cert JSON → sign → store"]:::build
    M --> CAP -->|pass| RISK --> EVAL -->|all pass| SIGN
    CAP -->|fail| REJ1["REJECTED · CAPABILITY_DENIED"]:::ext
    EVAL -->|below threshold| REJ2["REJECTED · EVAL_FAILED · no cert"]:::ext
  end

  %% ---------------- AWS: signing ----------------
  KMS@{ icon: "logos:aws-kms", form: "square", pos: "b", label: "AWS KMS — asymmetric sign / verify (RSA fallback if no key)" }
  SIGN -. "kms:Sign" .-> KMS

  %% ---------------- AWS: cert store ----------------
  subgraph STORE["Cert store (DynamoDB + S3 if configured, else local JSON)"]
    direction LR
    DDB@{ icon: "logos:aws-dynamodb", form: "square", pos: "b", label: "DynamoDB — certs · manifests · revocations" }
    S3@{ icon: "logos:aws-s3", form: "square", pos: "b", label: "S3 Object Lock — immutable cert archive" }
  end
  SIGN --> DDB

  %% ---------------- R-01 GATE (use the cert) ----------------
  subgraph GATE["R-01 Certificate Validator — POST /api/agents/{id}/execute"]
    direction TB
    V{"Cert found?<br/>not revoked?<br/>signature valid?<br/>not expired?"}:::gate
  end

  %% ---------------- AWS: execution target ----------------
  AC@{ icon: "logos:aws", form: "square", pos: "b", label: "AWS Bedrock AgentCore Runtime — InvokeAgentRuntime (Coverage / Intake / Risk / Orchestrator)" }
  CW@{ icon: "logos:aws-cloudwatch", form: "square", pos: "b", label: "CloudWatch — OTEL traces / observability" }

  %% flows
  USER -->|submit manifest| M
  USER -->|run on platform| V
  USER -->|raw run, NO cert| RAW["POST /api/raw/execute<br/>(bypass — contrast screen)"]:::ext

  V -. reads .-> DDB
  V -->|ALL pass| AC
  V -->|any fail| BLOCK["403 BLOCKED<br/>NO_CERTIFICATE / REVOKED /<br/>EXPIRED / SIGNATURE_INVALID"]:::gate
  RAW --> AC
  AC -. OTEL .-> CW

  USER -->|kill switch| REVOKE["POST /api/agents/{id}/revoke"]:::gate
  REVOKE --> DDB
  EVAL -. invokes live agent .-> AC
```

## How to read it

- **Earn it (green):** `submit` a manifest → the pipeline validates capabilities against
  `policies/allowlist.yaml`, scores risk, then **invokes the real agent on AgentCore** for 3 live
  tests (accuracy, prompt-injection/guardrail, capability conformance). Pass all → a cert is
  assembled and **signed** (local RSA-2048 by default, AWS KMS if `CERT_SIGNING_KEY_ID` is set) and
  stored.
- **Use it (amber):** `execute` hits the **R-01 validator** — cert exists, not revoked, signature
  verifies, not expired. Pass → forwards to `InvokeAgentRuntime`. Fail → **403 BLOCKED** with a
  specific reason.
- **Contrast / kill switch:** `raw/execute` runs straight on AgentCore with *no* check (proving the
  engine runs anything); `revoke` writes a revocation so the very next `execute` is blocked — same
  for expiry.
- **Pluggable backends:** signing = KMS or local RSA; storage = DynamoDB or local JSON file — same
  signed, verifiable artifact either way.

## Key endpoints

| Method | Path | Role |
|---|---|---|
| POST | `/api/agents/submit` | Start BUILD pipeline (background job) |
| GET  | `/api/pipeline/{exec_id}` | Poll pipeline state + stage log |
| POST | `/api/agents/{id}/execute` | **R-01 gate** → validate cert → `InvokeAgentRuntime` else BLOCKED |
| POST | `/api/raw/execute` | Raw AgentCore, no cert check (contrast) |
| POST | `/api/agents/{id}/revoke` | Kill switch → next execute BLOCKED |
| GET  | `/api/agents/{id}/status` | `CERTIFIED \| REVOKED \| EXPIRED \| NONE` |
| GET  | `/api/certs/{cert_id}` | The signed certificate JSON |
