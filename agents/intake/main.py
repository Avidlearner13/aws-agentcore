"""AgentCore Runtime entrypoint for the GCP ADK Intake agent.

The ``bedrock_agentcore`` runtime serves the AgentCore contract (HTTP /invocations + /ping)
and hands the request payload to the ``@app.entrypoint`` function. Locally, ``python main.py``
runs the same server so the agent can be exercised before deployment.

Expected invocation payload (JSON), per contracts.md (Intake):
    {"fnol_text": "<FNOL bundle text>", "policy_text": "<policy text>", "model": "<optional bedrock id>"}
"""

from __future__ import annotations

import os
from typing import Any

from bedrock_agentcore.runtime import BedrockAgentCoreApp

from intake import extract_claim_record

app = BedrockAgentCoreApp()


@app.entrypoint
async def invoke(payload: dict[str, Any]) -> dict[str, Any]:
    fnol_text = payload.get("fnol_text") or ""
    policy_text = payload.get("policy_text") or ""
    if not fnol_text:
        return {
            "error": "Provide non-empty 'fnol_text' in the payload.",
            "framework": "gcp-adk",
        }
    return await extract_claim_record(
        fnol_text, policy_text, model=payload.get("model")
    )


if __name__ == "__main__":
    app.run(port=int(os.environ.get("PORT", "8080")))
