# Demo Plan: The "Money Shot" — Certification-Gated Agent Deployment

> **Hand this to the team that has AgentCore agents ready.**
> Everything they need to build, rehearse, and deliver the demo is here.

---

## What We're Proving in One Sentence

**The same agent runs freely on raw AgentCore but is blocked on the AIG Platform without a certificate — and can be killed instantly by revoking one.**

---

## Pre-Requisites — What You Need Before Demo Day

### Agents You Need Ready

| Agent | Purpose | Where It Lives |
|-------|---------|----------------|
| **Claims Summarizer Agent** | The "good" agent — will go through full certification and pass | Your existing AgentCore setup |
| **Same agent, uncertified copy** | Identical agent but never submitted to the platform | Direct AgentCore deployment |
| **Bad Accuracy Agent** | A deliberately broken version (returns wrong answers to golden Q&A) | Variant of Claims Summarizer with bad prompts |

> You only need ONE real agent (Claims Summarizer). The "uncertified copy" is the same agent deployed directly. The "bad" agent is a copy with intentionally degraded system prompts so it fails eval.

### Infrastructure Ready

| Component | Status Needed | Who Owns |
|-----------|---------------|----------|
| AgentCore with Claims Summarizer deployed directly (no platform) | Running | Your team |
| Platform APIs deployed (B-01 through R-01) | Running | Platform team |
| KMS signing key provisioned | Active | Platform team |
| DynamoDB tables created (empty) | Ready | Platform team |
| S3 buckets with Object Lock | Ready | Platform team |
| Demo dashboard (CloudWatch) | Configured | Platform team |

### Demo Environment

| Item | Detail |
|------|--------|
| **Screen layout** | Split-screen or two browser tabs: LEFT = raw AgentCore, RIGHT = AIG Platform |
| **API client** | Postman collection OR a simple demo UI (recommended: build a thin React page) |
| **Demo data** | One sample claim document (a PDF or text blob the agent summarizes) |
| **Audience** | Leadership / architecture review — assume non-technical for narrative, show API calls for technical depth |
| **Duration** | 15–20 minutes for demo, 10 minutes Q&A |

---

## The Demo Script — 5 Scenarios, Exact Steps

---

### SCENARIO 1: The Contrast — Raw AgentCore vs. Platform

**Duration:** ~3 minutes
**What it proves:** AgentCore alone has zero governance

#### LEFT SCREEN — Raw AgentCore (no platform)

**Step 1:** Show the Claims Summarizer agent already deployed on AgentCore.

```bash
# Show it's running — invoke directly
aws bedrock-agent invoke-agent \
  --agent-id "CLAIMS-SUMMARIZER-RAW" \
  --session-id "demo-session-001" \
  --input-text "Summarize this claim: [paste sample claim text]"
```

**Step 2:** Agent responds with a summary. Works fine.

**Narration:**
> *"Here's a Claims Summarization Agent running directly on AWS AgentCore. I deploy it, it runs. No approval, no checks, no governance. It works — but nobody verified it gives correct answers, nobody checked if it can be jailbroken, and there's no record of who approved this or when."*

#### RIGHT SCREEN — AIG Platform

**Step 3:** Try to run the SAME agent through the platform (but it was never submitted).

```bash
# Try to execute — agent has no certificate
curl -X POST https://{api-gateway}/agents/claims-summarizer-v1/execute \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "claims-summarizer-v1",
    "version": "1.0.0",
    "input": "Summarize this claim: [same claim text]"
  }'
```

**Step 4:** Platform returns **BLOCKED**.

```json
{
  "status": "BLOCKED",
  "reason": "NO_CERTIFICATE_FOUND",
  "message": "Agent claims-summarizer-v1 v1.0.0 has no valid certificate. Submit the agent through the BUILD pipeline first.",
  "agent_id": "claims-summarizer-v1",
  "version": "1.0.0",
  "checked_at": "2026-06-27T14:00:01Z",
  "enforcement_component": "[R-01] Certificate Validator"
}
```

**Narration:**
> *"Same agent. Same logic. But through the AIG Platform — blocked. The Certificate Validator at R-01 looked for a signed certificate and found nothing. No certificate, no deployment. That's the rule."*

