"""AgentCore Runtime entrypoint for the Claude SDK claims-adjudication orchestrator.

Payload (see shared/contracts.md — Orchestrator):
    {"fnol_text": "...", "policy_text": "...", "model": "<optional>"}
Returns the common envelope whose `result` is the `adjudication_package` (contracts.md §4).
"""

from __future__ import annotations

import os
from typing import Any

from bedrock_agentcore.runtime import BedrockAgentCoreApp

from orchestrate import adjudicate, synthesize_only

app = BedrockAgentCoreApp()


@app.entrypoint
async def invoke(payload: dict[str, Any]) -> dict[str, Any]:
    # Synthesize-only mode: the caller already ran the specialists (e.g. for live progress)
    # and hands us the three findings — skip the specialist calls, just adjudicate.
    if payload.get("claim_record") is not None or payload.get("coverage") is not None \
            or payload.get("risk") is not None:
        return await synthesize_only(
            payload.get("claim_record"), payload.get("coverage"), payload.get("risk"),
            steps=payload.get("steps"), model=payload.get("model"))

    fnol_text = payload.get("fnol_text") or ""
    policy_text = payload.get("policy_text") or ""
    if not fnol_text or not policy_text:
        return {"error": "Provide non-empty 'fnol_text' and 'policy_text'.",
                "framework": "orchestrator-claude"}
    return await adjudicate(fnol_text, policy_text, model=payload.get("model"))


if __name__ == "__main__":
    app.run(port=int(os.environ.get("PORT", "8080")))
