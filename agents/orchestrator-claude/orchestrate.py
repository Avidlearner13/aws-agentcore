"""Phase-2 orchestrator (Claude Agent SDK supervisor) for claims adjudication.

Runs the cross-framework pipeline toward the common goal — adjudicate a claim:

    Intake (GCP ADK)  ->  Coverage (Claude SDK)  ->  Risk (LangChain)  ->  synthesize decision

The three specialists are reached over HTTP at their AgentCore `/invocations` endpoints
("agents as tools" — the local stand-in for the MCP agent registry). The orchestrator then
uses Claude to synthesize an `adjudication_package` (see shared/contracts.md §4) and applies a
human-approval gate on any payout. The orchestrator is itself just another agent, so the
conducting framework is swappable (see PLAN.md M-E).
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
import uuid
from typing import Any

import boto3
import httpx
from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TextBlock,
    query,
)

DEFAULT_MODEL = os.environ.get("CLAUDE_MODEL", "us.anthropic.claude-sonnet-4-6")
REGION = os.environ.get("AWS_REGION", "us-east-1")

# Specialist registry. Two transports:
#  - On AgentCore: set <NAME>_ARN env → call via the AgentCore data plane (InvokeAgentRuntime).
#  - Locally: fall back to the localhost /invocations HTTP endpoints.
LOCAL_URLS = {
    "intake": os.environ.get("INTAKE_URL", "http://127.0.0.1:8772/invocations"),
    "coverage": os.environ.get("COVERAGE_URL", "http://127.0.0.1:8771/invocations"),
    "risk": os.environ.get("RISK_URL", "http://127.0.0.1:8773/invocations"),
}
AGENT_ARNS = {
    "intake": os.environ.get("INTAKE_ARN"),
    "coverage": os.environ.get("COVERAGE_ARN"),
    "risk": os.environ.get("RISK_ARN"),
}

_ac_client = None


def _agentcore():
    global _ac_client
    if _ac_client is None:
        _ac_client = boto3.client("bedrock-agentcore", region_name=REGION)
    return _ac_client

SYNTH_PROMPT = """You are the senior claims adjudicator. You are given three specialist findings
about one insurance claim: an extracted claim record, a coverage determination, and a risk/fraud
assessment. Decide the outcome and draft the customer response.

