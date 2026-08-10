"""Risk, Fraud & Compliance agent for the claims-adjudication platform.

Implemented with LangChain (``langchain_aws.ChatBedrockConverse``), running Claude on
Amazon Bedrock via the Converse API. This is the LangChain specialist in the three-agent
adjudication pipeline (Intake → Coverage → Risk); see ``shared/contracts.md``.

The agent takes a ``claim_record`` (contracts.md §1) plus optional claimant/claim
``history`` and returns a ``risk_assessment`` (contracts.md §3): a ``fraud_score`` (0-100),
``risk_level``, ``flags``, a ``compliance`` block whose ``cited_rules`` reference the KB
guideline IDs/sources, and a ``recommended_action``.

Retrieval (light RAG): the knowledge base is a small set of Markdown guideline files
(``samples/kb/*.md`` — G-12 water damage, G-30 fraud red flags, R-05 regulatory). We load
the files at call time and ground the assessment + citations in them. The corpus is tiny,
so we inject the relevant guideline snippets directly into the prompt: we select files by
keyword/peril relevance and always include the fraud and regulatory guidelines (which apply
to every claim). The result envelope mirrors the other framework agents so the orchestrator
can compare them directly.
"""

from __future__ import annotations

import glob
import json
import os
import re
import time
from typing import Any

from langchain_aws import ChatBedrockConverse
from langchain_core.messages import HumanMessage, SystemMessage

# Bedrock model — Amazon Nova Pro (AWS-native, cheaper than Claude). ``us.`` prefix =
# cross-region inference profile in us-east-1.
# Override per-invocation (``model`` arg) or per-deployment (env CLAUDE_MODEL).
DEFAULT_MODEL = os.environ.get("CLAUDE_MODEL", "us.amazon.nova-pro-v1:0")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

# Knowledge base of guideline Markdown files. Overridable via env KB_DIR.
# Defaults to a `kb/` folder beside this file so it works both locally and inside the
# AgentCore container image (the Dockerfile bundles `kb/`).
DEFAULT_KB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kb")

# Always-relevant guidelines (apply to every claim regardless of peril).
_ALWAYS_INCLUDE = ("fraud", "regulatory")

# Keyword → filename-stem hints for naive peril/topic-based selection.
_TOPIC_KEYWORDS = {
    "water": ("water",),
    "flood": ("water",),
    "pipe": ("water",),
    "fire": ("fire",),
    "theft": ("theft",),
    "wind": ("wind",),
    "liability": ("liability",),
}

SYSTEM_PROMPT = """You are a senior insurance claims risk, fraud, and compliance analyst.
You review a claim_record (and any claimant/claim history) against the company's
KNOWLEDGE BASE guidelines and produce a structured risk assessment.

Ground every judgment in the provided KB guidelines. When you flag a fraud signal or a
compliance concern, cite the specific guideline by its ID/source (e.g. "G-30", "R-05",
"G-12") drawn ONLY from the KB excerpts given to you. Do not invent guideline IDs.

Scoring guidance (per G-30):
- Higher fraud_score for: late reporting relative to date of loss, amounts engineered just
  under a deductible/sub-limit, missing/unverifiable documentation, prior similar claims,
  inconsistent narrative (cause not matching damage), round-number or inflated line items.
- Lower fraud_score for: prompt reporting (within 24-48h), independent contractor estimates,
  damage consistent with the stated cause, no claim history.
Map the 0-100 score to risk_level roughly as: 0-33 low, 34-66 medium, 67-100 high.

Respond with ONLY a single JSON object (no prose, no code fences) matching this schema:
{
  "fraud_score": 0,
  "risk_level": "low | medium | high",
  "flags": [
    {"signal": "...", "severity": "low|medium|high", "explanation": "..."}
  ],
  "compliance": {
    "concerns": ["..."],
    "cited_rules": [ {"rule": "guideline ID and short name", "source": "KB filename or guideline ID"} ]
  },
  "recommended_action": "plain-language next step (e.g. proceed, request docs, refer to SIU)"
}
fraud_score MUST be an integer 0-100. risk_level MUST be one of low|medium|high.
cited_rules MUST be non-empty and reference the KB guidelines provided. Be faithful to the
claim_record and the KB; do not invent facts.
"""


