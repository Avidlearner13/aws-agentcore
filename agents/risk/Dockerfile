# AgentCore Runtime requires linux/arm64 container images.
FROM --platform=linux/arm64 public.ecr.aws/docker/library/python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1
# ChatBedrockConverse uses boto3, which picks up AWS creds from the AgentCore
# execution role and AWS_REGION injected by the runtime.

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY risk.py main.py ./
COPY kb ./kb

# AgentCore Runtime contract: HTTP server on 8080 exposing /invocations and /ping.
EXPOSE 8080
CMD ["python", "main.py"]
