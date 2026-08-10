# AgentCore Runtime requires linux/arm64 container images.
FROM --platform=linux/arm64 public.ecr.aws/docker/library/python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    # Synthesis step uses the Claude Agent SDK on Bedrock; specialist calls use boto3.
    CLAUDE_CODE_USE_BEDROCK=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY orchestrate.py app.py ./

# AgentCore Runtime contract: HTTP server on 8080 exposing /invocations and /ping.
# Specialist ARNs are injected at deploy via --env INTAKE_ARN/COVERAGE_ARN/RISK_ARN; the
# orchestrator's execution role must allow bedrock-agentcore:InvokeAgentRuntime on them.
EXPOSE 8080
CMD ["python", "app.py"]
