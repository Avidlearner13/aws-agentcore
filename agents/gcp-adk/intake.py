"""Intake & Document Intelligence for the claims-adjudication platform.

Implemented with the **GCP Agent Development Kit** (``google-adk``). ADK reaches Claude on
Amazon Bedrock through LiteLLM (``LiteLlm`` model wrapper -> ``bedrock/...`` model string).
This mirrors the Claude Agent SDK and LangChain implementations so the three frameworks can
be compared apples-to-apples on AgentCore (see PLAN.md).

The Intake agent takes the FNOL bundle text (claim form + attachments) plus the policy text
and EXTRACTS a structured ``claim_record`` (contracts.md §1). It does extraction and
normalization only -- it makes NO coverage or fraud judgment. The role-specific
``claim_record`` is returned inside the common envelope's ``result`` field.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
import uuid
from typing import Any

from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.runners import InMemoryRunner
from google.genai import types

# Bedrock model — Amazon Nova Pro (AWS-native, cheaper than Claude), reached via LiteLLM.
# ``us.`` prefix = cross-region inference profile in us-east-1. LiteLLM expects a
# ``bedrock/`` provider prefix on the model id (added by ``_litellm_model_id``).
# Override per-invocation (``model`` arg / payload "model") or per-deployment (env CLAUDE_MODEL).
DEFAULT_MODEL = os.environ.get("CLAUDE_MODEL", "us.amazon.nova-pro-v1:0")

APP_NAME = "intake-gcp-adk"

SYSTEM_PROMPT = """You are an insurance claims intake specialist performing document
intelligence. You will be given a First Notice of Loss (FNOL) bundle -- the claim form plus
any attachment text (receipts, repair estimates, photos described in text) -- and, optionally,
the policy text. Your job is EXTRACTION and NORMALIZATION only. Do NOT decide coverage, do
NOT judge fraud, do NOT compute deductibles or payouts -- only structure what the documents say.

Respond with ONLY a single JSON object (no prose, no code fences) matching this exact schema:
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

Rules:
- Be faithful to the documents; never invent figures, names, or dates. If something is not
  stated, use 'not stated' for string fields (or null for contact).
- ``peril_category`` MUST be one of the enumerated values; map the stated cause to the closest
  category (e.g. burst pipe / plumbing discharge -> "water").
- ``claimed_amount`` and ``total_claimed`` are NUMBERS (no currency symbols or commas).
- ``line_items`` should reflect the itemized claim. De-duplicate items that appear identically
  in both the form and an attachment estimate -- list each distinct item once.
- ``is_policyholder``: true if the claimant is the named insured on the policy/form.
- Note anything ambiguous, conflicting, or missing in ``extraction_notes``.
"""


def _litellm_model_id(model: str) -> str:
    """LiteLLM needs a provider prefix. Accept either a bare Bedrock id or a prefixed one."""
    return model if model.startswith("bedrock/") else f"bedrock/{model}"


def _build_prompt(fnol_text: str, policy_text: str) -> str:
    parts = [
        "Extract the claim_record JSON from the following FNOL bundle.\n",
        f"=== FNOL BUNDLE (claim form + attachments) ===\n{fnol_text}\n",
    ]
    if policy_text.strip():
        parts.append(
            "\n=== POLICY (context only -- use for policy_number / named insured "
            "confirmation; do NOT judge coverage) ===\n"
            f"{policy_text}\n"
        )
    return "".join(parts)


def _extract_json(text: str) -> dict[str, Any] | None:
    """Best-effort parse: strip code fences, then load the first JSON object found."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.DOTALL)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                return None
    return None


def _accumulate_usage(meta: dict[str, Any], usage: Any) -> None:
    """Sum token counts across events into ``meta['usage']`` (guarded for shape drift)."""
    if usage is None:
        return
    bucket = meta.setdefault("usage", {})
    for src_attr, dst_key in (
        ("prompt_token_count", "input_tokens"),
        ("candidates_token_count", "output_tokens"),
        ("total_token_count", "total_tokens"),
    ):
        val = getattr(usage, src_attr, None)
        if val is not None:
            bucket[dst_key] = bucket.get(dst_key, 0) + val


async def extract_claim_record(
    fnol_text: str, policy_text: str = "", *, model: str | None = None
) -> dict[str, Any]:
    """Extract a structured ``claim_record`` from an FNOL bundle and return the envelope.

    The envelope shape is shared across all three framework agents so the control-plane can
    compare them directly: framework, model, result (the parsed claim_record), raw, and meta
    (duration/usage). Coverage/fraud judgment is out of scope -- this is extraction only.
    """
    bedrock_model = model or DEFAULT_MODEL

    agent = LlmAgent(
        name="claim_intake",
        model=LiteLlm(model=_litellm_model_id(bedrock_model)),
        instruction=SYSTEM_PROMPT,
    )

    # ADK requires a Runner + session. InMemoryRunner wires up in-memory session/artifact
    # services for us; we just create one ephemeral session per invocation.
    runner = InMemoryRunner(agent=agent, app_name=APP_NAME)
    user_id = "intake-user"
    session_id = uuid.uuid4().hex
    await runner.session_service.create_session(
        app_name=APP_NAME, user_id=user_id, session_id=session_id
    )

    new_message = types.Content(
        role="user",
        parts=[types.Part(text=_build_prompt(fnol_text, policy_text))],
    )

    text_chunks: list[str] = []
    meta: dict[str, Any] = {}
    start = time.perf_counter()
    try:
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=new_message,
        ):
            _accumulate_usage(meta, getattr(event, "usage_metadata", None))
            if getattr(event, "error_message", None):
                meta["error_message"] = event.error_message
                meta["error_code"] = getattr(event, "error_code", None)
            # Only collect final (non-partial) assistant text so we don't double-count
            # streamed deltas.
            content = getattr(event, "content", None)
            if content and getattr(content, "parts", None) and not getattr(event, "partial", False):
                if event.is_final_response():
                    for part in content.parts:
                        if getattr(part, "text", None):
                            text_chunks.append(part.text)
    finally:
        meta["duration_ms"] = round((time.perf_counter() - start) * 1000, 1)
        close = getattr(runner, "close", None)
        if close is not None:
            try:
                await close()
            except Exception:  # noqa: BLE001 - cleanup must not mask a real result
                pass
        # LiteLLM holds an aiohttp session open; yield once so its connector can finish
        # closing before the event loop tears down (avoids benign Windows SSL-transport
        # shutdown warnings; harmless no-op on Linux).
        await asyncio.sleep(0)

    raw = "".join(text_chunks).strip()
    return {
        "framework": "gcp-adk",
        "model": bedrock_model,
        "result": _extract_json(raw),
        "raw": raw,
        "meta": meta,
    }
