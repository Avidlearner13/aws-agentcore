# Agent-Core — Shared Contracts (Claims Adjudication)

Source of truth for the JSON objects passed between agents. Each agent embeds its own copy of the
relevant schema (the agents run in isolated venvs and do not import across folders). All agents return
the common **envelope**; the role-specific payload goes in the envelope's `result` field.

## Common envelope (every agent's return value)
```json
{
  "framework": "gcp-adk | claude-agent-sdk | langchain | orchestrator-claude",
  "model": "us.anthropic.claude-sonnet-4-6",
  "result": { /* role-specific object, see below */ },
  "raw": "the model's raw text output",
  "meta": { "duration_ms": 0, "usage": { "input_tokens": 0, "output_tokens": 0 }, "cost_usd": null }
}
```

## 1. `claim_record` — OUTPUT of Intake (ADK); INPUT to Coverage and Risk
```json
{
  "claim_id": "string",
  "policy_number": "string",
  "claimant": { "name": "string", "is_policyholder": true, "contact": "string|null" },
  "loss": {
    "date_of_loss": "YYYY-MM-DD | 'not stated'",
    "reported_date": "YYYY-MM-DD | 'not stated'",
    "peril_category": "water | fire | theft | wind | liability | other",
    "cause": "short phrase, e.g. 'burst pipe under kitchen sink'",
    "description": "1-3 sentence narrative",
    "location": "string"
  },
  "line_items": [
    { "description": "string", "category": "dwelling|contents|other_structures|mitigation|loss_of_use|liability",
      "claimed_amount": 0 }
  ],
  "total_claimed": 0,
  "attachments": [ { "type": "form|receipt|estimate|photo|policy", "name": "string", "summary": "string" } ],
  "extraction_notes": "anything ambiguous or missing"
}
```

## 2. `coverage_determination` — OUTPUT of Coverage (Claude SDK)
Inputs: `claim_record` + the policy text.
```json
{
  "coverage_status": "covered | partially_covered | denied | needs_review",
  "applicable_coverages": [
    { "name": "string", "limit": "string", "applies": true, "rationale": "string" }
  ],
  "exclusions_triggered": [ { "description": "string", "impact": "string" } ],
  "deductible_applied": 0,
  "eligible_amount": 0,
  "rationale": "plain-language coverage explanation",
  "policy_citations": [ "section / clause references" ]
}
```

## 3. `risk_assessment` — OUTPUT of Risk/Fraud/Compliance (LangChain)
Inputs: `claim_record` (+ optional claimant/claim history).
```json
{
  "fraud_score": 0,
  "risk_level": "low | medium | high",
  "flags": [ { "signal": "string", "severity": "low|medium|high", "explanation": "string" } ],
  "compliance": { "concerns": ["string"], "cited_rules": [ { "rule": "string", "source": "string" } ] },
  "recommended_action": "string"
}
```

## 4. `adjudication_package` — OUTPUT of the Orchestrator (Phase 2)
Synthesized from the three specialist outputs.
```json
{
  "claim_id": "string",
  "decision": "approve | deny | partial | refer_to_human",
  "recommended_payout": 0,
  "summary": "string",
  "rationale": "string",
  "customer_letter": "drafted response text",
  "approval_required": true,
  "steps": [
    { "agent": "intake|coverage|risk", "framework": "string", "status": "ok|error", "duration_ms": 0 }
  ]
}
```

## AgentCore payload contract (all agents' `app.py` `/invocations`)
Each agent accepts a JSON payload and returns the envelope. Field names per role:
- **Intake**: `{ "fnol_text": "...", "policy_text": "...", "model"?: "..." }`
- **Coverage**: `{ "claim_record": {...}, "policy_text": "...", "model"?: "..." }`
- **Risk**: `{ "claim_record": {...}, "history"?: "...", "model"?: "..." }`
- **Orchestrator**: `{ "fnol_text": "...", "policy_text": "...", "orchestrator"?: "claude", "model"?: "..." }`

## Local ports (dev)
| Service | Port |
|---|---|
| Control-plane UI/API | 8770 |
| Coverage agent (Claude SDK) | 8771 |
| Intake agent (GCP ADK) | 8772 |
| Risk agent (LangChain) | 8773 |
| Orchestrator (Claude SDK) | 8774 |