**PAUSE.** Let this land. This is the core message.

---

### SCENARIO 2: The Happy Path — Full Certification Pipeline

**Duration:** ~5 minutes
**What it proves:** The BUILD pipeline works end-to-end

#### Step 1: Submit Agent Manifest (B-01)

```bash
curl -X POST https://{api-gateway}/agents/submit \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "claims-summarizer-v1",
    "name": "Claims Summarization Agent",
    "owner": "claims-lob",
    "framework": "bedrock-agent",
    "version": "1.0.0",
    "capabilities": {
      "tools": ["summarize_claim", "extract_entities"],
      "models": ["anthropic.claude-3-sonnet"],
      "data_access": ["claims-documents-s3"]
    },
    "risk_inputs": {
      "handles_pii": true,
      "external_facing": false,
      "action_type": "read-only"
    }
  }'
```

**Expected response:**

```json
{
  "status": "SUBMITTED",
  "agent_id": "claims-summarizer-v1",
  "version": "1.0.0",
  "pipeline_execution_id": "exec-20260627-001",
  "message": "Agent manifest accepted. BUILD pipeline started.",
  "next_steps": ["capability-validation", "risk-assessment"]
}
```

**Narration:**
> *"The developer submits their agent manifest — what it does, what tools it uses, what data it touches. This kicks off the BUILD pipeline."*

#### Step 2: Show Pipeline Running (Step Functions Console)

Switch to the **Step Functions console** — show the state machine executing:

```
[ManifestIntake] ✅ Complete (0.3s)
  ├─ [CapabilityValidation] ✅ Complete (0.5s) — all capabilities on approved list
  └─ [RiskAssessment] ✅ Complete (0.2s) — Risk Tier 2 (score: 5)
[EvalFramework] ⏳ Running...
  ├─ Accuracy & Quality: testing 5 golden Q&A pairs...
  ├─ Guardrail Adherence: sending 3 injection attempts...
  └─ Capability Governance: testing 2 undeclared tool calls...
[EvalFramework] ✅ Complete (8.2s) — ALL PASS
[CertificationSvc] ✅ Complete (1.1s) — Certificate issued
[AgentRegistry] ✅ Complete (0.3s) — Agent registered as CERTIFIED
```

**Narration:**
> *"Two things happen in parallel. First, we validate capabilities — are these approved tools and models? Second, risk assessment — this agent handles PII so it scores Tier 2.*
>
> *Then the Eval Framework kicks in. We test three things: Does it give accurate answers? Can it resist prompt injection? Does it refuse to use tools it didn't declare? All pass.*
>
> *Now the Certification Service signs a certificate with KMS and stores it immutably in S3 with Object Lock. The agent is registered as CERTIFIED."*

#### Step 3: Show the Certificate (Optional Technical Deep-Dive)

```bash
# Fetch the certificate
curl https://{api-gateway}/certs/CERT-20260627-claims-summarizer-v1
```

```json
{
  "certificate_id": "CERT-20260627-claims-summarizer-v1",
  "agent_id": "claims-summarizer-v1",
  "version": "1.0.0",
  "issued_at": "2026-06-27T14:02:11Z",
  "expires_at": "2026-09-25T14:02:11Z",
  "risk_tier": 2,
  "eval_scorecard": {
    "accuracy_quality": { "score": 0.92, "threshold": 0.80, "pass": true },
    "guardrail_adherence": { "score": 1.0, "threshold": 1.0, "pass": true },
    "capability_governance": { "score": 1.0, "threshold": 1.0, "pass": true }
  },
  "capabilities": {
    "tools": ["summarize_claim", "extract_entities"],
    "models": ["anthropic.claude-3-sonnet"],
    "data_access": ["claims-documents-s3"]
  },
  "signature": "BASE64_KMS_SIGNATURE...",
  "signature_algorithm": "RSASSA_PKCS1_V1_5_SHA_256",
  "signing_key": "alias/agent-cert-signing-key"
}
```

**Narration:**
> *"This is the certificate. It's not a flag in a database — it's a cryptographically signed artifact. That signature was generated by KMS and can be independently verified. The cert is stored in S3 with Object Lock — nobody can delete or modify it. And it expires in 90 days, forcing re-certification."*

