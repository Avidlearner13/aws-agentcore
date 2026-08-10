# GCP ADK Intake agent — Intake & Document Intelligence

Extracts a structured `claim_record` from a First Notice of Loss (FNOL) bundle (claim form +
attachments) plus the policy text. This is the **GCP Agent Development Kit (`google-adk`)**
specialist in the claims-adjudication platform. It does **extraction and normalization only**
— it makes no coverage or fraud judgment (those are the Coverage and Risk agents).

Output is the shared **envelope** (`{framework, model, result, raw, meta}`), with the
role-specific `claim_record` (contracts.md §1) in `result`.

## How it reaches the model

ADK has no native Bedrock provider, so it reaches Claude on Amazon Bedrock through
**LiteLLM**:

```python
from google.adk.models.lite_llm import LiteLlm
LiteLlm(model="bedrock/us.anthropic.claude-sonnet-4-6")
```

LiteLLM uses `boto3` under the hood, so AWS credentials/region resolve from the standard
chain (local: `AWS_PROFILE`/`AWS_REGION`; container: the AgentCore execution role).

## ADK usage pattern

`extract_claim_record` builds an `LlmAgent(model=LiteLlm(...), instruction=SYSTEM_PROMPT)`,
wraps it in an `InMemoryRunner` (which provides in-memory session/artifact services), creates
a one-shot session, and drives it with `runner.run_async(...)`, collecting text only from the
final response event (`event.is_final_response()`, skipping partials) and summing
`event.usage_metadata` token counts into `meta`. The raw text is parsed (code fences stripped)
into the `claim_record` placed in the envelope's `result`.

## Files

- `intake.py` — `async def extract_claim_record(fnol_text, policy_text="", *, model=None) -> dict`
- `app.py` — AgentCore entrypoint (`BedrockAgentCoreApp`); payload `fnol_text`, `policy_text`, optional `model`. Port is configurable via `PORT` (default 8080; dev port 8772 per contracts.md).
- `Dockerfile` — linux/arm64, python:3.12-slim
- `requirements.txt` — google-adk, litellm, boto3, bedrock-agentcore

## Payload contract (AgentCore `/invocations`)

```json
{ "fnol_text": "<FNOL bundle text>", "policy_text": "<policy text>", "model": "<optional bedrock id>" }
```

Returns the common envelope; the extracted `claim_record` is in `result`.

## Run / test

```powershell
$env:AWS_PROFILE="agentcore"; $env:AWS_REGION="us-east-1"
$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")

# Local AgentCore server (HTTP /invocations + /ping). Override port with $env:PORT.
$env:PORT="8772"; .\.venv\Scripts\python.exe app.py

# Direct smoke test
.\.venv\Scripts\python.exe -c "import asyncio, pathlib; from intake import extract_claim_record; fnol=pathlib.Path(r'..\..\samples\claims\fnol_text.txt').read_text(); pol=pathlib.Path(r'..\..\samples\policy_a.txt').read_text(); print(asyncio.run(extract_claim_record(fnol, pol))['result'])"
```

## Notes / gotchas

- `LiteLlm` requires `litellm` installed (`pip install litellm`, or `google-adk[extensions]`);
  it is **not** pulled in by base `google-adk`.
- LiteLLM needs the `bedrock/` provider prefix on the model id; `extract_claim_record` adds it
  automatically if absent.
- The model must return numbers (not currency strings) for `claimed_amount`/`total_claimed`;
  the system prompt enforces this. The parser strips ```` ``` ```` code fences and falls back
  to the first `{...}` block if the model wraps the JSON.
- On Windows + older Python you may see a benign `Fatal error on SSL transport` /
  `Event loop is closed` traceback printed after the run completes — it comes from aiohttp's
  connector closing during loop teardown, not from this code. A trailing `await
  asyncio.sleep(0)` mitigates it. It does not occur in the Linux/arm64 container.
