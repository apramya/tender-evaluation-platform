"""
Evaluation API routes
"""
import logging
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.database import (
    Bidder,
    BidderDocument,
    CriterionType,
    Evaluation,
    EvaluationStatus,
    EligibilityDecision,
    ReviewQueue,
    Tender,
    TenderCriterion,
)
from app.schemas.schemas import EvaluationCreate, EvaluationResult, CriterionEvaluation
from app.services.audit_service import AuditService
from app.services.ai_evaluation_service import AIEvaluationService
from app.services.document_processor import DocumentProcessor
from app.services.rule_evaluation_service import RuleEvaluationService
from app.services.storage_service import StorageService
from app.services.vector_service import VectorService
from app.utils.dependencies import get_db, get_current_user
from app.utils.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()


def _numeric_value(value):
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@router.post("")
async def create_evaluation(
    eval_data: EvaluationCreate,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Create evaluation for a bidder against tender
    """
    try:
        tender_result = await db.execute(select(Tender).where(Tender.id == eval_data.tender_id))
        tender = tender_result.scalars().first()
        if not tender:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tender not found")

        bidder_result = await db.execute(select(Bidder).where(Bidder.id == eval_data.bidder_id))
        bidder = bidder_result.scalars().first()
        if not bidder:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bidder not found")

        docs_result = await db.execute(
            select(BidderDocument).where(BidderDocument.bidder_id == eval_data.bidder_id)
        )
        documents = docs_result.scalars().all()

        criteria_result = await db.execute(
            select(TenderCriterion).where(TenderCriterion.tender_id == eval_data.tender_id)
        )
        criteria = criteria_result.scalars().all()

        tender_text = tender.extracted_text or ""
        if not tender_text and tender.file_path and tender.file_type:
            tender_file_path = StorageService.ensure_local_file(tender.file_path, tender.raw_data)
            tender_text, tender_ok = await DocumentProcessor.process_document(
                tender_file_path,
                tender.file_type,
            )
            tender.extracted_text = tender_text or None
            tender.extraction_status = "completed" if tender_ok else "failed"

        for doc in documents:
            if not doc.extracted_text and doc.file_path and doc.file_type:
                doc_file_path = StorageService.ensure_local_file(doc.file_path, doc.raw_data)
                doc_text, doc_ok = await DocumentProcessor.process_document(doc_file_path, doc.file_type)
                doc.extracted_text = doc_text or None
                doc.extraction_status = "completed" if doc_ok else "failed"

        bidder_text = "\n\n".join(
            doc.extracted_text or "" for doc in documents if doc.extracted_text
        )

        evaluation_data = {
            "overall_decision": "needs_manual_review",
            "overall_confidence": 0.0,
            "decision_summary": "Automatic evaluation could not run. Manual review is required.",
            "criteria_results": [],
        }

        if tender_text and bidder_text:
            extraction_tender_text = tender_text
            evaluation_tender_text = tender_text
            evaluation_bidder_text = bidder_text

            tender_rag_chunks = await VectorService.query(
                query_text=bidder_text[:4000],
                source_type="tender",
                source_id=tender.id,
                limit=6,
            )
            bidder_rag_chunks = []
            for doc in documents[:5]:
                bidder_rag_chunks.extend(await VectorService.query(
                    query_text=tender_text[:4000],
                    source_type="bidder_document",
                    source_id=doc.id,
                    limit=3,
                ))

            if tender_rag_chunks:
                evaluation_tender_text = evaluation_tender_text + "\n\n[RELEVANT TENDER CHUNKS]\n" + "\n\n".join(tender_rag_chunks)
            if bidder_rag_chunks:
                evaluation_bidder_text = evaluation_bidder_text + "\n\n[RELEVANT BIDDER CHUNKS]\n" + "\n\n".join(bidder_rag_chunks[:10])

            criteria_data = {"criteria": []}
            extraction_metadata = {}
            try:
                criteria_data = await AIEvaluationService.extract_criteria_from_tender(extraction_tender_text)
                extraction_metadata = criteria_data.get("metadata", {})
            except Exception as e:
                logger.warning(f"Tender criteria extraction skipped during evaluation: {e}")

            if criteria_data.get("criteria"):
                criteria_data["criteria"] = AIEvaluationService._dedupe_criteria(
                    criteria_data.get("criteria", [])
                )
            else:
                criteria_data["criteria"] = AIEvaluationService._dedupe_criteria(
                    RuleEvaluationService.augment_criteria([], extraction_tender_text)
                )

            if criteria_data.get("criteria"):
                for existing_criterion in criteria:
                    await db.delete(existing_criterion)
                criteria = []
            elif not criteria:
                evaluation_data["decision_summary"] = (
                    "No tender criteria could be extracted from the uploaded document. "
                    "Manual review is required."
                )

            for item in criteria_data.get("criteria", []):
                criterion_type = item.get("type") or item.get("criterion_type") or "mandatory"
                if criterion_type not in {choice.value for choice in CriterionType}:
                    criterion_type = "mandatory"

                criteria.append(TenderCriterion(
                    id=str(uuid.uuid4()),
                    tender_id=tender.id,
                    criterion_id=item.get("criterion_id") or f"CRIT-{str(uuid.uuid4())[:8]}",
                    criterion_type=CriterionType(criterion_type),
                    description=item.get("description") or "Tender criterion",
                    operator=item.get("operator"),
                    value=_numeric_value(item.get("value")),
                    unit=item.get("unit"),
                    allowed_values=item.get("allowed_values"),
                    is_mandatory=bool(item.get("is_mandatory", True)),
                    source_page=item.get("source_page"),
                    source_text=item.get("source_text"),
                ))
            if criteria_data.get("criteria"):
                db.add_all(criteria)

            criteria_payload = [
                {
                    "criterion": item.description,
                    "operator": item.operator,
                    "value": item.value,
                    "unit": item.unit,
                    "allowed_values": item.allowed_values,
                    "type": item.criterion_type.value,
                    "mandatory": item.is_mandatory,
                }
                for item in criteria
            ]
            if settings.GROQ_API_KEY:
                evaluation_data = await AIEvaluationService.evaluate_bidder_submission(
                    tender_text=evaluation_tender_text,
                    bidder_text=evaluation_bidder_text,
                    tender_criteria=criteria_payload,
                )
            llm_evaluation_used = bool(evaluation_data.pop("_llm_evaluation_used", False))
            rule_results = RuleEvaluationService.evaluate(
                tender_criteria=criteria_payload,
                bidder_text=evaluation_bidder_text,
                documents=documents,
            )
            evaluation_data = RuleEvaluationService.merge_with_ai(evaluation_data, rule_results)
            evaluation_data["criteria_results"] = AIEvaluationService.align_results_to_criteria(
                evaluation_data.get("criteria_results", []),
                criteria_payload,
            )
            evaluation_data = AIEvaluationService.finalize_evaluation_decision(evaluation_data)
            llm_criteria_used = int(
                extraction_metadata.get("llm_used_criteria_count")
                or extraction_metadata.get("llm_raw_criteria_count")
                or 0
            ) > 0
            rule_criteria_used = int(
                extraction_metadata.get("deterministic_used_criteria_count")
                or 0
            ) > 0
            rule_evaluation_used = bool(rule_results)
            method_parts = []
            if llm_criteria_used or llm_evaluation_used:
                method_parts.append("llm")
            if rule_criteria_used or rule_evaluation_used:
                method_parts.append("rules")
            evaluation_data["evaluation_method"] = "+".join(method_parts) if method_parts else "unavailable"
            evaluation_data["decision_summary"] = (
                f"{evaluation_data.get('decision_summary', 'Evaluation completed.')} "
                f"Method: {evaluation_data['evaluation_method']}; "
                f"LLM criteria: {extraction_metadata.get('llm_used_criteria_count', extraction_metadata.get('llm_raw_criteria_count', 0))}, "
                f"rule criteria: {extraction_metadata.get('deterministic_used_criteria_count', 0)}, "
                f"LLM failed sections: {extraction_metadata.get('failed_sections', 0)}."
            )
        elif not tender_text:
            evaluation_data["decision_summary"] = "Tender text has not been extracted. Manual review is required."
        elif not bidder_text:
            evaluation_data["decision_summary"] = "Bidder document text has not been extracted. Manual review is required."

        decision = EligibilityDecision(evaluation_data["overall_decision"])
        existing_eval_result = await db.execute(
            select(Evaluation).where(
                Evaluation.tender_id == eval_data.tender_id,
                Evaluation.bidder_id == eval_data.bidder_id,
            )
        )
        evaluation = existing_eval_result.scalars().first()

        if evaluation:
            evaluation.overall_decision = decision
            evaluation.overall_confidence = evaluation_data["overall_confidence"]
            evaluation.decision_summary = evaluation_data["decision_summary"]
            evaluation.criteria_results = evaluation_data["criteria_results"]
            evaluation.evaluation_method = evaluation_data.get("evaluation_method", "hybrid")
        else:
            evaluation = Evaluation(
                id=str(uuid.uuid4()),
                tender_id=eval_data.tender_id,
                bidder_id=eval_data.bidder_id,
                overall_decision=decision,
                overall_confidence=evaluation_data["overall_confidence"],
                decision_summary=evaluation_data["decision_summary"],
                criteria_results=evaluation_data["criteria_results"],
                evaluation_method=evaluation_data.get("evaluation_method", "hybrid"),
            )
            db.add(evaluation)

        bidder.evaluation_status = (
            EvaluationStatus.MANUAL_REVIEW
            if decision == EligibilityDecision.NEEDS_MANUAL_REVIEW
            else EvaluationStatus.COMPLETED
        )

        if decision == EligibilityDecision.NEEDS_MANUAL_REVIEW:
            queue_result = await db.execute(
                select(ReviewQueue).where(ReviewQueue.evaluation_id == evaluation.id)
            )
            if not queue_result.scalars().first():
                db.add(ReviewQueue(
                    id=str(uuid.uuid4()),
                    evaluation_id=evaluation.id,
                    reason="automatic_evaluation_needs_review",
                    priority=1,
                    status="pending",
            ))

        AuditService.add_log(
            db,
            user=current_user,
            action="create_evaluation",
            entity_type="evaluation",
            entity_id=evaluation.id,
            tender_id=tender.id,
            details={
                "bidder_id": bidder.id,
                "decision": decision.value,
                "confidence": evaluation_data["overall_confidence"],
                "criteria_count": len(evaluation_data["criteria_results"]),
            },
        )
        await db.commit()
        await db.refresh(evaluation)
        
        logger.info(f"Evaluation created: {evaluation.id}")
        
        return {
            "id": evaluation.id,
            "status": "created",
            "message": "Evaluation created.",
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating evaluation: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create evaluation",
        )


@router.get("/{evaluation_id}", response_model=EvaluationResult)
async def get_evaluation(
    evaluation_id: str,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get evaluation result
    """
    result = await db.execute(
        select(Evaluation).where(Evaluation.id == evaluation_id)
    )
    evaluation = result.scalars().first()
    
    if not evaluation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evaluation not found",
        )
    
    # Convert criteria_results from JSON
    criteria_results = []
    if evaluation.criteria_results:
        for cr in evaluation.criteria_results:
            criteria_results.append(CriterionEvaluation(**cr))
    
    return EvaluationResult(
        id=evaluation.id,
        tender_id=evaluation.tender_id,
        bidder_id=evaluation.bidder_id,
        overall_decision=evaluation.overall_decision.value,
        overall_confidence=evaluation.overall_confidence,
        decision_summary=evaluation.decision_summary,
        criteria_results=criteria_results,
        evaluation_method=evaluation.evaluation_method,
        is_reviewed=evaluation.is_reviewed,
        manual_decision=evaluation.manual_decision.value if evaluation.manual_decision else None,
        evaluated_at=evaluation.evaluated_at,
    )