#### Step 4: NOW Execute Through the Platform

```bash
# Same execute call that was BLOCKED in Scenario 1 — now it works
curl -X POST https://{api-gateway}/agents/claims-summarizer-v1/execute \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "claims-summarizer-v1",
    "version": "1.0.0",
    "input": "Summarize this claim: [same claim text]"
  }'
```

**Expected response:**

```json
{
  "status": "EXECUTED",
  "agent_id": "claims-summarizer-v1",
  "version": "1.0.0",
  "certificate_id": "CERT-20260627-claims-summarizer-v1",
  "validation": {
    "certificate_found": true,
    "signature_valid": true,
    "not_expired": true,
    "status": "CERTIFIED",
    "validated_at": "2026-06-27T14:03:00Z"
  },
  "agent_response": {
    "summary": "The claimant reported water damage to the basement on June 15, 2026. Estimated damages total $12,450 covering flooring replacement and structural repair. No prior claims on this policy. Recommendation: approve for adjuster site visit.",
    "execution_time_ms": 2340
  }
}
```

**Narration:**
> *"Same API call. But now the Certificate Validator finds the cert, verifies the KMS signature, confirms it's not expired, confirms status is CERTIFIED — and lets the agent through. The agent executes and returns the summary."*
>
> *"Notice the response includes the full validation trail. We know exactly which certificate authorized this execution and when it was verified."*

---

### SCENARIO 3: Eval Failure — Bad Agent Gets Rejected

**Duration:** ~3 minutes
**What it proves:** The eval gate catches bad agents

#### Step 1: Submit the "Bad" Agent

```bash
curl -X POST https://{api-gateway}/agents/submit \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "claims-summarizer-bad-v1",
    "name": "Claims Summarization Agent (Bad)",
    "owner": "claims-lob",
    "framework": "bedrock-agent",
    "version": "1.0.0",
    "capabilities": {
      "tools": ["summarize_claim", "extract_entities"],
      "models": ["anthropic.claude-3-sonnet"],
      "data_access": ["claims-documents-s3"]
    },
    "risk_inputs": {
      "handles_pii": true,
      "external_facing": false,
      "action_type": "read-only"
    }
  }'
```

#### Step 2: Pipeline Runs — Eval FAILS

Show the Step Functions console:

```
[ManifestIntake] ✅ Complete
  ├─ [CapabilityValidation] ✅ Complete — capabilities valid
  └─ [RiskAssessment] ✅ Complete — Risk Tier 2
[EvalFramework] ❌ FAILED
  ├─ Accuracy & Quality: score 0.41, threshold 0.80 — FAIL
  ├─ Guardrail Adherence: score 1.0, threshold 1.0 — pass
  └─ Capability Governance: score 1.0, threshold 1.0 — pass
[CertificationSvc] ⏭️ SKIPPED — eval failed
[AgentRegistry] ⏭️ SKIPPED — no certificate
```

**Response:**

```json
{
  "status": "REJECTED",
  "agent_id": "claims-summarizer-bad-v1",
  "version": "1.0.0",
  "reason": "EVAL_FAILED",
  "eval_results": {
    "accuracy_quality": { "score": 0.41, "threshold": 0.80, "pass": false },
    "guardrail_adherence": { "score": 1.0, "threshold": 1.0, "pass": true },
    "capability_governance": { "score": 1.0, "threshold": 1.0, "pass": true }
  },
  "message": "Agent failed evaluation. No certificate issued. Fix accuracy and resubmit.",
  "certificate_issued": false
}
```

#### Step 3: Try to Execute Anyway

```bash
curl -X POST https://{api-gateway}/agents/claims-summarizer-bad-v1/execute \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "claims-summarizer-bad-v1",
    "version": "1.0.0",
    "input": "Summarize this claim: [claim text]"
  }'
```

```json
{
  "status": "BLOCKED",
  "reason": "NO_CERTIFICATE_FOUND",
  "message": "Agent claims-summarizer-bad-v1 v1.0.0 has no valid certificate.",
  "enforcement_component": "[R-01] Certificate Validator"
}
```

