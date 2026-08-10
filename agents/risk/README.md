# LangChain Risk / Fraud / Compliance agent

LangChain implementation of the **Risk, Fraud & Compliance** specialist in the
claims-adjudication pipeline (Intake → Coverage → Risk). It takes a `claim_record`
(`shared/contracts.md` §1) plus optional claimant/claim `history` and returns a
`risk_assessment` (§3) inside the shared envelope. Runs Claude on Bedrock via
`langchain_aws.ChatBedrockConverse` (Bedrock Converse API).

## Files
- `risk.py` — `async def assess_risk(claim_record, history="", *, model=None) -> dict`.
  Returns the common envelope `{"framework": "langchain", "model", "result", "raw", "meta"}`,
  where `result` is the `risk_assessment` (`fraud_score`, `risk_level`, `flags`,
  `compliance.cited_rules`, `recommended_action`).
- `app.py` — AgentCore Runtime entrypoint (`BedrockAgentCoreApp`, `@app.entrypoint`).
  Payload contract: `{ "claim_record": {...}, "history"?: "...", "model"?: "..." }`.
  Runs on `PORT` (default 8080).
- `requirements.txt` — langchain, langchain-core, langgraph, langchain-aws,
  langchain-community, boto3, bedrock-agentcore.

## Retrieval (light RAG)
The knowledge base is a small set of Markdown guideline files under `samples/kb`:
- `water_damage_coverage.md` (G-12 — water damage coverage)
- `fraud_red_flags.md` (G-30 — fraud red flags / scoring)
- `regulatory_claims_handling.md` (R-05 — Illinois regulatory handling)

`risk.py` loads these at call time and injects the relevant snippets into the prompt.
Selection is naive keyword/peril matching: the fraud and regulatory guidelines are
**always** included (they apply to every claim), plus any file whose name matches the
claim's `peril_category` / cause / description keywords (e.g. a `water` peril pulls in
G-12). If selection is too narrow it falls back to all KB files. The model is instructed
to cite guideline IDs/sources drawn ONLY from the injected excerpts.

The KB directory is overridable via env `KB_DIR` (default `C:\agent-core\samples\kb`).

## Environment
- Model: Bedrock `us.anthropic.claude-sonnet-4-6` (cross-region inference profile, us-east-1).
  Override per-invocation (`model` arg) or per-deployment (env `CLAUDE_MODEL`).
- AWS creds: `AWS_PROFILE=agentcore`, `AWS_REGION=us-east-1`. `ChatBedrockConverse`
  picks up the profile/region from the environment via boto3.

## Run / test (PowerShell)
```powershell
$env:AWS_PROFILE = "agentcore"
$env:AWS_REGION  = "us-east-1"
$venv = ".\.venv\Scripts\python.exe"

# Smoke test assess_risk against a sample claim_record:
& $venv -c @'
import asyncio, json
from risk import assess_risk
claim = {"claim_id": "CLM-2026-44817", "loss": {"peril_category": "water",
         "cause": "burst supply pipe"}, "total_claimed": 16700}
r = asyncio.run(assess_risk(claim))
print(r["framework"], r["model"], r["meta"])
print(json.dumps(r["result"], indent=2))
'@

# Run the AgentCore server locally (serves /invocations + /ping):
& $venv app.py
```

## Notes
- `assess_risk` uses `await llm.ainvoke([SystemMessage, HumanMessage])`.
- The JSON parser strips ``` code fences and falls back to a regex object match.
- `meta` is populated from `response.usage_metadata` (token counts) and
  `response.response_metadata` (stop reason, Bedrock latency), guarded with getattr, plus
  `kb_dir` / `kb_sources` so you can see which guidelines were retrieved.
