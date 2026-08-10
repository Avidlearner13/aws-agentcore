"""AgentCore Runtime entrypoint for the Claude SDK Coverage agent.

The ``bedrock_agentcore`` runtime serves the AgentCore contract (HTTP /invocations + /ping
on port 8080) and hands the request payload to the ``@app.entrypoint`` function. Locally,
``python app.py`` runs the same server so the agent can be exercised before deployment.

Expected invocation payload (JSON, see shared/contracts.md — Coverage):
    {"claim_record": {...}, "policy_text": "<policy text>", "model": "<optional bedrock id>"}
"""

from __future__ import annotations

import os
from typing import Any

from bedrock_agentcore.runtime import BedrockAgentCoreApp

from coverage import assess_coverage

app = BedrockAgentCoreApp()


@app.entrypoint
async def invoke(payload: dict[str, Any]) -> dict[str, Any]:
    claim_record = payload.get("claim_record")
    policy_text = payload.get("policy_text") or payload.get("policy") or ""
    if not isinstance(claim_record, dict) or not claim_record:
        return {
            "error": "Provide a non-empty 'claim_record' object in the payload.",
            "framework": "claude-agent-sdk",
        }
    if not policy_text:
        return {
            "error": "Provide non-empty 'policy_text' in the payload.",
            "framework": "claude-agent-sdk",
        }
    return await assess_coverage(
        claim_record, policy_text, model=payload.get("model"),
        system_prompt=payload.get("system_prompt"),
    )


if __name__ == "__main__":
    # AgentCore Runtime uses 8080 in-container; locally we allow a unique port via PORT.
    app.run(port=int(os.environ.get("PORT", "8080")))