**Narration:**
> *"This agent has the right capabilities, passes risk scoring, but it gives wrong answers — accuracy score 0.41 against a threshold of 0.80. The Eval Framework catches it. No certificate is issued. The developer gets a clear rejection with the scores. They fix the agent, resubmit, and try again.*
>
> *And if they try to skip the process and deploy directly? Blocked. The gate doesn't care why there's no cert — it only cares that there isn't one."*

---

### SCENARIO 4: Revocation — Kill Switch

**Duration:** ~3 minutes
**What it proves:** Governance has teeth — you can revoke at any time

#### Step 1: Show the Agent is Currently Running Fine

```bash
# Execute — works
curl -X POST https://{api-gateway}/agents/claims-summarizer-v1/execute \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "claims-summarizer-v1",
    "version": "1.0.0",
    "input": "Summarize this claim: [claim text]"
  }'
```

Returns `"status": "EXECUTED"` — agent works.

#### Step 2: Revoke the Certificate

```bash
curl -X POST https://{api-gateway}/agents/claims-summarizer-v1/revoke \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "claims-summarizer-v1",
    "version": "1.0.0",
    "reason": "Security incident — potential data leakage identified",
    "revoked_by": "platform-admin@aig.com"
  }'
```

```json
{
  "status": "REVOKED",
  "agent_id": "claims-summarizer-v1",
  "version": "1.0.0",
  "certificate_id": "CERT-20260627-claims-summarizer-v1",
  "revoked_at": "2026-06-27T14:10:00Z",
  "revoked_by": "platform-admin@aig.com",
  "reason": "Security incident — potential data leakage identified",
  "message": "Certificate revoked. Agent will be blocked on next execution attempt."
}
```

#### Step 3: Try to Execute Again — Immediately Blocked

```bash
# Same call — NOW blocked
curl -X POST https://{api-gateway}/agents/claims-summarizer-v1/execute \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "claims-summarizer-v1",
    "version": "1.0.0",
    "input": "Summarize this claim: [claim text]"
  }'
```

```json
{
  "status": "BLOCKED",
  "reason": "CERTIFICATE_REVOKED",
  "message": "Agent claims-summarizer-v1 v1.0.0 certificate has been revoked.",
  "certificate_id": "CERT-20260627-claims-summarizer-v1",
  "revoked_at": "2026-06-27T14:10:00Z",
  "revoked_by": "platform-admin@aig.com",
  "revoke_reason": "Security incident — potential data leakage identified",
  "enforcement_component": "[R-01] Certificate Validator",
  "alert_triggered": true
}
```

#### Step 4: Contrast with Raw AgentCore

Switch to LEFT SCREEN — run the same agent on raw AgentCore.

```bash
# Still running on raw AgentCore — no concept of revocation
aws bedrock-agent invoke-agent \
  --agent-id "CLAIMS-SUMMARIZER-RAW" \
  --session-id "demo-session-002" \
  --input-text "Summarize this claim: [claim text]"
```

It still works. Raw AgentCore has no revocation mechanism.

**Narration:**
> *"I just revoked the certificate. One API call. The agent is immediately blocked on the platform — and the response tells you exactly who revoked it, when, and why.*
>
> *Meanwhile, on raw AgentCore? [gestures to left screen] Still running. No kill switch. If this were a real security incident, you'd be scrambling to manually tear down the agent. On the platform, it's one call and it's done."*

---

### SCENARIO 5: Expiry — Certificates Don't Last Forever

**Duration:** ~2 minutes
**What it proves:** Time-limited trust forces continuous re-certification

> **Setup note:** For the live demo, pre-create a certificate with `expires_at` set to a timestamp in the past (e.g., 5 minutes before demo time). This avoids waiting 90 days.

#### Step 1: Show an Expired Agent

```bash
# Check agent status — shows EXPIRED
curl https://{api-gateway}/agents/claims-summarizer-v0/status
```

```json
{
  "agent_id": "claims-summarizer-v0",
  "version": "0.9.0",
  "status": "EXPIRED",
  "certificate_id": "CERT-20260327-claims-summarizer-v0",
  "issued_at": "2026-03-27T10:00:00Z",
  "expired_at": "2026-06-25T10:00:00Z",
  "message": "Certificate expired. Agent must be re-certified to execute."
}
```

