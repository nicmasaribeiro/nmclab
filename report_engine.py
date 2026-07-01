
from __future__ import annotations

import csv
import io
import re
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List


def _safe(value: Any) -> str:
    text = str(value if value is not None else "")
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text).strip()


def _num(value: Any) -> Any:
    if value is None:
        return ""
    return value


def report_filename(kind: str, ext: str) -> str:
    safe_kind = re.sub(r"[^a-z0-9_-]+", "_", (kind or "report").lower()).strip("_") or "report"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"nmc_{safe_kind}_report_{stamp}.{ext}"


def _writer() -> tuple[io.StringIO, csv.writer]:
    buffer = io.StringIO(newline="")
    return buffer, csv.writer(buffer)


def _write_rows(writer: csv.writer, title: str, headers: Iterable[str], rows: Iterable[Iterable[Any]]) -> None:
    writer.writerow([title])
    writer.writerow(list(headers))
    for row in rows:
        writer.writerow([_safe(cell) for cell in row])
    writer.writerow([])


def _component_rows(report: Dict[str, Any]) -> List[List[Any]]:
    rows = []
    for row in report.get("component_rows", []) or []:
        rows.append([row.get("key"), row.get("label"), row.get("score"), row.get("description")])
    return rows


def _bar_score_rows(report: Dict[str, Any]) -> List[List[Any]]:
    rows = []
    for row in report.get("bar_scores", []) or []:
        comps = row.get("component_scores", {}) or {}
        rows.append([
            row.get("line_number"),
            row.get("assigned_bars") or row.get("bar_index"),
            row.get("overall"),
            row.get("grade", {}).get("letter"),
            comps.get("rhyme_power"),
            comps.get("cadence_fit"),
            comps.get("bar_fit"),
            comps.get("meter_stress"),
            comps.get("scansion_physics"),
            comps.get("content_clarity"),
            "; ".join(row.get("diagnosis", {}).get("issues", []) or []),
            row.get("text"),
        ])
    return rows


def build_csv_report(kind: str, report: Dict[str, Any], meta: Dict[str, Any] | None = None) -> str:
    meta = meta or {}
    kind = (kind or "snapshot").lower()
    buffer, writer = _writer()
    writer.writerow(["NMC Rap Lab Export"])
    writer.writerow(["kind", kind])
    writer.writerow(["generated_utc", datetime.now(timezone.utc).isoformat(timespec="seconds")])
    writer.writerow(["mode", meta.get("mode", "")])
    writer.writerow([])

    if kind == "compare":
        summary = report.get("summary", {}) or {}
        _write_rows(writer, "Summary", ["metric", "value"], [
            ["original_score", summary.get("original_score")],
            ["edited_score", summary.get("edited_score")],
            ["delta", summary.get("delta")],
            ["verdict", summary.get("verdict")],
            ["recommendation", summary.get("recommendation")],
            ["changed_bars", summary.get("changed_bars")],
            ["improved_bars", summary.get("improved_bars")],
            ["weakened_bars", summary.get("weakened_bars")],
        ])
        _write_rows(writer, "Component deltas", ["key", "label", "original", "edited", "delta", "verdict"], [
            [row.get("key"), row.get("label"), row.get("original"), row.get("edited"), row.get("delta"), row.get("verdict")]
            for row in (report.get("component_deltas", []) or [])
        ])
        _write_rows(writer, "Changed bars", ["bar", "status", "delta", "original_score", "edited_score", "original_text", "edited_text", "advice"], [
            [row.get("bar_index"), row.get("status"), row.get("delta"), row.get("original_score"), row.get("edited_score"), row.get("original_text"), row.get("edited_text"), " | ".join(row.get("edited_advice", []) or [])]
            for row in (report.get("changed_bars", []) or [])
        ])
        return buffer.getvalue()

    score_report = report if kind == "score" else report.get("score_report", {}) or {}
    if score_report:
        _write_rows(writer, "System score", ["metric", "value"], [
            ["overall", score_report.get("overall")],
            ["grade", score_report.get("grade", {}).get("letter")],
            ["label", score_report.get("grade", {}).get("label")],
            ["headline", score_report.get("headline")],
        ])
        _write_rows(writer, "Score components", ["key", "label", "score", "description"], _component_rows(score_report))
        _write_rows(writer, "Bar scores", ["line", "bars", "overall", "grade", "rhyme", "cadence", "bar_fit", "meter", "physics", "clarity", "issues", "text"], _bar_score_rows(score_report))

    if kind == "snapshot":
        _write_rows(writer, "Snapshot overview", ["metric", "value"], [
            ["headline", report.get("overview", {}).get("headline")],
            ["lines", report.get("summary", {}).get("lines")],
            ["words", report.get("summary", {}).get("words")],
            ["style_match", report.get("summary", {}).get("style_match")],
            ["best_reference", report.get("comparison", {}).get("best_match", {}).get("name")],
            ["best_reference_score", report.get("comparison", {}).get("best_match", {}).get("score")],
        ])
        _write_rows(writer, "Static line breakdown", ["line", "priority", "syllables", "word_count", "end_word", "rhyme_key", "role", "action_steps", "text"], [
            [row.get("line_number"), row.get("priority"), row.get("syllables"), row.get("word_count"), row.get("end_word"), row.get("rhyme_key"), row.get("role"), " | ".join(row.get("suggestion", {}).get("action_steps", []) or []), row.get("text")]
            for row in (report.get("line_breakdown", []) or [])
        ])
    return buffer.getvalue()


