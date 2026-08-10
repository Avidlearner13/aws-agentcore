"""Generate two elaborate sample homeowners-insurance policy PDFs (Plan A vs renewal Plan B).

These are demo fixtures for the policy-comparison agent. Run:
    & control-plane/.venv/Scripts/python.exe tools/generate_policies.py
Outputs: samples/policy_a.pdf, samples/policy_b.pdf
"""

from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

OUT_DIR = Path(__file__).resolve().parent.parent / "samples"
OUT_DIR.mkdir(exist_ok=True)

# --- Policy content -----------------------------------------------------------

POLICY_A = {
    "title": "EVERGREEN HOMESHIELD — Homeowners Policy (HO-3)",
    "plan": "Plan A — Current Term",
    "decl": {
        "Named insured": "Jordan & Sam Avery",
        "Insured location": "742 Birchwood Lane, Springfield, IL 62704",
        "Policy number": "EHS-HO3-0099821-A",
        "Policy period": "2025-08-01 to 2026-08-01 (12 months)",
        "Total annual premium": "$1,842.00",
        "Roof loss settlement": "Replacement cost (all ages)",
    },
    "property": [
        ("A — Dwelling", "$325,000"),
        ("B — Other Structures", "$32,500 (10% of Dwelling)"),
        ("C — Personal Property", "$162,500 (50% of Dwelling)"),
        ("D — Loss of Use", "$65,000 (20% of Dwelling)"),
    ],
    "deductibles": [
        ("All Other Perils", "$1,000"),
        ("Wind / Hail", "1% of Dwelling ($3,250)"),
        ("Hurricane", "2% of Dwelling ($6,500)"),
    ],
    "liability": [
        ("E — Personal Liability", "$300,000 per occurrence"),
        ("F — Medical Payments to Others", "$5,000 per person"),
    ],
    "endorsements": [
        ("Water Backup & Sump Overflow", "$5,000"),
        ("Service Line Coverage", "Not included"),
        ("Equipment Breakdown", "$50,000"),
        ("Ordinance or Law", "10% of Dwelling"),
        ("Scheduled Personal Property — Jewelry", "$10,000"),
        ("Identity Fraud Expense", "Not included"),
    ],
    "perils": (
        "Section I covers the Dwelling and Other Structures against risk of direct "
        "physical loss (open perils), except as excluded. Personal Property is "
        "covered against the named perils listed in the policy (fire, lightning, "
        "windstorm, theft, etc.)."
    ),
    "exclusions": [
        "Flood and surface water",
        "Earthquake and earth movement",
        "Neglect, wear and tear, and gradual deterioration",
        "Ordinance or law (except as provided by endorsement)",
        "Intentional loss",
    ],
    "conditions": (
        "Insured duties after loss include prompt notice, protecting the property "
        "from further damage, preparing an inventory, and cooperating with the "
        "investigation. Loss is payable 60 days after a sworn proof of loss is filed."
    ),
}

