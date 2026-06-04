"""
Bidder API routes
"""
import logging
import re
import uuid
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import or_

from app.models.database import AuditLog, Bidder, BidderDocument, Evaluation, ExtractedField, Review, ReviewQueue
from app.schemas.schemas import BidderCreate, BidderResponse, BidderDetailResponse
from app.services.audit_service import AuditService
from app.services.ai_evaluation_service import AIEvaluationService
from app.services.document_processor import DocumentProcessor
from app.services.storage_service import StorageService
from app.services.vector_service import VectorService
from app.utils.dependencies import get_db, get_current_user
from app.utils.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()


def _normalize_alnum(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", value.upper())


def _validate_bidder_document_matches_form(bidder: Bidder, extracted_text: str) -> list[str]:
    text = extracted_text or ""
    normalized_text = _normalize_alnum(text)
    mismatches = []

    if bidder.gst_number:
        expected = _normalize_alnum(bidder.gst_number)
        found = re.findall(r"\b[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]\b", text.upper())
        if found and expected not in [_normalize_alnum(item) for item in found]:
            mismatches.append(f"GST number does not match uploaded document. Entered {bidder.gst_number}, found {', '.join(found[:3])}.")

    if bidder.pan_number:
        expected = _normalize_alnum(bidder.pan_number)
        found = re.findall(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b", text.upper())
        if found and expected not in [_normalize_alnum(item) for item in found]:
            mismatches.append(f"PAN number does not match uploaded document. Entered {bidder.pan_number}, found {', '.join(found[:3])}.")

    if bidder.contact_email:
        expected = bidder.contact_email.lower().strip()
        found = re.findall(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", text, flags=re.IGNORECASE)
        if found and expected not in [item.lower() for item in found]:
            mismatches.append(f"Contact email does not match uploaded document. Entered {bidder.contact_email}, found {', '.join(found[:3])}.")

    company_tokens = [token for token in re.findall(r"[A-Z0-9]{3,}", bidder.company_name.upper()) if token not in {"PVT", "LTD", "LIMITED", "PRIVATE", "COMPANY"}]
    if company_tokens:
        matched = sum(1 for token in company_tokens if token in normalized_text)
        if len(company_tokens) >= 2 and matched == 0:
            mismatches.append("Company name entered during upload was not found in the uploaded bidder document.")

    return mismatches


@router.post("")
async def create_bidder(
    bidder_data: BidderCreate,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new bidder record
    """
    try:
        duplicate_filters = []
        if bidder_data.gst_number:
            duplicate_filters.append(Bidder.gst_number == bidder_data.gst_number)
        if bidder_data.pan_number:
            duplicate_filters.append(Bidder.pan_number == bidder_data.pan_number)

        if duplicate_filters:
            result = await db.execute(select(Bidder).where(or_(*duplicate_filters)))
            existing_bidder = result.scalars().first()
            if existing_bidder:
                if existing_bidder.tender_id == bidder_data.tender_id:
                    logger.info(f"Existing bidder reused: {existing_bidder.id}")
                    return existing_bidder

                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="A bidder with this GST or PAN already exists for another tender",
                )

        bidder = Bidder(
            id=str(uuid.uuid4()),
            **bidder_data.dict(),
        )
        
        db.add(bidder)
        await db.commit()
        await db.refresh(bidder)
        AuditService.add_log(
            db,
            user=current_user,
            action="create_bidder",
            entity_type="bidder",
            entity_id=bidder.id,
            tender_id=bidder.tender_id,
            details={"company_name": bidder.company_name},
        )
        await db.commit()
        
        logger.info(f"Bidder created: {bidder.id}")
        
        return bidder
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating bidder: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create bidder",
        )


@router.post("/{bidder_id}/upload-document")
async def upload_bidder_document(
    bidder_id: str,
    file: UploadFile = File(...),
    document_type: str = Form(""),
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload document for a bidder
    """
    try:
        # Validate file
        if not file.filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No file provided",
            )
        
        # Check bidder exists
        result = await db.execute(
            select(Bidder).where(Bidder.id == bidder_id)
        )
        bidder = result.scalars().first()
        
        if not bidder:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Bidder not found",
            )
        
        file_ext = file.filename.split('.')[-1].lower()
        storage = await StorageService.save_upload(
            file_obj=file,
            original_filename=file.filename,
            kind="bidder_doc",
            file_ext=file_ext,
        )
        doc_id = storage["id"]
        file_path = storage["local_path"]
        
        extracted_text, extraction_ok = await DocumentProcessor.process_document(file_path, file_ext)
        if extraction_ok:
            mismatches = _validate_bidder_document_matches_form(bidder, extracted_text)
            if mismatches:
                StorageService.delete_file(file_path, storage)
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=" ".join(mismatches),
                )

        # Create document record
        document = BidderDocument(
            id=doc_id,
            bidder_id=bidder_id,
            file_name=file.filename,
            file_path=file_path,
            file_type=file_ext,
            document_type=document_type,
            extracted_text=extracted_text or None,
            raw_data={
                "storage_backend": storage["storage_backend"],
                "s3_bucket": storage["s3_bucket"],
                "s3_key": storage["s3_key"],
            },
            extraction_status="completed" if extraction_ok else "failed",
        )
        
        db.add(document)

        if extraction_ok and settings.GROQ_API_KEY:
            try:
                bidder.extracted_data = await AIEvaluationService.extract_bidder_data(extracted_text)
            except Exception as e:
                logger.warning(f"Bidder AI extraction skipped after upload: {e}")

        indexed_chunks = await VectorService.index_text(
            db,
            source_type="bidder_document",
            source_id=document.id,
            text=extracted_text or "",
        )
        await db.commit()
        AuditService.add_log(
            db,
            user=current_user,
            action="upload_bidder_document",
            entity_type="bidder_document",
            entity_id=document.id,
            tender_id=bidder.tender_id,
            details={
                "bidder_id": bidder_id,
                "file_name": document.file_name,
                "file_type": document.file_type,
                "document_type": document.document_type,
                "extraction_status": document.extraction_status,
                "indexed_chunks": indexed_chunks,
                "storage_backend": document.raw_data.get("storage_backend") if document.raw_data else "local",
            },
        )
        await db.commit()
        
        logger.info(f"Bidder document uploaded: {doc_id}")
        
        return {
            "id": document.id,
            "status": "uploaded",
            "message": "Document uploaded successfully",
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading bidder document: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upload document",
        )


@router.get("/{bidder_id}", response_model=BidderDetailResponse)
async def get_bidder(
    bidder_id: str,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get bidder details
    """
    result = await db.execute(
        select(Bidder).where(Bidder.id == bidder_id)
    )
    bidder = result.scalars().first()
    
    if not bidder:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bidder not found",
        )
    
    return bidder


@router.get("")
async def list_bidders(
    tender_id: str = None,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 10,
):
    """
    List bidders
    """
    query = select(Bidder)
    
    if tender_id:
        query = query.where(Bidder.tender_id == tender_id)
    
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    bidders = result.scalars().all()
    
    return {
        "total": len(bidders),
        "bidders": bidders,
    }


@router.delete("/{bidder_id}/documents/{document_id}")
async def delete_bidder_document(
    bidder_id: str,
    document_id: str,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(BidderDocument).where(
            BidderDocument.id == document_id,
            BidderDocument.bidder_id == bidder_id,
        )
    )
    document = result.scalars().first()
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    bidder = await db.get(Bidder, bidder_id)
    StorageService.delete_file(document.file_path, document.raw_data)
    await db.delete(document)
    AuditService.add_log(
        db,
        user=current_user,
        action="delete_bidder_document",
        entity_type="bidder_document",
        entity_id=document_id,
        tender_id=bidder.tender_id if bidder else None,
        details={"bidder_id": bidder_id, "file_name": document.file_name},
    )
    await db.commit()
    return {"message": "Document deleted successfully"}


@router.delete("/{bidder_id}")
async def delete_bidder(
    bidder_id: str,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    bidder = await db.get(Bidder, bidder_id)
    if not bidder:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bidder not found")

    docs_result = await db.execute(select(BidderDocument).where(BidderDocument.bidder_id == bidder_id))
    for document in docs_result.scalars().all():
        StorageService.delete_file(document.file_path, document.raw_data)
        await db.delete(document)

    fields_result = await db.execute(select(ExtractedField).where(ExtractedField.bidder_id == bidder_id))
    for field in fields_result.scalars().all():
        await db.delete(field)

    eval_result = await db.execute(select(Evaluation).where(Evaluation.bidder_id == bidder_id))
    for evaluation in eval_result.scalars().all():
        queue_result = await db.execute(select(ReviewQueue).where(ReviewQueue.evaluation_id == evaluation.id))
        for queue_item in queue_result.scalars().all():
            await db.delete(queue_item)
        review_result = await db.execute(select(Review).where(Review.evaluation_id == evaluation.id))
        for review in review_result.scalars().all():
            await db.delete(review)
        await db.delete(evaluation)

    audit_result = await db.execute(select(AuditLog).where(AuditLog.entity_id == bidder_id))
    for log in audit_result.scalars().all():
        log.entity_id = None

    tender_id = bidder.tender_id
    company_name = bidder.company_name
    await db.delete(bidder)
    AuditService.add_log(
        db,
        user=current_user,
        action="delete_bidder",
        entity_type="bidder",
        entity_id=bidder_id,
        tender_id=tender_id,
        details={"company_name": company_name},
    )
    await db.commit()
    return {"message": "Bidder deleted successfully"}
