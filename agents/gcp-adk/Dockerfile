# AgentCore Runtime requires linux/arm64 container images.
FROM --platform=linux/arm64 public.ecr.aws/docker/library/python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY intake.py app.py ./

# AgentCore Runtime contract: HTTP server on 8080 exposing /invocations and /ping.
# AWS creds come from the AgentCore execution role; AWS_REGION is injected by the runtime.
# LiteLLM uses boto3 under the hood to call Bedrock, so no extra runtime deps are needed.
EXPOSE 8080
CMD ["python", "app.py"]