def _pdf_styles():
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib import colors
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="NmcTitle", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=22, leading=27, textColor=colors.HexColor("#111827"), spaceAfter=14))
    styles.add(ParagraphStyle(name="NmcH2", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=14, leading=18, textColor=colors.HexColor("#111827"), spaceBefore=12, spaceAfter=8))
    styles.add(ParagraphStyle(name="NmcBody", parent=styles["BodyText"], fontName="Helvetica", fontSize=9.4, leading=12.5, textColor=colors.HexColor("#1f2937")))
    styles.add(ParagraphStyle(name="NmcSmall", parent=styles["BodyText"], fontName="Helvetica", fontSize=8, leading=10, textColor=colors.HexColor("#4b5563")))
    return styles


def _para(text: Any, style):
    from xml.sax.saxutils import escape
    from reportlab.platypus import Paragraph
    return Paragraph(escape(_safe(text)), style)


def _table(rows: List[List[Any]], widths: List[float] | None = None):
    from reportlab.lib import colors
    from reportlab.platypus import Table, TableStyle
    data = [[_safe(cell) for cell in row] for row in rows]
    table = Table(data, colWidths=widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#111827")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7.2),
        ("LEADING", (0, 0), (-1, -1), 8.5),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d1d5db")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f9fafb")]),
    ]))
    return table


def _add_score_story(story: list, score: Dict[str, Any], styles: Dict[str, Any]) -> None:
    from reportlab.platypus import Spacer
    story.append(_para("System score", styles["NmcH2"]))
    grade = score.get("grade", {}) or {}
    story.append(_para(f"{score.get('overall', 0)}% - {grade.get('letter', '')} - {grade.get('label', '')}", styles["NmcBody"]))
    if score.get("headline"):
        story.append(_para(score.get("headline"), styles["NmcBody"]))
    actions = score.get("global_actions", []) or []
    if actions:
        story.append(_para("Top actions: " + " | ".join(actions[:6]), styles["NmcSmall"]))
    comps = score.get("component_rows", []) or []
    if comps:
        rows = [["Component", "Score", "Description"]] + [[r.get("label") or r.get("key"), r.get("score"), r.get("description")] for r in comps[:10]]
        story.append(_table(rows, [105, 48, 360]))
        story.append(Spacer(1, 8))
    bars = score.get("bar_scores", []) or []
    if bars:
        rows = [["Line", "Bars", "Score", "Weakest / issues", "Text"]]
        for row in bars[:80]:
            issues = "; ".join(row.get("diagnosis", {}).get("issues", []) or [])
            rows.append([row.get("line_number"), row.get("assigned_bars") or row.get("bar_index"), row.get("overall"), issues[:130], _safe(row.get("text"))[:160]])
        story.append(_para("Bar scores", styles["NmcH2"]))
        story.append(_table(rows, [34, 50, 44, 170, 215]))