@router.get("")
async def list_evaluations(
    tender_id: str = None,
    bidder_id: str = None,
    decision: str = None,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 10,
):
    """
    List evaluations with filters
    """
    query = select(Evaluation)
    
    if tender_id:
        query = query.where(Evaluation.tender_id == tender_id)
    
    if bidder_id:
        query = query.where(Evaluation.bidder_id == bidder_id)
    
    if decision:
        query = query.where(Evaluation.overall_decision == decision)
    
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    evaluations = result.scalars().all()
    
    return {
        "total": len(evaluations),
        "evaluations": evaluations,
    }


@router.post("/{evaluation_id}/override")
async def override_evaluation(
    evaluation_id: str,
    new_decision: str,
    comments: str = "",
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Override evaluation decision
    """
    result = await db.execute(
        select(Evaluation).where(Evaluation.id == evaluation_id)
    )
    evaluation = result.scalars().first()
    
    if not evaluation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evaluation not found",
        )
    
    try:
        evaluation.manual_decision = EligibilityDecision(new_decision)
        evaluation.is_reviewed = True
        evaluation.review_comments = comments
        AuditService.add_log(
            db,
            user=current_user,
            action="override_evaluation",
            entity_type="evaluation",
            entity_id=evaluation.id,
            tender_id=evaluation.tender_id,
            details={"new_decision": new_decision, "comments": comments},
        )
        
        await db.commit()
        
        logger.info(f"Evaluation overridden: {evaluation_id}")
        
        return {
            "message": "Evaluation overridden successfully",
            "evaluation_id": evaluation.id,
        }
    
    except Exception as e:
        logger.error(f"Error overriding evaluation: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to override evaluation",
        )
