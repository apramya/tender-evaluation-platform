"""
Export API routes for report generation
"""
import logging
import json
import re
import textwrap
from io import BytesIO
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from fpdf import FPDF

from app.models.database import Evaluation, Tender, Bidder
from app.schemas.schemas import EmailReportRequest
from app.services.audit_service import AuditService
from app.services.email_service import EmailService
from app.utils.dependencies import get_db, get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


def _pdf_safe(value) -> str:
    text = "" if value is None else str(value)
    text = text.replace("\t", " ")
    text = re.sub(r"[-_]{8,}", " ", text)
    text = re.sub(r"(\S{24})", r"\1 ", text)
    return text.encode("latin-1", errors="replace").decode("latin-1")


def _safe_percent(value) -> str:
    try:
        if isinstance(value, str) and value.strip().endswith("%"):
            return value.strip()
        return f"{float(value or 0):.2%}"
    except (TypeError, ValueError):
        return "N/A"


def _decision_value(decision) -> str:
    return getattr(decision, "value", decision or "unknown")


def _write_label(pdf: FPDF, label: str, value) -> None:
    pdf.set_font("Arial", "B", 9)
    pdf.multi_cell(0, 5, _pdf_safe(label))
    pdf.set_font("Arial", "", 9)
    pdf.multi_cell(0, 5, _pdf_safe(value or "N/A"))


def _write_line(pdf: FPDF, text) -> None:
    pdf.multi_cell(0, 6, _pdf_safe(text))


def _criterion_item(item) -> dict:
    if isinstance(item, dict):
        return item
    return {
        "criterion": str(item),
        "decision": "N/A",
        "confidence": None,
        "reasoning": "Stored criterion result is not in structured format.",
    }


def _plain_report(evaluation: Evaluation, tender: Tender | None, bidder: Bidder | None) -> str:
    lines = [
        "Tender Evaluation Report",
        "",
        "Evaluation Information",
        f"Evaluation ID: {evaluation.id}",
        f"Method: {evaluation.evaluation_method or 'N/A'}",
        f"Evaluated At: {evaluation.evaluated_at or 'N/A'}",
        "",
        "Tender Information",
        f"Tender ID: {getattr(tender, 'id', 'N/A')}",
        f"Tender Number: {getattr(tender, 'tender_number', 'N/A')}",
        f"Title: {getattr(tender, 'title', 'N/A')}",
        "",
        "Bidder Information",
        f"Company: {getattr(bidder, 'company_name', 'N/A')}",
        f"GST: {getattr(bidder, 'gst_number', None) or 'N/A'}",
        f"PAN: {getattr(bidder, 'pan_number', None) or 'N/A'}",
        "",
        "Evaluation Decision",
        f"Decision: {_decision_value(evaluation.overall_decision).upper()}",
        f"Confidence: {_safe_percent(evaluation.overall_confidence)}",
        f"Method: {evaluation.evaluation_method or 'N/A'}",
        f"Evaluated At: {evaluation.evaluated_at or 'N/A'}",
        f"Summary: {evaluation.decision_summary or 'N/A'}",
        "",
        "Criterion-Level Findings",
    ]
    criteria_results = evaluation.criteria_results or []
    if not criteria_results:
        lines.extend([
            "No criterion-level findings are stored for this evaluation.",
            "",
            "This usually means the evaluation was created before criteria extraction completed, the LLM failed to return structured JSON, or the evaluation needs to be re-run.",
            "Use Re-run AI on the Evaluations page, wait for the updated result, then export again.",
        ])
        return "\n".join(lines)

    for index, raw_item in enumerate(criteria_results, start=1):
        item = _criterion_item(raw_item)
        lines.extend([
            "",
            f"{index}. {item.get('criterion', 'Criterion')}",
            f"Decision: {item.get('decision', 'N/A')}",
            f"Confidence: {_safe_percent(item.get('confidence'))}",
            f"Source: {item.get('source_document') or 'N/A'}",
            f"Value: {item.get('extracted_value') or 'N/A'}",
            f"Reasoning: {item.get('reasoning') or 'N/A'}",
            f"Evidence: {item.get('evidence_snippet') or 'N/A'}",
        ])
    return "\n".join(lines)


