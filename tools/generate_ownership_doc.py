"""Render the Ownership & Shared-Responsibility briefing as a polished PDF.

    & control-plane/.venv/Scripts/python.exe tools/generate_ownership_doc.py
Output: docs/ownership-and-shared-responsibility.pdf

Authoring convention for all text/cells: plain text with **bold** and *italic* markers and
literal & < > (escaped automatically). Do NOT embed raw HTML tags or entities.
"""

from __future__ import annotations

import html
import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

OUT = Path(__file__).resolve().parent.parent / "docs" / "ownership-and-shared-responsibility.pdf"
OUT.parent.mkdir(exist_ok=True)
ACCENT = colors.HexColor("#1f4e79")
ACCENT2 = colors.HexColor("#eef3f8")
GRID = colors.HexColor("#c9d6e3")

ss = getSampleStyleSheet()
TITLE = ParagraphStyle("T", parent=ss["Title"], fontSize=19, leading=23, textColor=ACCENT, spaceAfter=2)
SUB = ParagraphStyle("Sub", parent=ss["Heading2"], fontSize=12.5, textColor=colors.HexColor("#33475b"), spaceAfter=2)
META = ParagraphStyle("M", parent=ss["Normal"], fontSize=9, textColor=colors.HexColor("#6b7785"))
H2 = ParagraphStyle("H2", parent=ss["Heading2"], fontSize=13, textColor=ACCENT, spaceBefore=14, spaceAfter=5)
BODY = ParagraphStyle("B", parent=ss["BodyText"], fontSize=9.7, leading=14, alignment=TA_LEFT, spaceAfter=6)
QUOTE = ParagraphStyle("Q", parent=BODY, leftIndent=10, textColor=colors.HexColor("#33475b"), fontName="Helvetica-Oblique")
CELL = ParagraphStyle("C", parent=ss["Normal"], fontSize=8.6, leading=11.5)
CELLH = ParagraphStyle("CH", parent=ss["Normal"], fontSize=8.7, leading=11.5, textColor=colors.white, fontName="Helvetica-Bold")
CELLC = ParagraphStyle("CC", parent=CELL, alignment=1)


def _fmt(t: str) -> str:
    t = html.escape(t, quote=False)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"\*(.+?)\*", r"<i>\1</i>", t)
    return t


def para(t: str, style=BODY) -> Paragraph:
    return Paragraph(_fmt(t), style)


def table(header, rows, widths, center_from=None):
    data = [[Paragraph(_fmt(h), CELLH) for h in header]]
    for r in rows:
        cells = []
        for i, c in enumerate(r):
            st = CELLC if (center_from is not None and i >= center_from) else CELL
            cells.append(Paragraph(_fmt(c), st))
        data.append(cells)
    t = Table(data, colWidths=[w * inch for w in widths], repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, ACCENT2]),
        ("GRID", (0, 0), (-1, -1), 0.4, GRID),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


s = []
s.append(para("Enterprise Agentic AI Platform — Ownership & Shared Responsibility", TITLE))
s.append(para("Infrastructure Services (IS) vs the AI Platform — who owns what on AWS Bedrock AgentCore", SUB))
s.append(para("June 23, 2026", META))
s.append(Spacer(1, 6)); s.append(HRFlowable(color=GRID, width="100%")); s.append(Spacer(1, 6))

s.append(para("AWS Bedrock AgentCore is a managed **substrate** — a runtime plus a set of primitives "
              "(memory, gateway, identity, observability) — the same way RDS, EKS, or a Kafka cluster is "
              "a substrate. Provisioning that substrate is necessary but **not the same as having an "
              "enterprise platform.** This note clarifies what **IS owns** versus what the **AI Platform "
              "team owns**, where their responsibilities meet (the *seams*), the two distinct kinds of "
              '"guardrails," and a RACI to settle ownership.'))

