"""Coverage & Adjudication agent (Phase-1 role: Coverage).

Implemented with the Claude Agent SDK (``claude_agent_sdk``), running Claude on Amazon
Bedrock. Given a structured ``claim_record`` (the output of the Intake agent) plus the
governing policy text, this agent determines coverage: which coverages/limits apply, which
exclusions trigger, the deductible, the eligible amount, and a rationale with policy
citations. It returns the ``coverage_determination`` object (see shared/contracts.md §2)
wrapped in the common envelope shared across all framework agents.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TextBlock,
    query,
)

# Claude model on Bedrock. ``us.`` prefix = cross-region inference profile in us-east-1.
# Override per-invocation (payload "model") or per-deployment (env CLAUDE_MODEL).
# sonnet-4-6 is enabled on this account (Anthropic use-case form accepted 2026-06-22) and
# verified end-to-end via the Claude Agent SDK + AgentCore entrypoint path.
DEFAULT_MODEL = os.environ.get("CLAUDE_MODEL", "us.anthropic.claude-sonnet-4-6")

SYSTEM_PROMPT = """You are a senior insurance coverage adjuster for a homeowners (HO-3) claims-adjudication platform.
You will be given (1) a structured claim_record and (2) the full text of the governing policy.
Determine coverage precisely and faithfully to the policy and the claim facts.

Reason through, in order:
1. Identify the peril and cause of loss, and which policy coverage(s) (e.g. Dwelling A, Other Structures B,
   Personal Property C, Loss of Use D, liability, or endorsements) could respond.
2. Check the Perils Insured Against and the Exclusions. An HO-3 covers the dwelling on an open-perils basis
   except as excluded. A SUDDEN AND ACCIDENTAL internal plumbing failure (e.g. a burst supply pipe) is a
   COVERED water peril. Flood / surface water and sewer/drain backup are different perils: only cite the flood
   exclusion or a water-backup/sump endorsement if the facts actually involve flood, surface water, or backup.
3. Apply the correct deductible. Use the All Other Perils deductible unless a specific peril deductible
   (wind/hail, hurricane) applies to this loss.
4. Compute eligible_amount: sum the covered line items, subtract the applicable deductible (never below 0),
   and respect coverage limits. Mitigation/water-extraction costs are reasonable covered expenses under the
   duty to protect the property.

Respond with ONLY a single JSON object (no prose, no code fences) matching this schema:
{
  "coverage_status": "covered | partially_covered | denied | needs_review",
  "applicable_coverages": [
    {"name": "...", "limit": "limit/term from the policy", "applies": true, "rationale": "..."}
  ],
  "exclusions_triggered": [ {"description": "...", "impact": "..."} ],
  "deductible_applied": 0,
  "eligible_amount": 0,
  "rationale": "plain-language coverage explanation",
  "policy_citations": ["section / clause references from the policy text"]
}

Rules:
- deductible_applied and eligible_amount MUST be numbers (not strings).
- Be faithful to the documents; do not invent limits or figures. Cite actual policy sections.
- If the policy or claim is genuinely ambiguous or key facts are missing, use "needs_review" and explain.
- If no listed exclusion applies, return an empty exclusions_triggered array.
"""


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


def _build_prompt(claim_record: dict[str, Any], policy_text: str) -> str:
    return (
        "Determine coverage for this claim against the policy below and return the JSON "
        "coverage_determination object.\n\n"
        f"=== CLAIM RECORD (JSON) ===\n{json.dumps(claim_record, indent=2)}\n\n"
        f"=== POLICY TEXT ===\n{policy_text}\n"
    )


async def assess_coverage(
    claim_record: dict[str, Any], policy_text: str, *, model: str | None = None,
    system_prompt: str | None = None
) -> dict[str, Any]:
    """Run the coverage determination and return the common result envelope.

    The envelope shape is shared across all framework agents so the control-plane can
    compare/orchestrate them directly: framework, model, result (parsed
    coverage_determination), raw, and meta (cost/usage/duration).

    ``system_prompt`` overrides the built-in adjuster prompt. Used by the governance layer's
    certification eval to run a deliberately *degraded* variant of this same live agent (the demo
    "bad" agent), so an eval failure is real rather than simulated. Defaults to the strong prompt.
    """
    options = ClaudeAgentOptions(
        system_prompt=system_prompt or SYSTEM_PROMPT,
        model=model or DEFAULT_MODEL,
        allowed_tools=[],          # pure reasoning over provided text; no tools needed
        setting_sources=[],        # do not load local CLAUDE.md / settings in the container
    )

    text_chunks: list[str] = []
    meta: dict[str, Any] = {}
    async for message in query(
        prompt=_build_prompt(claim_record, policy_text), options=options
    ):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    text_chunks.append(block.text)
        elif isinstance(message, ResultMessage):
            # Field names guarded with getattr so a minor SDK bump can't break us.
            meta = {
                "cost_usd": getattr(message, "total_cost_usd", None),
                "duration_ms": getattr(message, "duration_ms", None),
                "num_turns": getattr(message, "num_turns", None),
                "is_error": getattr(message, "is_error", None),
                "usage": getattr(message, "usage", None),
            }

    raw = "".join(text_chunks).strip()
    return {
        "framework": "claude-agent-sdk",
        "model": options.model,
        "result": _extract_json(raw),
        "raw": raw,
        "meta": meta,
    }