Respond with ONLY a single JSON object (no prose, no code fences) matching this schema:
{
  "claim_id": "string",
  "decision": "approve | deny | partial | refer_to_human",
  "recommended_payout": number,
  "summary": "2-3 sentence summary of the claim and outcome",
  "rationale": "why this decision, referencing coverage + risk",
  "customer_letter": "a short, empathetic letter to the claimant stating the outcome and next steps",
  "approval_required": true
}
Decision rules:
- If coverage_status is 'denied' -> decision 'deny', recommended_payout 0.
- If risk_level is 'high' (or fraud_score >= 70) -> decision 'refer_to_human'.
- If coverage_status is 'covered' and risk is acceptable -> 'approve', recommended_payout = eligible_amount.
- If 'partially_covered' -> 'partial', recommended_payout = eligible_amount.
- Any non-zero payout sets approval_required = true (a human must authorize disbursement).
"""


def _extract_json(text: str) -> dict[str, Any] | None:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.DOTALL)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                return None
    return None


async def _call_specialist(name: str, payload: dict) -> tuple[dict, dict]:
    """Call a specialist by name — via AgentCore (if its ARN is set) or local HTTP."""
    started = time.perf_counter()
    arn = AGENT_ARNS.get(name)
    step: dict[str, Any] = {"agent": name, "status": "ok", "via": "agentcore" if arn else "local-http"}
    try:
        if arn:
            def _invoke() -> bytes:
                r = _agentcore().invoke_agent_runtime(
                    agentRuntimeArn=arn, qualifier="DEFAULT",
                    runtimeSessionId=uuid.uuid4().hex + uuid.uuid4().hex,
                    contentType="application/json", accept="application/json",
                    payload=json.dumps(payload).encode("utf-8"),
                )
                return r["response"].read()
            env = json.loads(await asyncio.to_thread(_invoke))
        else:
            async with httpx.AsyncClient(timeout=300) as client:
                resp = await client.post(LOCAL_URLS[name], json=payload)
                resp.raise_for_status()
                env = resp.json()
        step["framework"] = env.get("framework")
    except Exception as e:  # noqa: BLE001
        env = {"error": str(e)}
        step["status"] = "error"
        step["error"] = str(e)
    step["duration_ms"] = round((time.perf_counter() - started) * 1000)
    return env, step


async def _synthesize(claim_record, coverage, risk, *, model: str) -> tuple[dict | None, str, dict]:
    payload = {
        "claim_record": claim_record,
        "coverage_determination": coverage,
        "risk_assessment": risk,
    }
    prompt = SYNTH_PROMPT + "\n\nSPECIALIST FINDINGS (JSON):\n" + json.dumps(payload, indent=2)
    options = ClaudeAgentOptions(
        system_prompt="You are a precise insurance claims adjudicator. Output only JSON.",
        model=model, allowed_tools=[], setting_sources=[],
    )
    chunks: list[str] = []
    meta: dict[str, Any] = {}
    async for message in query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    chunks.append(block.text)
        elif isinstance(message, ResultMessage):
            meta = {"cost_usd": getattr(message, "total_cost_usd", None),
                    "duration_ms": getattr(message, "duration_ms", None),
                    "usage": getattr(message, "usage", None)}
    raw = "".join(chunks).strip()
    return _extract_json(raw), raw, meta


def _assemble(claim_record, coverage, risk, *, package, raw, synth_meta,
              steps: list[dict], started: float, model: str) -> dict[str, Any]:
    """Build the common envelope from synthesized parts (shared by full + synth-only paths)."""
    if package is None:
        package = {"decision": "refer_to_human", "recommended_payout": 0,
                   "summary": "Synthesis failed to parse.", "approval_required": True}
    package["claim_id"] = (claim_record or {}).get("claim_id", package.get("claim_id"))
    # any disbursement requires a human gate (tool-auth policy stand-in)
    if package.get("recommended_payout", 0):
        package["approval_required"] = True
    package["steps"] = [{"agent": s["agent"], "framework": s.get("framework"),
                         "status": s["status"], "duration_ms": s["duration_ms"]} for s in steps]
    return {
        "framework": "orchestrator-claude",
        "model": model,
        "result": package,
        "raw": raw,
        "meta": {**synth_meta, "total_duration_ms": round((time.perf_counter() - started) * 1000),
                 "specialist_outputs": {"claim_record": claim_record, "coverage": coverage, "risk": risk}},
    }


async def synthesize_only(claim_record, coverage, risk, *, steps: list[dict] | None = None,
                          model: str | None = None) -> dict[str, Any]:
    """Synthesize a decision from already-computed specialist outputs (no specialist calls).

    Used when the caller (e.g. the control-plane) drives Intake → Coverage → Risk itself for
    live per-step progress, then hands the three findings here for the final adjudication.
    """
    model = model or DEFAULT_MODEL
    started = time.perf_counter()
    package, raw, synth_meta = await _synthesize(claim_record, coverage, risk, model=model)
    return _assemble(claim_record, coverage, risk, package=package, raw=raw, synth_meta=synth_meta,
                     steps=steps or [], started=started, model=model)


async def adjudicate(fnol_text: str, policy_text: str, *, model: str | None = None) -> dict[str, Any]:
    """Orchestrate the three specialists and synthesize an adjudication package."""
    model = model or DEFAULT_MODEL
    steps: list[dict] = []
    started = time.perf_counter()

    intake_env, s = await _call_specialist("intake", {"fnol_text": fnol_text, "policy_text": policy_text})
    steps.append(s)
    claim_record = (intake_env or {}).get("result")

    cov_env, s = await _call_specialist("coverage", {"claim_record": claim_record, "policy_text": policy_text})
    steps.append(s)
    coverage = (cov_env or {}).get("result")

    risk_env, s = await _call_specialist("risk", {"claim_record": claim_record})
    steps.append(s)
    risk = (risk_env or {}).get("result")

    package, raw, synth_meta = await _synthesize(claim_record, coverage, risk, model=model)
    return _assemble(claim_record, coverage, risk, package=package, raw=raw, synth_meta=synth_meta,
                     steps=steps, started=started, model=model)
