from io import BytesIO
from datetime import datetime, timezone
import xml.sax.saxutils as saxutils

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.schemas.report import ReportView


def _escape(text: str | None) -> str:
    if text is None:
        return ""
    return saxutils.escape(str(text))


def _to_utc(ts: datetime) -> datetime:
    # Naive datetimes are treated as already being in UTC.
    return ts.astimezone(timezone.utc) if ts.tzinfo is not None else ts


def _fmt_timestamp(ts: datetime) -> str:
    return _to_utc(ts).strftime("%Y-%m-%d %H:%M UTC")


def _fmt_date(ts: datetime) -> str:
    return _to_utc(ts).strftime("%Y-%m-%d")


def _make_page_callback(view: ReportView):
    def callback(canvas, doc):
        canvas.saveState()

        # Header for demo data
        if view.is_demo_data:
            canvas.setFont("Helvetica-Bold", 8)
            canvas.setFillColor(colors.HexColor("#b91c1c"))
            canvas.drawCentredString(
                A4[0] / 2.0, A4[1] - 1.2 * cm, "DEMO DATA — not a real assessment"
            )

        # Footer on every page
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#475569"))
        timestamp_str = _fmt_timestamp(view.generated_at)

        footer_y = 1.0 * cm
        canvas.drawString(2 * cm, footer_y, "Agentic GRC — Confidential")
        canvas.drawCentredString(A4[0] / 2.0, footer_y, timestamp_str)
        canvas.drawRightString(
            A4[0] - 2 * cm, footer_y, f"Page {canvas.getPageNumber()}"
        )

        canvas.restoreState()

    return callback