def _render_pdf_from_text(text: str) -> bytes:
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_margins(12, 12, 12)
    pdf.add_page()
    pdf.set_text_color(0, 0, 0)

    section_titles = {
        "Evaluation Information",
        "Tender Information",
        "Bidder Information",
        "Evaluation Decision",
        "Criterion-Level Findings",
    }

    for line in text.splitlines():
        safe_line = _pdf_safe(line)
        wrapped_lines = textwrap.wrap(
            safe_line,
            width=95,
            break_long_words=True,
            break_on_hyphens=False,
            replace_whitespace=True,
        ) or [""]

        if safe_line == "Tender Evaluation Report":
            pdf.set_font("Helvetica", "B", 14)
            pdf.cell(0, 8, safe_line, ln=1)
            pdf.ln(2)
            continue

        if safe_line in section_titles:
            pdf.ln(2)
            pdf.set_font("Helvetica", "B", 11)
            pdf.cell(0, 7, safe_line, ln=1)
            pdf.set_font("Helvetica", "", 9)
            continue

        pdf.set_font("Helvetica", "", 9)
        for wrapped_line in wrapped_lines:
            pdf.cell(0, 5, wrapped_line, ln=1)
    pdf_output = pdf.output(dest="S")
    return bytes(pdf_output) if isinstance(pdf_output, (bytes, bytearray)) else pdf_output.encode("latin-1")


async def _get_evaluation_report_context(db: AsyncSession, evaluation_id: str):
    result = await db.execute(select(Evaluation).where(Evaluation.id == evaluation_id))
    evaluation = result.scalars().first()

    if not evaluation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evaluation not found",
        )

    tender_result = await db.execute(select(Tender).where(Tender.id == evaluation.tender_id))
    tender = tender_result.scalars().first()

    bidder_result = await db.execute(select(Bidder).where(Bidder.id == evaluation.bidder_id))
    bidder = bidder_result.scalars().first()

    return evaluation, tender, bidder


def _evaluation_pdf_bytes(evaluation: Evaluation, tender: Tender | None, bidder: Bidder | None) -> bytes:
    return _render_pdf_from_text(_plain_report(evaluation, tender, bidder))


@router.get("/evaluation/{evaluation_id}/pdf")
async def export_evaluation_pdf(
    evaluation_id: str,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Export evaluation result as PDF
    """
    try:
        evaluation, tender, bidder = await _get_evaluation_report_context(db, evaluation_id)
        pdf_bytes = _evaluation_pdf_bytes(evaluation, tender, bidder)
        
        AuditService.add_log(
            db,
            user=current_user,
            action="export_evaluation_pdf",
            entity_type="evaluation",
            entity_id=evaluation.id,
            tender_id=evaluation.tender_id,
        )
        await db.commit()

        return StreamingResponse(
            BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="evaluation_{evaluation_id}.pdf"'},
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error exporting PDF")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate PDF",
        )


@router.post("/evaluation/{evaluation_id}/email")
async def email_evaluation_report(
    evaluation_id: str,
    request: EmailReportRequest,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Email evaluation result as a PDF attachment.
    """
    if not EmailService.is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SMTP is not configured. Set SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD and EMAIL_FROM.",
        )

    try:
        evaluation, tender, bidder = await _get_evaluation_report_context(db, evaluation_id)
        pdf_bytes = _evaluation_pdf_bytes(evaluation, tender, bidder)
        bidder_name = getattr(bidder, "company_name", None) or "bidder"
        tender_title = getattr(tender, "title", None) or "tender"
        subject = request.subject or f"TenderEval report: {bidder_name}"
        body = request.message or (
            "Please find attached the TenderEval evaluation report.\n\n"
            f"Tender: {tender_title}\n"
            f"Bidder: {bidder_name}\n"
            f"Decision: {_decision_value(evaluation.overall_decision).replace('_', ' ').title()}\n"
            f"Confidence: {_safe_percent(evaluation.overall_confidence)}\n"
        )
        filename = f"evaluation_{evaluation_id}.pdf"

        EmailService.send_evaluation_report(
            recipients=[str(item) for item in request.recipients],
            cc=[str(item) for item in request.cc or []],
            subject=subject,
            body=body,
            pdf_bytes=pdf_bytes,
            filename=filename,
        )

        AuditService.add_log(
            db,
            user=current_user,
            action="email_evaluation_pdf",
            entity_type="evaluation",
            entity_id=evaluation.id,
            tender_id=evaluation.tender_id,
            details={
                "recipients": [str(item) for item in request.recipients],
                "cc_count": len(request.cc or []),
            },
        )
        await db.commit()

        return {
            "message": "Evaluation report emailed successfully",
            "recipients": [str(item) for item in request.recipients],
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error emailing evaluation report")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to email evaluation report",
        )


