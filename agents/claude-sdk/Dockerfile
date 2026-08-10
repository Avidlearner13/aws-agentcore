# AgentCore Runtime requires linux/arm64 container images.
FROM --platform=linux/arm64 public.ecr.aws/docker/library/python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    # Route the Claude Agent SDK to Claude on Amazon Bedrock (creds come from the
    # AgentCore execution role; AWS_REGION is injected by the runtime).
    CLAUDE_CODE_USE_BEDROCK=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY coverage.py app.py ./

# AgentCore Runtime contract: HTTP server on 8080 exposing /invocations and /ping.
EXPOSE 8080
CMD ["python", "app.py"]

# NOTE: verify at first build that claude_agent_sdk's bundled CLI runs in this base image
# (the linux/arm64 wheel is expected to be self-contained). If it requires Node.js at
# runtime, add it here:  RUN apt-get update && apt-get install -y --no-install-recommends nodejs npm
