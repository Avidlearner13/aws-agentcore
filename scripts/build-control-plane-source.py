"""Assemble the CodeBuild source archive for the control-plane image.

Two things this exists to get right:

1. **Forward-slash archive names.** PowerShell's Compress-Archive writes ZIP
   entries with backslashes; Linux CodeBuild then sees flat filenames like
   "control-plane\\app\\main.py" and every Dockerfile COPY fails. zipfile with
   explicit forward-slash arcnames avoids that.
2. **Only the manifests from agents/.** The control plane reads
   agents/<name>/agent.yaml to build its registry, but must not ship agent code
   or (much worse) the multi-hundred-megabyte .venv directories that live beside
   it. The Dockerfile does `COPY agents ./agents`, so the *build context* is what
   limits it - hence the explicit allow-list below.

Usage:
    python scripts/build-control-plane-source.py [--out PATH]
"""
from __future__ import annotations

import argparse
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Files copied verbatim to the archive root (the Docker build context root).
ROOT_FILES = {
    "control-plane/Dockerfile": "Dockerfile",
    "control-plane/buildspec.yml": "buildspec.yml",
    "control-plane/requirements.txt": "control-plane/requirements.txt",
}

# Whole trees, minus SKIP_DIRS.
TREES = ["control-plane/app", "samples", "policies", "infra"]

# From agents/, take only these filenames - never code, never venvs.
AGENT_FILES = ["agent.yaml", "agent-card.yaml"]

SKIP_DIRS = {".venv", "__pycache__", ".git", ".governance", ".bedrock_agentcore"}


def add_tree(zf: zipfile.ZipFile, rel: str) -> int:
    base = ROOT / rel
    n = 0
    if not base.is_dir():
        return 0
    for dirpath, dirnames, filenames in base.walk() if hasattr(base, "walk") else _walk(base):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            full = Path(dirpath) / fn
            arc = f"{rel}/{full.relative_to(base).as_posix()}"
            zf.write(full, arc)
            n += 1
    return n


def _walk(base: Path):
    import os
    for dp, dn, fn in os.walk(base):
        yield Path(dp), dn, fn


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "build" / "control-plane-source.zip"))
    args = ap.parse_args()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for src, arc in ROOT_FILES.items():
            zf.write(ROOT / src, arc)
        total = len(ROOT_FILES)
        for tree in TREES:
            total += add_tree(zf, tree)
        for agent_dir in sorted((ROOT / "agents").glob("*/")):
            for name in AGENT_FILES:
                f = agent_dir / name
                if f.exists():
                    zf.write(f, f"agents/{agent_dir.name}/{name}")
                    total += 1

    with zipfile.ZipFile(out) as zf:
        names = zf.namelist()
    bad = [n for n in names if "\\" in n]
    leaked = [n for n in names if "/.venv/" in n or n.endswith(".pyc")]
    print(f"wrote {out}  ({len(names)} entries, {out.stat().st_size // 1024} KiB)")
    if bad:
        print(f"ERROR: {len(bad)} entries contain backslashes")
        return 1
    if leaked:
        print(f"ERROR: {len(leaked)} venv/bytecode entries leaked into the archive")
        return 1
    print("manifests included:", [n for n in names if n.startswith("agents/")])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