@router.get("/evaluation/{evaluation_id}/json")
async def export_evaluation_json(
    evaluation_id: str,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Export evaluation result as JSON
    """
    try:
        result = await db.execute(
            select(Evaluation).where(Evaluation.id == evaluation_id)
        )
        evaluation = result.scalars().first()
        
        if not evaluation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Evaluation not found",
            )
        
        # Prepare JSON response
        export_data = {
            "evaluation_id": evaluation.id,
            "tender_id": evaluation.tender_id,
            "bidder_id": evaluation.bidder_id,
            "overall_decision": _decision_value(evaluation.overall_decision),
            "confidence": evaluation.overall_confidence,
            "criteria_results": evaluation.criteria_results or [],
            "decision_summary": evaluation.decision_summary,
            "is_reviewed": evaluation.is_reviewed,
            "manual_decision": _decision_value(evaluation.manual_decision) if evaluation.manual_decision else None,
            "evaluated_at": evaluation.evaluated_at.isoformat(),
        }
        
        AuditService.add_log(
            db,
            user=current_user,
            action="export_evaluation_json",
            entity_type="evaluation",
            entity_id=evaluation.id,
            tender_id=evaluation.tender_id,
        )
        await db.commit()
        return export_data
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error exporting JSON: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to export JSON",
        )


@router.get("/tender/{tender_id}/comparison")
async def export_tender_comparison(
    tender_id: str,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Export bidder comparison report for a tender
    """
    try:
        # Get all evaluations for tender
        result = await db.execute(
            select(Evaluation).where(Evaluation.tender_id == tender_id)
        )
        evaluations = result.scalars().all()
        
        if not evaluations:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No evaluations found for this tender",
            )
        
        bidder_ids = [e.bidder_id for e in evaluations]
        bidder_result = await db.execute(select(Bidder).where(Bidder.id.in_(bidder_ids)))
        bidders = {bidder.id: bidder for bidder in bidder_result.scalars().all()}

        comparison_data = {
            "tender_id": tender_id,
            "total_bidders": len(evaluations),
            "evaluations": [
                {
                    "evaluation_id": e.id,
                    "bidder_id": e.bidder_id,
                    "company_name": bidders.get(e.bidder_id).company_name if bidders.get(e.bidder_id) else None,
                    "decision": _decision_value(e.overall_decision),
                    "confidence": e.overall_confidence,
                    "is_reviewed": e.is_reviewed,
                    "manual_decision": _decision_value(e.manual_decision) if e.manual_decision else None,
                    "criteria_results": e.criteria_results or [],
                    "decision_summary": e.decision_summary,
                }
                for e in evaluations
            ],
        }
        
        AuditService.add_log(
            db,
            user=current_user,
            action="export_tender_comparison",
            entity_type="tender",
            entity_id=tender_id,
            tender_id=tender_id,
            details={"total_bidders": len(evaluations)},
        )
        await db.commit()
        return comparison_data
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error exporting comparison: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to export comparison",
        )