s.append(para("Roles in this document", H2))
s.append(table(
    ["Role", "Who they are"],
    [["**IS — Infrastructure Services**",
      "Provisions and operates the underlying AWS environment and managed services; owns the secured, "
      "compliant substrate."],
     ["**AI Platform team**",
      "Builds the governed platform on top of the substrate (registry, orchestration, policies, tools, "
      "evaluations, console) that application teams build on."],
     ["**App / product teams**",
      "Build and own the specific use-case agents (e.g. claims, underwriting) *using* the platform — "
      "the platform's tenants/consumers, not its builders."],
     ["**Risk / Compliance**",
      "Sets and signs off on the regulatory rules the system must obey (PII handling, approval "
      "requirements, audit, denied actions). Accountable, not a builder; includes Legal / Security / "
      "Data Governance."]],
    [1.9, 5.2]))

s.append(para("1. The layered ownership model", H2))
s.append(table(
    ["Layer", "Owns", "Delivers"],
    [["**Infrastructure Services (IS)**",
      "Account/landing zone, VPC & networking, IAM baseline + **infrastructure guardrails** (§4); "
      "provisions and operates the managed services (AgentCore Runtime, Bedrock access, Gateway/Memory "
      "infra, Fargate); patching, quotas, SLAs, cost plumbing",
      '"A secured, compliant, provisioned AgentCore + Bedrock environment"'],
     ["**AI Platform team**",
      "Agent **blueprints + registry/lifecycle** (create/reuse/clone), **orchestration patterns**, the "
      "**policy repository + AI guardrail content** (§4), **memory strategies**, the **tool/Gateway "
      "catalog** + agents-as-tools, **RAG curation**, **eval/safety** harness, **observability semantics "
      "+ audit**, developer experience (templates, CI/CD), the **console/UI**",
      '"A paved road that app teams safely build agents on"'],
     ["**Application / product teams**",
      "The actual use-case agents (e.g. claims adjudication, underwriting) built using the platform",
      "Business outcomes"]],
    [1.7, 3.9, 1.5]))
s.append(Spacer(1, 4))
s.append(para("AgentCore gives you *primitives*; none of them give you your blueprint model, governance "
              "rules, curated tool catalog, evaluations, or developer experience. Those are the platform."))

s.append(para("2. Is it difficult to separate IS out? — No, if the line is drawn deliberately", H2))
s.append(para("The interfaces are clean. AgentCore exposes a **control plane** (provision/configure — IS, "
              "via Infrastructure-as-Code) versus a **data plane** (invoke/use — Platform & apps). IS owns "
              "provisioning + infrastructure guardrails; the Platform owns everything configured and built "
              "on top. It only becomes hard when **nobody draws the line** — which is the ambiguity this "
              "document removes."))

s.append(para("3. Where ownership / handover / handshaking gets confused (the seams)", H2))
s.append(para("A managed service like AgentCore **collapses several traditional layers** (compute + "
              'identity + memory + gateway) into one product — which is why it can look like "it\'s all in '
              'there." Responsibility still splits, at predictable seams that must be assigned explicitly:'))
s.append(table(
    ["Seam", "The ambiguity", "Clean split"],
    [["**Identity**", "IS owns account IAM; who mints per-agent workload identities + downstream permissions?",
      "IS: baseline + guardrails. Platform: agent identities & credential vending. System owner: approves access"],
     ["**Gateway / tool exposure**", "Who decides which enterprise API becomes an MCP tool, and approves an agent calling it?",
      "IS: network path. Platform: tool definition + authorization policy. Data owner: approval"],
     ["**Memory & data**", "Who owns retention, PII classification, right-to-be-forgotten?",
      "IS: storage/encryption. Platform: memory strategy + retention. Data governance: PII rules"],
     ["**Observability**", "Who owns the compliance audit trail versus the raw logs?",
      "IS: CloudWatch/log infrastructure. Platform: trace semantics, dashboards, audit reports"],
     ["**FinOps**", "Consumption-priced; who owns per-agent/per-tenant cost attribution + budgets?",
      "Platform (with IS tagging support); Finance accountable"],
     ["**CI/CD**", "Who owns the agent build → deploy pipeline (CodeBuild → ECR → AgentCore)?",
      "Platform, on IS-provided primitives"]],
    [1.5, 2.8, 2.8]))