POLICY_B = {
    "title": "EVERGREEN HOMESHIELD — Homeowners Policy (HO-3)",
    "plan": "Plan B — Renewal Offer",
    "decl": {
        "Named insured": "Jordan & Sam Avery",
        "Insured location": "742 Birchwood Lane, Springfield, IL 62704",
        "Policy number": "EHS-HO3-0099821-B",
        "Policy period": "2026-08-01 to 2027-08-01 (12 months)",
        "Total annual premium": "$2,176.00",
        "Roof loss settlement": "Actual cash value (ACV) for roofs older than 15 years",
    },
    "property": [
        ("A — Dwelling", "$358,000"),
        ("B — Other Structures", "$35,800 (10% of Dwelling)"),
        ("C — Personal Property", "$179,000 (50% of Dwelling)"),
        ("D — Loss of Use", "$71,600 (20% of Dwelling)"),
    ],
    "deductibles": [
        ("All Other Perils", "$1,500"),
        ("Wind / Hail", "2% of Dwelling ($7,160)"),
        ("Hurricane", "5% of Dwelling ($17,900)"),
    ],
    "liability": [
        ("E — Personal Liability", "$500,000 per occurrence"),
        ("F — Medical Payments to Others", "$10,000 per person"),
    ],
    "endorsements": [
        ("Water Backup & Sump Overflow", "$15,000"),
        ("Service Line Coverage", "$10,000 (NEW)"),
        ("Equipment Breakdown", "$100,000"),
        ("Ordinance or Law", "25% of Dwelling"),
        ("Scheduled Personal Property — Jewelry", "$15,000"),
        ("Identity Fraud Expense", "$25,000 (NEW)"),
    ],
    "perils": (
        "Section I covers the Dwelling and Other Structures against risk of direct "
        "physical loss (open perils), except as excluded. Personal Property is "
        "covered against the named perils listed in the policy (fire, lightning, "
        "windstorm, theft, etc.)."
    ),
    "exclusions": [
        "Flood and surface water",
        "Earthquake and earth movement",
        "Neglect, wear and tear, and gradual deterioration",
        "Ordinance or law (except as provided by endorsement)",
        "Intentional loss",
        "Home-sharing / short-term rental activity (NEW exclusion)",
    ],
    "conditions": (
        "Insured duties after loss include prompt notice, protecting the property "
        "from further damage, preparing an inventory, and cooperating with the "
        "investigation. Loss is payable 60 days after a sworn proof of loss is filed."
    ),
}


def _styles():
    ss = getSampleStyleSheet()
    ss.add(ParagraphStyle("H1c", parent=ss["Title"], fontSize=16, spaceAfter=4))
    ss.add(ParagraphStyle("Plan", parent=ss["Heading2"], textColor=colors.HexColor("#1f4e79")))
    ss.add(ParagraphStyle("Sec", parent=ss["Heading2"], fontSize=12,
                          textColor=colors.HexColor("#1f4e79"), spaceBefore=10, spaceAfter=4))
    ss.add(ParagraphStyle("Body2", parent=ss["BodyText"], fontSize=9.5, leading=13))
    return ss


def _kv_table(rows):
    t = Table([[k, v] for k, v in rows], colWidths=[2.6 * inch, 3.6 * inch])
    t.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#eef3f8")),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#1f4e79")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c9d6e3")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


def build(policy: dict, out_path: Path):
    ss = _styles()
    story = []
    story.append(Paragraph(policy["title"], ss["H1c"]))
    story.append(Paragraph(policy["plan"], ss["Plan"]))
    story.append(Spacer(1, 6))

    story.append(Paragraph("Declarations", ss["Sec"]))
    story.append(_kv_table(list(policy["decl"].items())))

    story.append(Paragraph("Section I — Property Coverages", ss["Sec"]))
    story.append(_kv_table(policy["property"]))

    story.append(Paragraph("Deductibles", ss["Sec"]))
    story.append(_kv_table(policy["deductibles"]))

    story.append(Paragraph("Section II — Liability Coverages", ss["Sec"]))
    story.append(_kv_table(policy["liability"]))

    story.append(Paragraph("Optional Endorsements & Additional Coverages", ss["Sec"]))
    story.append(_kv_table(policy["endorsements"]))

    story.append(Paragraph("Perils Insured Against", ss["Sec"]))
    story.append(Paragraph(policy["perils"], ss["Body2"]))

    story.append(Paragraph("Exclusions", ss["Sec"]))
    for ex in policy["exclusions"]:
        story.append(Paragraph(f"• {ex}", ss["Body2"]))

    story.append(Paragraph("Conditions", ss["Sec"]))
    story.append(Paragraph(policy["conditions"], ss["Body2"]))

    doc = SimpleDocTemplate(
        str(out_path), pagesize=LETTER,
        leftMargin=0.8 * inch, rightMargin=0.8 * inch,
        topMargin=0.7 * inch, bottomMargin=0.7 * inch,
        title=f"{policy['title']} — {policy['plan']}",
    )
    doc.build(story)
    print("wrote", out_path)


if __name__ == "__main__":
    build(POLICY_A, OUT_DIR / "policy_a.pdf")
    build(POLICY_B, OUT_DIR / "policy_b.pdf")