def render_report_pdf(view: ReportView) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )

    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        textColor=colors.HexColor("#0f172a"),
        alignment=0,
        spaceAfter=6,
    )
    subtitle_style = ParagraphStyle(
        "ReportSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=12,
        leading=16,
        textColor=colors.HexColor("#334155"),
        spaceAfter=4,
    )
    timestamp_style = ParagraphStyle(
        "ReportTimestamp",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#64748b"),
        spaceAfter=10,
    )
    section_heading_style = ParagraphStyle(
        "ReportSectionHeading",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=17,
        textColor=colors.HexColor("#0f172a"),
        spaceBefore=14,
        spaceAfter=8,
        keepWithNext=True,
    )
    body_style = ParagraphStyle(
        "ReportBody",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#1e293b"),
        spaceAfter=6,
    )
    italic_style = ParagraphStyle(
        "ReportItalic",
        parent=body_style,
        fontName="Helvetica-Oblique",
        textColor=colors.HexColor("#475569"),
    )
    notice_style = ParagraphStyle(
        "ReportNotice",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#b45309"),
        backColor=colors.HexColor("#fef3c7"),
        borderColor=colors.HexColor("#f59e0b"),
        borderWidth=0.5,
        borderPadding=6,
        spaceBefore=6,
        spaceAfter=12,
    )
    table_cell_style = ParagraphStyle(
        "TableCell",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=11.5,
        textColor=colors.HexColor("#1e293b"),
    )
    table_cell_bold = ParagraphStyle(
        "TableCellBold",
        parent=table_cell_style,
        fontName="Helvetica-Bold",
        textColor=colors.HexColor("#0f172a"),
    )
    table_header_style = ParagraphStyle(
        "TableHeader",
        parent=table_cell_style,
        fontName="Helvetica-Bold",
        fontSize=8.5,
        leading=11.5,
        textColor=colors.HexColor("#0f172a"),
    )
    result_heading_style = ParagraphStyle(
        "ResultHeading",
        parent=styles["Heading3"],
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#0f172a"),
        spaceBefore=8,
        spaceAfter=3,
        keepWithNext=True,
    )

    story = []

    # 1. Title block (the DEMO DATA notice is drawn in the page header by the page callback)
    story.append(Paragraph("NIST CSF 2.0 Assessment Report", title_style))
    story.append(Paragraph(_escape(view.organization.name), subtitle_style))
    story.append(Paragraph(_escape(view.assessment.title), subtitle_style))
    story.append(Paragraph(f"Generated {_fmt_timestamp(view.generated_at)}", timestamp_style))

    if view.summary.pending > 0:
        notice_text = (
            f"This report contains {view.summary.pending} control(s) pending expert review. "
            "They are listed separately and are not presented as final results."
        )
        story.append(Paragraph(notice_text, notice_style))

    story.append(Spacer(1, 8))

    # Standard table style for grid tables
    grid_table_style = TableStyle(
        [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]
    )

    kv_table_style = TableStyle(
        [
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f8fafc")),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]
    )

    # 2. "1. Organization and assessment"
    story.append(Paragraph("1. Organization and assessment", section_heading_style))

    started_str = _fmt_timestamp(view.assessment.started_at) if view.assessment.started_at else "—"
    completed_str = _fmt_timestamp(view.assessment.completed_at) if view.assessment.completed_at else "—"

    org_assessment_data = [
        [Paragraph("Organization", table_cell_bold), Paragraph(_escape(view.organization.name), table_cell_style)],
        [Paragraph("Sector", table_cell_bold), Paragraph(_escape(view.organization.sector), table_cell_style)],
        [Paragraph("Size", table_cell_bold), Paragraph(_escape(view.organization.size), table_cell_style)],
        [Paragraph("Assessment", table_cell_bold), Paragraph(_escape(view.assessment.title), table_cell_style)],
        [Paragraph("Framework", table_cell_bold), Paragraph(_escape(view.assessment.framework), table_cell_style)],
        [Paragraph("Knowledge base version", table_cell_bold), Paragraph(_escape(view.assessment.kb_version), table_cell_style)],
        [Paragraph("Assessment status", table_cell_bold), Paragraph(_escape(view.assessment.status), table_cell_style)],
        [Paragraph("Started", table_cell_bold), Paragraph(_escape(started_str), table_cell_style)],
        [Paragraph("Completed", table_cell_bold), Paragraph(_escape(completed_str), table_cell_style)],
    ]
    org_table = Table(org_assessment_data, colWidths=[5.0 * cm, 12.0 * cm])
    org_table.setStyle(kv_table_style)
    story.append(org_table)
    story.append(Spacer(1, 10))

    # 3. "2. Scope"
    story.append(Paragraph("2. Scope", section_heading_style))
    scope_intro = (
        f"This assessment covers {len(view.scope)} NIST CSF 2.0 subcategories. "
        "Only results reviewed by an Aligo consultant are presented as final."
    )
    story.append(Paragraph(scope_intro, body_style))

    scope_data = [
        [Paragraph("Control", table_header_style), Paragraph("Name", table_header_style)]
    ]
    for item in view.scope:
        scope_data.append(
            [
                Paragraph(_escape(item.code), table_cell_bold),
                Paragraph(_escape(item.title), table_cell_style),
            ]
        )
    scope_table = Table(scope_data, colWidths=[3.0 * cm, 14.0 * cm], repeatRows=1)
    scope_table.setStyle(grid_table_style)
    story.append(scope_table)
    story.append(Spacer(1, 10))

    # 4. "3. Summary"
    story.append(Paragraph("3. Summary", section_heading_style))
    summary_data = [
        [Paragraph("Controls in scope", table_cell_bold), Paragraph(str(view.summary.controls_in_scope), table_cell_style)],
        [Paragraph("Final results", table_cell_bold), Paragraph(str(len(view.results)), table_cell_style)],
        [Paragraph("Exclusions", table_cell_bold), Paragraph(str(len(view.exclusions)), table_cell_style)],
        [Paragraph("Pending review", table_cell_bold), Paragraph(str(view.summary.pending), table_cell_style)],
        [Paragraph("Coverage", table_cell_bold), Paragraph(f"{view.summary.coverage_pct}%", table_cell_style)],
        [Paragraph("Implemented", table_cell_bold), Paragraph(str(view.summary.status_counts.get("implemented", 0)), table_cell_style)],
        [Paragraph("Partially implemented", table_cell_bold), Paragraph(str(view.summary.status_counts.get("partially_implemented", 0)), table_cell_style)],
        [Paragraph("Not implemented", table_cell_bold), Paragraph(str(view.summary.status_counts.get("not_implemented", 0)), table_cell_style)],
        [Paragraph("Not assessed", table_cell_bold), Paragraph(str(view.summary.status_counts.get("not_assessed", 0)), table_cell_style)],
    ]
    summary_table = Table(summary_data, colWidths=[7.0 * cm, 10.0 * cm])
    summary_table.setStyle(kv_table_style)
    story.append(summary_table)
    story.append(Spacer(1, 10))

    # 5. "4. Reviewed results"
    story.append(Paragraph("4. Reviewed results", section_heading_style))
    if not view.results:
        story.append(Paragraph("No reviewed results yet.", italic_style))
    else:
        results_data = [
            [
                Paragraph("Control", table_header_style),
                Paragraph("Name", table_header_style),
                Paragraph("Status", table_header_style),
                Paragraph("Reviewed by", table_header_style),
            ]
        ]
        for res in view.results:
            basis_text = "accepted" if res.basis == "accepted_agent_result" else "consultant version"
            rev_date = _fmt_date(res.reviewed_at)
            reviewed_by_str = f"{res.reviewed_by} ({basis_text}), {rev_date}"

            results_data.append(
                [
                    Paragraph(_escape(res.code), table_cell_bold),
                    Paragraph(_escape(res.title), table_cell_style),
                    Paragraph(_escape(res.status_label), table_cell_style),
                    Paragraph(_escape(reviewed_by_str), table_cell_style),
                ]
            )
        # Status column must be at least 4.2 cm wide
        results_table = Table(results_data, colWidths=[2.4 * cm, 5.2 * cm, 4.4 * cm, 5.0 * cm], repeatRows=1)
        results_table.setStyle(grid_table_style)
        story.append(results_table)
        story.append(Spacer(1, 10))

        # Detail block for each result
        for res in view.results:
            heading_text = f"{_escape(res.code)} — {_escape(res.status_label)}"
            story.append(Paragraph(heading_text, result_heading_style))

            story.append(Paragraph(_escape(res.explanation), body_style))

            if res.control_status == "not_assessed" and res.not_assessed_reason:
                story.append(
                    Paragraph(f"Reason not assessed: {_escape(res.not_assessed_reason)}", body_style)
                )

            if res.evidence_pending:
                story.append(
                    Paragraph(
                        "Evidence pending validation: this status relies on a statement that has not yet been verified.",
                        italic_style,
                    )
                )

            story.append(Paragraph("<b>Evidence</b>", body_style))
            if not res.evidence:
                story.append(Paragraph("No evidence on file.", italic_style))
            else:
                for ev in res.evidence:
                    ev_text = f"[{_escape(ev.nature)}] {_escape(ev.reference)}"
                    if ev.excerpt:
                        ev_text += f' — <i>"{_escape(ev.excerpt)}"</i>'
                    story.append(Paragraph(ev_text, body_style))

            story.append(Spacer(1, 6))

    story.append(Spacer(1, 8))

    # 6. "5. Pending review"
    story.append(Paragraph("5. Pending review", section_heading_style))
    if not view.pending:
        story.append(Paragraph("No items pending review.", italic_style))
    else:
        pending_data = [
            [
                Paragraph("Control", table_header_style),
                Paragraph("Name", table_header_style),
                Paragraph("Reason", table_header_style),
            ]
        ]
        for pend in view.pending:
            pending_data.append(
                [
                    Paragraph(_escape(pend.code), table_cell_bold),
                    Paragraph(_escape(pend.title), table_cell_style),
                    Paragraph(_escape(pend.reason_label), table_cell_style),
                ]
            )
        pending_table = Table(pending_data, colWidths=[2.5 * cm, 7.5 * cm, 7.0 * cm], repeatRows=1)
        pending_table.setStyle(grid_table_style)
        story.append(pending_table)

    story.append(Spacer(1, 10))

    # 7. "6. Exclusions (not applicable)"
    story.append(Paragraph("6. Exclusions (not applicable)", section_heading_style))
    if not view.exclusions:
        story.append(Paragraph("No exclusions.", italic_style))
    else:
        exclusions_data = [
            [
                Paragraph("Control", table_header_style),
                Paragraph("Name", table_header_style),
                Paragraph("Justification", table_header_style),
                Paragraph("Approved by", table_header_style),
            ]
        ]
        for exc in view.exclusions:
            app_date = _fmt_date(exc.reviewed_at)
            approved_by_str = f"{exc.reviewed_by}, {app_date}"
            exclusions_data.append(
                [
                    Paragraph(_escape(exc.code), table_cell_bold),
                    Paragraph(_escape(exc.title), table_cell_style),
                    Paragraph(_escape(exc.justification), table_cell_style),
                    Paragraph(_escape(approved_by_str), table_cell_style),
                ]
            )
        exclusions_table = Table(exclusions_data, colWidths=[2.5 * cm, 5.0 * cm, 5.5 * cm, 4.0 * cm], repeatRows=1)
        exclusions_table.setStyle(grid_table_style)
        story.append(exclusions_table)

    page_callback = _make_page_callback(view)
    doc.build(story, onFirstPage=page_callback, onLaterPages=page_callback)

    return buffer.getvalue()