s.append(para('4. Two kinds of "guardrails" (a common point of confusion)', H2))
s.append(para('The word "guardrails" is overloaded — two different layers, owned by two different teams. '
              "This is usually the single biggest source of the ownership argument."))
s.append(table(
    ["Dimension", "Infrastructure / landing-zone guardrails", "AI / behavioral guardrails"],
    [["**What it is**", "Controls on what can be provisioned and how the environment behaves",
      "Controls on how the agent/model behaves"],
     ["**Examples**",
      "SCPs, AWS Config rules, IAM permission boundaries, network/egress controls, encryption-at-rest, "
      "**hardened base/container images** (golden images, CIS benchmarks)",
      "Bedrock Guardrails content (denied topics, content filters, **PII redaction in model I/O**, "
      "prompt-injection defense), tool-authorization, human-approval gates, the policy repository"],
     ["**Owner**", "**IS**", "**Platform team (+ Risk / Compliance)**"]],
    [1.3, 2.9, 2.9]))
s.append(Spacer(1, 4))
s.append(para("**The subtlety — Bedrock Guardrails splits ownership:** IS may *enable the capability* in "
              "the account, but the Platform team and Risk/Compliance *author the guardrail content* "
              "(which topics are denied, which PII is masked, which actions need approval). **Enablement "
              'is not authorship.** So when IS "owns guardrails," that means the **infrastructure baseline '
              "and base images** — **not** the platform-level AI guardrails, which the Platform team owns.",
              QUOTE))

s.append(para("5. RACI — ownership by responsibility, not by service", H2))
s.append(para("The resolving principle: **assign ownership by responsibility, not by service** — the way "
              "cloud providers publish a shared-responsibility model. Each capability gets a named owner, "
              'which dissolves the "it\'s all AgentCore, so it\'s all done / all ours" claim.'))
s.append(para("**R** = Responsible · **A** = Accountable · **C** = Consulted · **I** = Informed", META))
s.append(table(
    ["Capability", "IS", "Platform", "App", "Risk/Comp"],
    [["Account / network / landing zone", "A,R", "I", "I", "C"],
     ["AgentCore & Bedrock provisioning", "A,R", "C", "I", "I"],
     ["Infra guardrails (SCP/Config/base images/encryption)", "A,R", "C", "I", "C"],
     ["Agent identity & credential vending", "C", "A,R", "I", "C"],
     ["Tool exposure (Gateway targets)", "C", "A,R", "C", "C"],
     ["Agent blueprints / registry / lifecycle", "I", "A,R", "C", "I"],
     ["Orchestration patterns", "I", "A,R", "C", "I"],
     ["Memory strategy & retention", "C", "A,R", "I", "C"],
     ["AI / behavioral guardrail content", "C", "R", "I", "A"],
     ["RAG / knowledge-base curation", "I", "A,R", "C", "C"],
     ["Observability semantics & audit", "C", "A,R", "I", "C"],
     ["FinOps / cost attribution", "C", "R", "I", "A=Finance"],
     ["CI/CD for agents", "C", "A,R", "C", "I"],
     ["Evaluation / safety / quality harness", "I", "A,R", "C", "C"],
     ["Use-case agents", "I", "C", "A,R", "C"]],
    [2.7, 0.95, 1.0, 0.85, 1.1], center_from=1))

s.append(para("6. Bottom line", H2))
for b in [
    "Separation is **achievable and not technically hard** — clean control-plane vs data-plane interfaces.",
    "The confusion is **organizational, not architectural**, and is **predictable** at the named seams.",
    "AgentCore being present means the **substrate** is there; the **platform** is the governed layer the AI Platform team owns on top.",
    "Resolve it once with a **shared-responsibility model + RACI**, and the ownership debate goes away.",
]:
    s.append(para("•  " + b))

SimpleDocTemplate(str(OUT), pagesize=LETTER, leftMargin=0.7 * inch, rightMargin=0.7 * inch,
                  topMargin=0.65 * inch, bottomMargin=0.6 * inch,
                  title="Ownership & Shared Responsibility — Agent-Core").build(s)
print("wrote", OUT)
