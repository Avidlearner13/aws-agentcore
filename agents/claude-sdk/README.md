# Claude SDK Agent — Coverage & Adjudication

Insurance **coverage-determination** agent built with the **Claude Agent SDK**
(`claude_agent_sdk`), running Claude on **Amazon Bedrock**, packaged for **AgentCore Runtime**.
It is the **Coverage** specialist in the claims-adjudication platform: given a structured
`claim_record` (output of the Intake agent) plus the governing policy text, it determines
which coverages/limits apply, which exclusions trigger, the deductible, the `eligible_amount`,
and a cited rationale — returning the `coverage_determination` object (see
`../../shared/contracts.md` §2). The Risk specialist lives under `agents/langchain`, Intake
under `agents/gcp-adk`.

## Files
- `coverage.py` — core logic: `async def assess_coverage(claim_record, policy_text, *, model=None)`.
  Streams a `query()` over Claude and returns the common envelope
  `{framework, model, result, raw, meta}`, where `result` is the parsed `coverage_determination`.
- `app.py` — AgentCore Runtime entrypoint (`BedrockAgentCoreApp` → `/invocations` + `/ping`).
- `Dockerfile` — linux/arm64, Python 3.12 (AgentCore requirement).
- `samples/` — sample policy documents for local testing.

## Run locally
Requires the venv (`.venv`) and AWS creds with Bedrock access (profile `agentcore`).

```powershell
$env:AWS_PROFILE = "agentcore"; $env:AWS_REGION = "us-east-1"; $env:CLAUDE_CODE_USE_BEDROCK = "1"
& .venv\Scripts\python.exe app.py            # serves the AgentCore contract on :8080 (PORT overrides)
```
Then POST the Coverage payload to `http://localhost:8080/invocations`:
```json
{"claim_record": { /* claim_record per contracts.md §1 */ }, "policy_text": "<contents of samples/policy_a.txt>"}
```

## Deploy to AgentCore Runtime (later)
Build is done in the cloud (CodeBuild → ECR); no local Docker needed:
```powershell
& ..\..\control-plane\.venv\Scripts\agentcore.exe configure --entrypoint app.py
& ..\..\control-plane\.venv\Scripts\agentcore.exe launch
```

## Notes
- Model defaults to a Claude Sonnet Bedrock inference profile; override via the `model`
  payload field or the `CLAUDE_MODEL` env var.
- `setting_sources=[]` keeps the container from loading any local `CLAUDE.md`/settings, and
  `allowed_tools=[]` keeps the run to pure reasoning over the provided text.
- `coverage_determination` numeric fields (`deductible_applied`, `eligible_amount`) are
  emitted as numbers; the system prompt enforces this.
