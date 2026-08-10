# Control-plane + UI image for AWS App Runner.
# NOTE: build context must be the repo root (it copies both control-plane/ and samples/):
#   docker build -f control-plane/Dockerfile .
FROM public.ecr.aws/docker/library/python:3.12-slim

WORKDIR /srv
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8080

COPY control-plane/requirements.txt ./control-plane/requirements.txt
RUN pip install --no-cache-dir -r ./control-plane/requirements.txt

COPY control-plane/app ./control-plane/app
COPY samples ./samples
COPY policies ./policies

# main.py at /srv/control-plane/app/main.py → ROOT=/srv, so /srv/samples resolves correctly.
EXPOSE 8080
WORKDIR /srv/control-plane/app
CMD ["python", "main.py"]
