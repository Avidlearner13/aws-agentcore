"""Switch the App Runner console to a specific ECR image tag (deploy or rollback).

The service is pinned to an explicit tag (v1, v2, ...), so deploying or rolling back is just
"point it at a different tag and redeploy". This round-trips the EXACT current SourceConfiguration
and changes ONLY the image tag, so every env var / secret / IAM role is preserved.

Usage (from the repo root, using the control-plane venv's python):
    control-plane/.venv/Scripts/python.exe scripts/set-app-image.py v2     # deploy v2
    control-plane/.venv/Scripts/python.exe scripts/set-app-image.py v1     # roll back to v1
Or via the wrapper:  scripts\\Agent-Core DEPLOY.cmd v2
"""
import os
import sys
import time

import boto3

# Per-account settings. Overridable by env so this file never pins an account.
PROFILE = os.environ.get("AGENTCORE_PROFILE", "agentcore-personal")
REGION = os.environ.get("AWS_REGION", "us-east-1")
SVC_NAME = os.environ.get("AGENTCORE_SVC_NAME", "agent-core-console")
REPO = os.environ.get("AGENTCORE_ECR_REPO", "agent-core-control-plane")


def _resolve_service(ar, name: str) -> str:
    """Look the App Runner service ARN up by name, so no account ID is hardcoded."""
    paginator = ar.get_paginator("list_services")
    for page in paginator.paginate():
        for s in page["ServiceSummaryList"]:
            if s["ServiceName"] == name:
                return s["ServiceArn"]
    raise SystemExit(f"ERROR: App Runner service '{name}' not found in profile "
                     f"{PROFILE} ({REGION}). Has it been created yet?")


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: set-app-image.py <image-tag>   point App Runner at an existing ECR tag")
        print("       set-app-image.py --show        print the currently-served tag")
        print("       set-app-image.py --list        list available ECR tags (newest first)")
        return 2
    tag = sys.argv[1]
    s = boto3.Session(profile_name=PROFILE, region_name=REGION)
    ecr, ar = s.client("ecr"), s.client("apprunner")
    svc = _resolve_service(ar, SVC_NAME)

    if tag == "--show":
        svc = ar.describe_service(ServiceArn=svc)["Service"]
        ident = svc["SourceConfiguration"]["ImageRepository"]["ImageIdentifier"]
        print(f"    {ident.split('/')[-1]}   (service status: {svc['Status']})")
        return 0

    if tag == "--list":
        cur = (ar.describe_service(ServiceArn=svc)["Service"]
               ["SourceConfiguration"]["ImageRepository"]["ImageIdentifier"].split(":")[-1])
        imgs = ecr.describe_images(repositoryName=REPO)["imageDetails"]
        imgs.sort(key=lambda d: d.get("imagePushedAt"), reverse=True)
        for d in imgs:
            tags = d.get("imageTags") or ["<untagged>"]
            when = d.get("imagePushedAt")
            mark = "  <-- serving now" if cur in tags else ""
            print(f"    {','.join(tags):18} {when:%Y-%m-%d}{mark}")
        return 0

    # Refuse to deploy a tag that doesn't exist in ECR (prevents a broken deployment).
    try:
        ecr.describe_images(repositoryName=REPO, imageIds=[{"imageTag": tag}])
    except ecr.exceptions.ImageNotFoundException:
        print(f"ERROR: image tag '{tag}' not found in ECR repo {REPO}. Build/push it first.")
        return 1

    sc = ar.describe_service(ServiceArn=svc)["Service"]["SourceConfiguration"]
    old = sc["ImageRepository"]["ImageIdentifier"]
    new = old.rsplit(":", 1)[0] + ":" + tag
    if old == new:
        print(f"Already pinned to {tag}. Forcing a redeploy anyway.")
        ar.start_deployment(ServiceArn=svc)
    else:
        print(f"Switching image: {old.split('/')[-1]} -> {new.split('/')[-1]}")
        sc["ImageRepository"]["ImageIdentifier"] = new
        ar.update_service(ServiceArn=svc, SourceConfiguration=sc)

    print("Deploying... (~3-5 min)")
    deadline = time.time() + 360
    while time.time() < deadline:
        st = ar.describe_service(ServiceArn=svc)["Service"]["Status"]
        if st != "OPERATION_IN_PROGRESS":
            print("Final status:", st, "| now serving tag:", tag)
            return 0 if st == "RUNNING" else 1
        time.sleep(20)
    print("Still in progress after 6 min — check the App Runner console.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
