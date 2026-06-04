"""
Tender API routes
"""
import logging
import uuid
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.models.database import (
    AuditLog,
    Bidder,
    BidderDocument,
    Evaluation,
    ExtractedField,
    Review,
    ReviewQueue,
    Tender,
    TenderCriterion,
    CriterionType,
)
from app.schemas.schemas import TenderCreate, TenderResponse, TenderDetailResponse
from app.services.audit_service import AuditService
from app.services.document_processor import DocumentProcessor
from app.services.ai_evaluation_service import AIEvaluationService
from app.services.rule_evaluation_service import RuleEvaluationService
from app.services.storage_service import StorageService
from app.services.vector_service import VectorService
from app.utils.dependencies import get_db, get_current_user, get_admin_user, get_procurement_user
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


@router.post("/upload")
async def upload_tender(
    file: UploadFile = File(...),
    tender_data: str = "",
    current_user = Depends(get_procurement_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload a tender document
    """
    try:
        # Validate file
        if not file.filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No file provided",
            )
        
        # Get file extension
        file_ext = file.filename.split('.')[-1].lower()
        if file_ext not in settings.ALLOWED_FILE_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File type {file_ext} not allowed",
            )
        
        # Save file
        storage = await StorageService.save_upload(
            file_obj=file,
            original_filename=file.filename,
            kind="tender",
            file_ext=file_ext,
        )
        tender_id = storage["id"]
        file_path = storage["local_path"]
        
        # Create tender record
        tender = Tender(
            id=tender_id,
            tender_number=f"TENDER-{tender_id[:8]}",
            title=file.filename,
            file_path=file_path,
            file_name=file.filename,
            file_type=file_ext,
            created_by=current_user.id,
            extraction_status="pending",
            raw_data={
                "storage_backend": storage["storage_backend"],
                "s3_bucket": storage["s3_bucket"],
                "s3_key": storage["s3_key"],
            },
        )
        
        db.add(tender)
        await db.commit()
        await db.refresh(tender)
        
        logger.info(f"Tender uploaded: {tender_id}")
        indexed_chunks = 0

        if settings.PROCESS_UPLOADS_ON_REQUEST:
            # Optional synchronous processing for small local demos.
            extracted_text, extraction_ok = await DocumentProcessor.process_document(file_path, file_ext)
            tender.extracted_text = extracted_text or None
            tender.extraction_status = "completed" if extraction_ok else "failed"

            if extraction_ok:
                try:
                    if settings.GROQ_API_KEY:
                        criteria_data = await AIEvaluationService.extract_criteria_from_tender(extracted_text)
                        if criteria_data.get("criteria"):
                            criteria_data["criteria"] = AIEvaluationService._dedupe_criteria(
                                criteria_data.get("criteria", [])
                            )
                        else:
                            criteria_data["criteria"] = AIEvaluationService._dedupe_criteria(
                                RuleEvaluationService.augment_criteria([], extracted_text)
                            )
                    else:
                        criteria_data = {"criteria": []}
                except Exception as e:
                    logger.warning(f"Tender AI criteria extraction skipped after upload: {e}")
                    criteria_data = {"criteria": []}

                for item in criteria_data.get("criteria", []):
                    criterion_type = item.get("type") or item.get("criterion_type") or "mandatory"
                    if criterion_type not in {choice.value for choice in CriterionType}:
                        criterion_type = "mandatory"

                    db.add(TenderCriterion(
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

            indexed_chunks = await VectorService.index_text(
                db,
                source_type="tender",
                source_id=tender.id,
                text=extracted_text or "",
            )
            await db.commit()
        else:
            try:
                from app.tasks import reindex_tender

                reindex_tender.delay(tender.id)
                tender.extraction_status = "queued"
                await db.commit()
            except Exception as e:
                logger.warning(f"Tender background processing was not queued: {e}")
        
        AuditService.add_log(
            db,
            user=current_user,
            action="upload_tender",
            entity_type="tender",
            entity_id=tender.id,
            tender_id=tender.id,
            details={
                "file_name": tender.file_name,
                "file_type": tender.file_type,
                "extraction_status": tender.extraction_status,
                "indexed_chunks": indexed_chunks,
                "storage_backend": tender.raw_data.get("storage_backend") if tender.raw_data else "local",
            },
        )
        await db.commit()

        return {
            "id": tender.id,
            "status": "uploaded",
            "message": "Tender uploaded successfully. Processing will continue in the background."
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading tender: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upload tender",
        )


@router.get("/{tender_id}", response_model=TenderDetailResponse)
async def get_tender(
    tender_id: str,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get tender details
    """
    result = await db.execute(
        select(Tender).options(selectinload(Tender.criteria)).where(Tender.id == tender_id)
    )
    tender = result.scalars().first()
    
    if not tender:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tender not found",
        )
    
    return tender


@router.get("")
async def list_tenders(
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 10,
):
    """
    List all tenders
    """
    result = await db.execute(
        select(Tender).options(selectinload(Tender.criteria)).offset(skip).limit(limit)
    )
    tenders = result.scalars().all()
    
    return {
        "total": len(tenders),
        "tenders": tenders,
    }


@router.delete("/{tender_id}")
async def delete_tender(
    tender_id: str,
    current_user = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Delete a tender (admin only)
    """
    result = await db.execute(
        select(Tender).where(Tender.id == tender_id)
    )
    tender = result.scalars().first()
    
    if not tender:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tender not found",
        )
    
    docs_result = await db.execute(
        select(BidderDocument)
        .join(Bidder, BidderDocument.bidder_id == Bidder.id)
        .where(Bidder.tender_id == tender_id)
    )
    for document in docs_result.scalars().all():
        StorageService.delete_file(document.file_path, document.raw_data)

    eval_result = await db.execute(select(Evaluation).where(Evaluation.tender_id == tender_id))
    evaluations = eval_result.scalars().all()
    for evaluation in evaluations:
        queue_result = await db.execute(select(ReviewQueue).where(ReviewQueue.evaluation_id == evaluation.id))
        for queue_item in queue_result.scalars().all():
            await db.delete(queue_item)
        review_result = await db.execute(select(Review).where(Review.evaluation_id == evaluation.id))
        for review in review_result.scalars().all():
            await db.delete(review)
        await db.delete(evaluation)

    bidders_result = await db.execute(select(Bidder).where(Bidder.tender_id == tender_id))
    for bidder in bidders_result.scalars().all():
        fields_result = await db.execute(select(ExtractedField).where(ExtractedField.bidder_id == bidder.id))
        for field in fields_result.scalars().all():
            await db.delete(field)
        bidder_docs_result = await db.execute(select(BidderDocument).where(BidderDocument.bidder_id == bidder.id))
        for document in bidder_docs_result.scalars().all():
            await db.delete(document)
        await db.delete(bidder)

    criteria_result = await db.execute(select(TenderCriterion).where(TenderCriterion.tender_id == tender_id))
    for criterion in criteria_result.scalars().all():
        await db.delete(criterion)

    StorageService.delete_file(tender.file_path, tender.raw_data)

    audit_result = await db.execute(select(AuditLog).where(AuditLog.tender_id == tender_id))
    for log in audit_result.scalars().all():
        log.tender_id = None

    await db.delete(tender)
    AuditService.add_log(
        db,
        user=current_user,
        action="delete_tender",
        entity_type="tender",
        entity_id=tender_id,
    )
    await db.commit()
    
    return {"message": "Tender deleted successfully"}