def _load_kb(kb_dir: str, peril: str = "", text_hint: str = "") -> list[tuple[str, str]]:
    """Load KB guideline files as (filename, contents) tuples.

    Naive retrieval: always include the fraud + regulatory guidelines (universally
    applicable), plus any file whose stem matches the claim's peril/topic keywords. The
    corpus is tiny, so if selection yields too little we fall back to all files.
    """
    paths = sorted(glob.glob(os.path.join(kb_dir, "*.md")))
    if not paths:
        return []

    hint = f"{peril} {text_hint}".lower()
    wanted_stems: set[str] = set()
    for kw, stems in _TOPIC_KEYWORDS.items():
        if kw in hint:
            wanted_stems.update(stems)

    selected: list[tuple[str, str]] = []
    for path in paths:
        name = os.path.basename(path)
        stem = name.lower()
        relevant = any(tag in stem for tag in _ALWAYS_INCLUDE) or any(
            s in stem for s in wanted_stems
        )
        if relevant:
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    selected.append((name, fh.read().strip()))
            except OSError:
                continue

    # Fallback: include everything if selection was empty/too narrow.
    if len(selected) < 2:
        selected = []
        for path in paths:
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    selected.append((os.path.basename(path), fh.read().strip()))
            except OSError:
                continue
    return selected


def _build_prompt(claim_record: dict[str, Any], history: str, kb: list[tuple[str, str]]) -> str:
    kb_blocks = "\n\n".join(f"--- {name} ---\n{body}" for name, body in kb) or "(none)"
    history_block = history.strip() or "(no prior claimant/claim history provided)"
    claim_json = json.dumps(claim_record, indent=2, ensure_ascii=False)
    return (
        "Assess the fraud risk and compliance posture of this claim. Ground your "
        "assessment and citations in the KNOWLEDGE BASE guidelines below.\n\n"
        f"=== KNOWLEDGE BASE GUIDELINES ===\n{kb_blocks}\n\n"
        f"=== CLAIM RECORD ===\n{claim_json}\n\n"
        f"=== CLAIMANT / CLAIM HISTORY ===\n{history_block}\n\n"
        "Return ONLY the risk_assessment JSON object."
    )


def _extract_json(text: str) -> dict[str, Any] | None:
    """Best-effort parse: strip code fences, then load the first JSON object found."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.DOTALL)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                return None
    return None


def _content_to_text(content: Any) -> str:
    """ChatBedrockConverse may return a string or a list of content blocks."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and "text" in block:
                parts.append(block["text"])
        return "".join(parts)
    return str(content)


async def assess_risk(
    claim_record: dict[str, Any], history: str = "", *, model: str | None = None
) -> dict[str, Any]:
    """Assess fraud risk and compliance for a claim_record; return a normalized envelope.

    Loads the KB from ``KB_DIR`` (env, default ``samples/kb``), grounds the assessment in
    the relevant guidelines (light RAG), and returns the common envelope shared across the
    framework agents: framework, model, result (the risk_assessment), raw, and meta.
    """
    model_id = model or DEFAULT_MODEL
    kb_dir = os.environ.get("KB_DIR", DEFAULT_KB_DIR)

    loss = claim_record.get("loss") or {}
    peril = str(loss.get("peril_category") or "")
    text_hint = " ".join(
        str(loss.get(k) or "") for k in ("cause", "description")
    )
    kb = _load_kb(kb_dir, peril=peril, text_hint=text_hint)
    kb_sources = [name for name, _ in kb]

    llm = ChatBedrockConverse(model_id=model_id, region_name=AWS_REGION)
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=_build_prompt(claim_record, history, kb)),
    ]

    start = time.perf_counter()
    response = await llm.ainvoke(messages)
    latency_ms = round((time.perf_counter() - start) * 1000.0, 1)

    raw = _content_to_text(getattr(response, "content", "")).strip()

    # Usage/metadata are guarded: shapes vary by langchain-aws version.
    usage = getattr(response, "usage_metadata", None)
    response_metadata = getattr(response, "response_metadata", None) or {}
    meta: dict[str, Any] = {
        "latency_ms": latency_ms,
        "usage": usage,
        "input_tokens": (usage or {}).get("input_tokens") if isinstance(usage, dict) else None,
        "output_tokens": (usage or {}).get("output_tokens") if isinstance(usage, dict) else None,
        "total_tokens": (usage or {}).get("total_tokens") if isinstance(usage, dict) else None,
        "stop_reason": response_metadata.get("stopReason"),
        "model_id": response_metadata.get("model_id") or model_id,
        "kb_dir": kb_dir,
        "kb_sources": kb_sources,
    }
    try:
        metrics = response_metadata.get("metrics") or {}
        meta["bedrock_latency_ms"] = metrics.get("latencyMs")
    except (AttributeError, TypeError):
        pass

    return {
        "framework": "langchain",
        "model": model_id,
        "result": _extract_json(raw),
        "raw": raw,
        "meta": meta,
    }
