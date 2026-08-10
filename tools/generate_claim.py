"""Generate a sample FNOL (First Notice of Loss) claim bundle as PDFs.

Demo fixtures for the claims-adjudication flow: a burst-pipe water-damage claim filed against
policy_a.pdf (Evergreen HomeShield Plan A). Run:
    & control-plane/.venv/Scripts/python.exe tools/generate_claim.py
Outputs: samples/claims/fnol_form.pdf, samples/claims/repair_estimate.pdf
"""

from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

OUT_DIR = Path(__file__).resolve().parent.parent / "samples" / "claims"
OUT_DIR.mkdir(parents=True, exist_ok=True)

ACCENT = colors.HexColor("#1f4e79")


def _styles():
    ss = getSampleStyleSheet()
    ss.add(ParagraphStyle("H1c", parent=ss["Title"], fontSize=16, spaceAfter=4))
    ss.add(ParagraphStyle("Sub", parent=ss["Heading2"], textColor=ACCENT))
    ss.add(ParagraphStyle("Sec", parent=ss["Heading2"], fontSize=12, textColor=ACCENT,
                          spaceBefore=10, spaceAfter=4))
    ss.add(ParagraphStyle("Body2", parent=ss["BodyText"], fontSize=9.5, leading=13))
    return ss


def _kv(rows):
    t = Table([[k, v] for k, v in rows], colWidths=[2.4 * inch, 3.8 * inch])
    t.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#eef3f8")),
        ("TEXTCOLOR", (0, 0), (0, -1), ACCENT),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c9d6e3")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


def _line_items(rows, total):
    data = [["Description", "Category", "Amount"]] + rows + [["", "Total claimed", total]]
    t = Table(data, colWidths=[3.2 * inch, 1.8 * inch, 1.2 * inch])
    t.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("BACKGROUND", (0, 0), (-1, 0), ACCENT), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c9d6e3")),
        ("FONTNAME", (1, -1), (-1, -1), "Helvetica-Bold"),
        ("ALIGN", (2, 0), (2, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


def build_fnol(path: Path):
    ss = _styles()
    s = []
    s.append(Paragraph("EVERGREEN HOMESHIELD — First Notice of Loss", ss["H1c"]))
    s.append(Paragraph("Claim Intake Form", ss["Sub"]))
    s.append(Spacer(1, 6))
    s.append(Paragraph("Claim & Policy", ss["Sec"]))
    s.append(_kv([
        ("Claim number", "CLM-2026-44817"),
        ("Policy number", "EHS-HO3-0099821-A"),
        ("Named insured", "Jordan & Sam Avery"),
        ("Insured location", "742 Birchwood Lane, Springfield, IL 62704"),
        ("Contact", "jordan.avery@example.com / (217) 555-0148"),
        ("Date of loss", "2026-03-14"),
        ("Date reported", "2026-03-15"),
    ]))
    s.append(Paragraph("Loss Details", ss["Sec"]))
    s.append(_kv([
        ("Cause of loss", "Sudden burst of the supply pipe under the kitchen sink"),
        ("Peril category", "Water (sudden & accidental plumbing discharge)"),
        ("Was it a flood / external water?", "No — internal plumbing failure"),
        ("Was it sewer/drain backup?", "No"),
    ]))
    s.append(Paragraph(
        "Description: While the insured was away for the weekend, the cold-water supply line under "
        "the kitchen sink burst. Water ran for an estimated 6–8 hours, damaging the kitchen hardwood "
        "flooring, the lower cabinets, and an adjacent area rug. A plumber capped the line and a "
        "mitigation company performed water extraction and drying. No mold observed at inspection.",
        ss["Body2"]))
    s.append(Paragraph("Itemized Claim", ss["Sec"]))
    s.append(_line_items([
        ["Hardwood flooring repair/replacement (kitchen)", "Dwelling", "$8,500.00"],
        ["Lower kitchen cabinets", "Dwelling", "$4,200.00"],
        ["Water extraction & structural drying", "Mitigation", "$3,100.00"],
        ["Area rug (personal property)", "Contents", "$900.00"],
    ], "$16,700.00"))
    s.append(Spacer(1, 8))
    s.append(Paragraph("Attachments: repair_estimate.pdf (contractor estimate).", ss["Body2"]))
    SimpleDocTemplate(str(path), pagesize=LETTER, leftMargin=0.8 * inch, rightMargin=0.8 * inch,
                      topMargin=0.7 * inch, bottomMargin=0.7 * inch, title="FNOL — CLM-2026-44817").build(s)
    print("wrote", path)


def build_estimate(path: Path):
    ss = _styles()
    s = []
    s.append(Paragraph("DryFast Restoration LLC — Repair Estimate", ss["H1c"]))
    s.append(Paragraph("Estimate #DF-9921 · for CLM-2026-44817", ss["Sub"]))
    s.append(Spacer(1, 6))
    s.append(_kv([
        ("Property", "742 Birchwood Lane, Springfield, IL 62704"),
        ("Prepared for", "Jordan & Sam Avery"),
        ("Inspection date", "2026-03-16"),
        ("Cause", "Burst supply line under kitchen sink — water damage"),
    ]))
    s.append(Paragraph("Estimated Costs", ss["Sec"]))
    s.append(_line_items([
        ["Remove & replace hardwood flooring (180 sq ft)", "Dwelling", "$8,500.00"],
        ["Replace lower cabinets + countertop section", "Dwelling", "$4,200.00"],
        ["Emergency water extraction + 3-day drying", "Mitigation", "$3,100.00"],
        ["Area rug (not restorable)", "Contents", "$900.00"],
    ], "$16,700.00"))
    s.append(Spacer(1, 8))
    s.append(Paragraph("Notes: Damage limited to kitchen and adjacent hallway. No evidence of "
                       "long-term leakage; failure appears sudden. Estimate valid 30 days.", ss["Body2"]))
    SimpleDocTemplate(str(path), pagesize=LETTER, leftMargin=0.8 * inch, rightMargin=0.8 * inch,
                      topMargin=0.7 * inch, bottomMargin=0.7 * inch, title="Repair Estimate DF-9921").build(s)
    print("wrote", path)


if __name__ == "__main__":
    build_fnol(OUT_DIR / "fnol_form.pdf")
    build_estimate(OUT_DIR / "repair_estimate.pdf")