#### Step 2: Try to Execute

```bash
curl -X POST https://{api-gateway}/agents/claims-summarizer-v0/execute \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "claims-summarizer-v0",
    "version": "0.9.0",
    "input": "Summarize this claim: [claim text]"
  }'
```

```json
{
  "status": "BLOCKED",
  "reason": "CERTIFICATE_EXPIRED",
  "message": "Agent claims-summarizer-v0 v0.9.0 certificate expired on 2026-06-25T10:00:00Z.",
  "certificate_id": "CERT-20260327-claims-summarizer-v0",
  "expired_at": "2026-06-25T10:00:00Z",
  "action_required": "Re-submit agent through BUILD pipeline for re-certification.",
  "enforcement_component": "[R-01] Certificate Validator"
}
```

**Narration:**
> *"Certificates expire. This one was issued 90 days ago and it's now past its expiry. The agent is blocked until the owner re-submits it through the BUILD pipeline — which means it goes through risk assessment and evaluation again.*
>
> *Why? Because models change. Data changes. Threats change. An agent that was safe 90 days ago might not be safe today. Continuous re-certification is how we maintain trust over time."*

---

## Demo Flow — Timing & Transitions

```
Time    Scenario                          Key Moment
─────   ─────────────────────────────     ──────────────────────────────────
0:00    Opening — set the stage           "Two deployments of the same agent"
0:30    SCENARIO 1 — The Contrast         LEFT: runs. RIGHT: BLOCKED.     ← MONEY SHOT
3:00    SCENARIO 2 — Happy Path           Submit → Risk → Eval → Cert → Runs
8:00    SCENARIO 3 — Eval Failure         Bad agent rejected, no cert, blocked
11:00   SCENARIO 4 — Revocation           Working agent → revoke → immediately blocked
14:00   SCENARIO 5 — Expiry               Old cert expired → blocked → must re-certify
16:00   Closing — what this means         "Platform = control plane, AgentCore = engine"
18:00   Q&A
```

---

## Demo Checklist — Day Before

### Agents

- [ ] Claims Summarizer Agent deployed on raw AgentCore (no platform) — **verify it runs**
- [ ] Same agent manifest JSON ready for platform submission
- [ ] "Bad" agent variant ready (degraded prompts for low accuracy)
- [ ] Pre-expired certificate agent (`claims-summarizer-v0`) seeded in DynamoDB with past `expires_at`

### Platform

- [ ] All APIs responding (hit each endpoint with a health check)
- [ ] KMS key active and accessible
- [ ] S3 Object Lock bucket created with GOVERNANCE mode
- [ ] DynamoDB tables empty (clean state for demo — except the pre-expired cert)
- [ ] Step Functions state machine deployed and tested
- [ ] EventBridge rules active

### Demo Environment

- [ ] Postman collection imported with all 5 scenarios as saved requests
- [ ] OR demo UI deployed and tested
- [ ] Split screen configured — LEFT raw AgentCore, RIGHT platform
- [ ] Sample claim document ready (use the same one for every call)
- [ ] CloudWatch dashboard open in a background tab (optional: show metrics live)
- [ ] Screen recording running (backup if live demo fails)

### Rehearsal

- [ ] Full dry run completed at least once end-to-end
- [ ] Verified Scenario 1 contrast works (blocked vs. runs)
- [ ] Verified Scenario 2 pipeline completes in under 15 seconds
- [ ] Verified Scenario 3 bad agent fails eval (accuracy < 0.80)
- [ ] Verified Scenario 4 revocation blocks immediately
- [ ] Verified Scenario 5 expired cert blocks
- [ ] Backup plan: if any API fails, have pre-recorded responses ready

---

## Sample Claim Document (Use for All Scenarios)

```text
CLAIM REPORT — CLM-2026-04872

Policy Number: HO-7741892
Policyholder: Jane Mitchell
Date of Loss: June 15, 2026
Date Reported: June 16, 2026
Type: Homeowner — Water Damage

Description:
Policyholder reports a burst pipe in the basement causing flooding
to approximately 400 sq ft of finished basement space. Damage includes
hardwood flooring, drywall (2 walls), electrical outlets (3), and
personal property (home office equipment).

Estimated Damages:
- Flooring replacement: $6,200
- Drywall repair: $2,800
- Electrical: $1,450
- Personal property: $2,000
- Total: $12,450

Prior Claims: None on this policy
Coverage: Standard HO-3, $500 deductible
Recommendation: Approve for adjuster site visit
```

