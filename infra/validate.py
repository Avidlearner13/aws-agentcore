"""Pre-apply validation for the declarative manifests.

The manifests are only a source of truth if something fails when reality drifts
from them. This is the check that `governance.yaml` declares as
`policy.enforcement[stage: pre-apply]`.

Run it in CI and before any provisioning apply:

    python infra/validate.py         # exit 0 = clean, 1 = drift

Checks:
  1. every manifest parses and has the fields the provisioner requires
  2. every declared model + framework is in policies/allowlist.yaml
  3. each agent's manifest model matches the DEFAULT_MODEL fallback in its code
  4. spec.dependencies reference agents that actually exist
  5. console keys / arnEnv names are unique, and platform agentBindings agree
  6. no account IDs, ARNs or absolute paths leak into a manifest
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
AGENT_DIR = ROOT / "agents"                 # one directory per agent
ALLOWLIST = ROOT / "policies" / "allowlist.yaml"
PLATFORM = ROOT / "infra" / "platform.yaml"

# The module holding each agent's DEFAULT_MODEL literal, relative to its own
# directory, so manifest and code cannot silently disagree.
CODE_MODEL_MODULES = {
    "intake": "intake.py",
    "coverage": "coverage.py",
    "risk": "risk.py",
    "orchestrator": "orchestrate.py",
}

REQUIRED = [
    ("metadata", "name"),
    ("spec", "source", "framework"),
    ("spec", "source", "entrypoint"),
    ("spec", "model", "id"),
    ("spec", "runtime", "protocol"),
]

errors: list[str] = []
warnings: list[str] = []


def err(msg: str) -> None:
    errors.append(msg)


def dig(doc: dict, *path: str):
    cur = doc
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return None
        cur = cur[key]
    return cur


def main() -> int:
    if not AGENT_DIR.is_dir():
        err(f"missing manifest directory: {AGENT_DIR}")
        return report()

    allow = yaml.safe_load(ALLOWLIST.read_text(encoding="utf-8")) or {}
    allow_models = set(allow.get("models") or [])
    allow_frameworks = set(allow.get("frameworks") or [])

    manifests: dict[str, dict] = {}
    manifest_dirs: dict[str, Path] = {}
    for path in sorted(AGENT_DIR.glob("*/agent.yaml")):
        try:
            doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            err(f"{path.name}: does not parse - {exc}")
            continue

        for field in REQUIRED:
            if dig(doc, *field) is None:
                err(f"{path.name}: missing required field spec: {'.'.join(field)}")

        name = dig(doc, "metadata", "name")
        if name:
            manifests[name] = doc
            manifest_dirs[name] = path.parent
            if name != path.parent.name:
                err(f"{path.parent.name}/: directory name does not match "
                    f"metadata.name {name!r} - one agent, one directory")
            if not (path.parent / "agent-card.yaml").exists():
                warnings.append(f"{name}: no agent-card.yaml alongside agent.yaml")

        # 6. leakage
        text = path.read_text(encoding="utf-8")
        if re.search(r"\b\d{12}\b", text):
            err(f"{path.name}: contains what looks like an AWS account ID")
        if "arn:aws:" in text:
            err(f"{path.name}: contains a hardcoded ARN")
        if re.search(r"[A-Za-z]:[\\/]", text):
            err(f"{path.name}: contains an absolute filesystem path")

        # 2. allow-list
        model = dig(doc, "spec", "model", "id")
        if model and allow_models and model not in allow_models:
            err(f"{name}: model {model!r} is not in policies/allowlist.yaml")
        framework = dig(doc, "spec", "source", "framework")
        if framework and allow_frameworks and framework not in allow_frameworks:
            err(f"{name}: framework {framework!r} is not in policies/allowlist.yaml")

    # 3. manifest model vs the literal in the agent's code
    for name, module in CODE_MODEL_MODULES.items():
        doc = manifests.get(name)
        if doc is None:
            continue
        src = manifest_dirs[name] / module
        if not src.exists():
            warnings.append(f"{name}: expected {module} in {manifest_dirs[name].name}/")
            continue
        match = re.search(r'DEFAULT_MODEL\s*=\s*os\.environ\.get\(\s*"[^"]+"\s*,\s*"([^"]+)"',
                          src.read_text(encoding="utf-8"))
        if not match:
            warnings.append(f"{name}: could not find DEFAULT_MODEL in {src.name}")
            continue
        if match.group(1) != dig(doc, "spec", "model", "id"):
            err(f"{name}: manifest model {dig(doc, 'spec', 'model', 'id')!r} != "
                f"{src.name} default {match.group(1)!r}")

    # 4. dependency edges resolve
    for name, doc in manifests.items():
        for dep in dig(doc, "spec", "dependencies") or []:
            target = dep.get("agent")
            if target not in manifests:
                err(f"{name}: depends on unknown agent {target!r}")
            if not dep.get("injectAs"):
                err(f"{name}: dependency on {target!r} has no injectAs")

    # 5. uniqueness + platform agreement
    seen_keys, seen_envs = {}, {}
    for name, doc in manifests.items():
        console = dig(doc, "spec", "console") or {}
        for field, bucket in (("key", seen_keys), ("arnEnv", seen_envs)):
            val = console.get(field)
            if not val:
                warnings.append(f"{name}: spec.console.{field} not set")
            elif val in bucket:
                err(f"{name}: spec.console.{field} {val!r} collides with {bucket[val]!r}")
            else:
                bucket[val] = name

    if PLATFORM.exists():
        platform = yaml.safe_load(PLATFORM.read_text(encoding="utf-8")) or {}
        for svc in dig(platform, "spec", "services") or []:
            for binding in svc.get("agentBindings") or []:
                target = binding.get("agent")
                if target not in manifests:
                    err(f"platform.yaml: binding references unknown agent {target!r}")
                    continue
                declared = (dig(manifests[target], "spec", "console") or {}).get("arnEnv")
                if declared and binding.get("injectAs") != declared:
                    err(f"platform.yaml: binding for {target!r} injects "
                        f"{binding.get('injectAs')!r} but the manifest declares {declared!r}")

    return report()


def report() -> int:
    for w in warnings:
        print(f"WARN  {w}")
    for e in errors:
        print(f"ERROR {e}")
    if errors:
        print(f"\nFAILED - {len(errors)} error(s)")
        return 1
    print(f"OK - manifests consistent ({len(warnings)} warning(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