def build_pdf_report(kind: str, report: Dict[str, Any], meta: Dict[str, Any] | None = None) -> bytes:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Spacer

    meta = meta or {}
    kind = (kind or "snapshot").lower()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=0.55 * inch, leftMargin=0.55 * inch, topMargin=0.55 * inch, bottomMargin=0.55 * inch)
    styles = _pdf_styles()
    story: list = []
    title = {"snapshot": "NMC Static Snapshot Report", "score": "NMC System Score Report", "compare": "NMC Edit Comparison Report"}.get(kind, "NMC Rap Report")
    story.append(_para(title, styles["NmcTitle"]))
    story.append(_para(f"Generated UTC: {datetime.now(timezone.utc).isoformat(timespec='seconds')} | Mode: {meta.get('mode', '')}", styles["NmcSmall"]))
    story.append(Spacer(1, 8))

    if kind == "compare":
        summary = report.get("summary", {}) or {}
        story.append(_para(summary.get("recommendation") or summary.get("verdict") or "Edit comparison ready.", styles["NmcH2"]))
        rows = [["Original", "Edited", "Delta", "Changed", "Improved", "Weakened"], [summary.get("original_score"), summary.get("edited_score"), summary.get("delta"), summary.get("changed_bars"), summary.get("improved_bars"), summary.get("weakened_bars")]]
        story.append(_table(rows, [70, 70, 60, 70, 70, 70]))
        comps = report.get("component_deltas", []) or []
        if comps:
            story.append(_para("Component deltas", styles["NmcH2"]))
            story.append(_table([["Component", "Original", "Edited", "Delta", "Verdict"]] + [[r.get("label"), r.get("original"), r.get("edited"), r.get("delta"), r.get("verdict")] for r in comps], [130, 55, 55, 50, 220]))
        changed = report.get("changed_bars", []) or []
        if changed:
            story.append(_para("Changed bars", styles["NmcH2"]))
            story.append(_table([["Bar", "Delta", "Before", "After", "Advice"]] + [[r.get("bar_index"), r.get("delta"), _safe(r.get("original_text"))[:145], _safe(r.get("edited_text"))[:145], " | ".join(r.get("edited_advice", []) or [])[:160]] for r in changed[:60]], [35, 42, 145, 145, 145]))
    elif kind == "score":
        _add_score_story(story, report, styles)
    else:
        overview = report.get("overview", {}) or {}
        story.append(_para(overview.get("headline") or "Static snapshot ready.", styles["NmcH2"]))
        actions = overview.get("actions", []) or []
        if actions:
            story.append(_para("Top actions: " + " | ".join(actions[:7]), styles["NmcSmall"]))
        score = report.get("score_report", {}) or {}
        if score:
            _add_score_story(story, score, styles)
        lines = report.get("line_breakdown", []) or []
        if lines:
            story.append(_para("Line-by-line suggestions", styles["NmcH2"]))
            rows = [["Line", "Priority", "Syll", "Rhyme", "Action", "Text"]]
            for row in lines[:90]:
                actions = " | ".join(row.get("suggestion", {}).get("action_steps", []) or [])
                rows.append([row.get("line_number"), row.get("priority"), row.get("syllables"), row.get("rhyme_key"), actions[:145], _safe(row.get("text"))[:160]])
            story.append(_table(rows, [32, 45, 32, 58, 170, 176]))

    doc.build(story)
    return buffer.getvalue()