---

## Backup Plan — If Something Breaks During Demo

| Failure | Recovery |
|---------|----------|
| API Gateway down | Switch to pre-recorded terminal output (have screenshots ready) |
| Lambda timeout | Show Step Functions console with last successful run |
| KMS error | Explain the signing concept, show cert JSON from S3 directly |
| AgentCore won't respond | Focus demo on BUILD pipeline + certificate gate (R-01 is the star anyway) |
| Everything breaks | Use the Mermaid diagrams + pre-recorded video (always have a recording) |

**Golden rule: The demo is about the PRINCIPLE, not the plumbing. If the live system fails, the narrative still works with pre-captured output.**

---

## Talking Points for Q&A

| Question | Answer |
|----------|--------|
| "How long does certification take?" | *"For this POC, the full pipeline runs in under 15 seconds. In production, the eval framework would run more comprehensive tests — maybe 2-5 minutes depending on the agent's risk tier."* |
| "What if we need to deploy urgently?" | *"The platform supports emergency fast-track for Tier 1 (low risk) agents with reduced eval dimensions. But Tier 3 agents always get the full gate. Urgency doesn't override safety."* |
| "Can the developer see why they failed?" | *"Yes. The rejection response includes exact scores per dimension, the threshold they missed, and which dimension failed. It's actionable — they know what to fix."* |
| "How is this different from just using IAM policies?" | *"IAM controls WHO can deploy. The certificate controls WHAT is deployable. An IAM role might let you deploy any agent — the certificate ensures only evaluated, approved agents actually run."* |
| "What about agent updates?" | *"Every new version requires a new certificate. Version 1.0.0 cert doesn't cover 1.1.0. This prevents someone from certifying a clean agent and then swapping in different logic."* |
| "What stops someone from bypassing the platform?" | *"In production, the AgentCore execution role would only be assumable through the platform's R-01 validator. Direct access to AgentCore gets locked down via IAM. For the POC, we show the contrast side-by-side to make the point."* |
| "Why 90-day expiry?" | *"Models drift, threats evolve, compliance requirements change. 90 days forces periodic re-evaluation. The interval is configurable — some high-risk agents might need 30-day recertification."* |
| "What's next after this POC?" | *"Runtime capability enforcement — R-06. Right now we certify what an agent SAYS it will do. Next, we enforce what it ACTUALLY does at runtime. If it tries to call a tool it didn't declare, we block the call in real-time."* |

---

## Narrative Arc — Speaker Notes

### Opening (30 seconds)
> *"I want to show you one thing today. One principle that separates a managed AI platform from a science project. And I'm going to show it to you side by side."*

### The Contrast — Scenario 1 (2.5 minutes)
> *"LEFT: raw AgentCore. I deploy an agent, it runs. No questions. RIGHT: the AIG Platform. Same agent — blocked. Why? No certificate. That's the entire thesis."*

### The Pipeline — Scenario 2 (5 minutes)
> *"Now let me show you how an agent earns a certificate..."*
> Walk through submit → risk → eval → cert → execute.
> Pause on the certificate JSON — *"This is a real cryptographic artifact, not a checkbox."*

### The Teeth — Scenarios 3, 4, 5 (6 minutes)
> *"The gate has teeth in three directions:"*
> - *"It catches bad agents BEFORE they deploy."* (Scenario 3)
> - *"It kills running agents AFTER you revoke."* (Scenario 4)
> - *"It forces re-certification OVER TIME."* (Scenario 5)

### The Close (1 minute)
> *"AgentCore is an execution engine. It's good at running agents. But it has no opinion about WHICH agents should run. The platform is the control plane. It decides. And the certificate is the proof.*
>
> *No certificate, no deployment. That's the rule.*
>
> *Next step: we add runtime capability enforcement — not just 'did you earn a license,' but 'are you driving in your lane right now.' But that's Phase 2. Today, the gate works."*
