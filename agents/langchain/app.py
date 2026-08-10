"""AgentCore Runtime entrypoint for the LangChain Risk/Fraud/Compliance agent.

The ``bedrock_agentcore`` runtime serves the AgentCore contract (HTTP /invocations + /ping)
and hands the request payload to the ``@app.entrypoint`` function. Locally, ``python app.py``
runs the same server so the agent can be exercised before deployment.

Expected invocation payload (JSON), per shared/contracts.md (Risk):
    {"claim_record": {...}, "history": "<optional>", "model": "<optional bedrock id>"}
"""

from __future__ import annotations

import os
from typing import Any

from bedrock_agentcore.runtime import BedrockAgentCoreApp

from risk import assess_risk

app = BedrockAgentCoreApp()


@app.entrypoint
async def invoke(payload: dict[str, Any]) -> dict[str, Any]:
    claim_record = payload.get("claim_record")
    if not isinstance(claim_record, dict) or not claim_record:
        return {
            "error": "Provide a non-empty 'claim_record' object in the payload.",
            "framework": "langchain",
        }
    history = payload.get("history") or ""
    return await assess_risk(claim_record, history, model=payload.get("model"))


if __name__ == "__main__":
    app.run(port=int(os.environ.get("PORT", "8080")))
