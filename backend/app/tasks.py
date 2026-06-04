"""
Background task definitions.

The current API still performs uploads/evaluations synchronously so the user gets
immediate results. These tasks provide the production worker entrypoints for
moving heavy processing out of request/response flow as the workload grows.
"""
import asyncio
import logging

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import sessionmaker

import uuid

from app.models.database import BidderDocument, CriterionType, Tender, TenderCriterion
from app.services.document_processor import DocumentProcessor
from app.services.ai_evaluation_service import AIEvaluationService
from app.services.rule_evaluation_service import RuleEvaluationService
from app.services.storage_service import StorageService
from app.services.vector_service import VectorService
from app.utils.config import settings
from app.worker import celery_app

logger = logging.getLogger(__name__)


async def _session_factory():
    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    try:
        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with async_session() as session:
            yield session
    finally:
        await engine.dispose()


@celery_app.task(name="documents.reindex_tender")
def reindex_tender(tender_id: str) -> dict:
    return asyncio.run(_reindex_tender(tender_id))


async def _reindex_tender(tender_id: str) -> dict:
    async for db in _session_factory():
        tender = await db.get(Tender, tender_id)
        if not tender:
            return {"status": "not_found", "tender_id": tender_id}

        file_path = StorageService.ensure_local_file(tender.file_path, tender.raw_data)
        text, ok = await DocumentProcessor.process_document(file_path, tender.file_type or "")
        tender.extracted_text = text or None
        tender.extraction_status = "completed" if ok else "failed"
        if ok:
            existing_result = await db.execute(
                select(TenderCriterion).where(TenderCriterion.tender_id == tender.id)
            )
            for existing in existing_result.scalars().all():
                await db.delete(existing)

            criteria_data = {"criteria": []}
            try:
                if settings.GROQ_API_KEY:
                    criteria_data = await AIEvaluationService.extract_criteria_from_tender(text)
                    criteria_data["criteria"] = RuleEvaluationService.augment_criteria(
                        criteria_data.get("criteria", []),
                        text,
                    )
                else:
                    criteria_data = {"criteria": []}
            except Exception as e:
                logger.warning(f"Background criteria extraction failed for tender {tender_id}: {e}")
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
                    value=item.get("value"),
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
            text=text or "",
        )
        await db.commit()
        return {"status": tender.extraction_status, "indexed_chunks": indexed_chunks}


@celery_app.task(name="documents.reindex_bidder_document")
def reindex_bidder_document(document_id: str) -> dict:
    return asyncio.run(_reindex_bidder_document(document_id))


async def _reindex_bidder_document(document_id: str) -> dict:
    async for db in _session_factory():
        document = await db.get(BidderDocument, document_id)
        if not document:
            return {"status": "not_found", "document_id": document_id}

        file_path = StorageService.ensure_local_file(document.file_path, document.raw_data)
        text, ok = await DocumentProcessor.process_document(file_path, document.file_type or "")
        document.extracted_text = text or None
        document.extraction_status = "completed" if ok else "failed"
        indexed_chunks = await VectorService.index_text(
            db,
            source_type="bidder_document",
            source_id=document.id,
            text=text or "",
        )
        await db.commit()
        return {"status": document.extraction_status, "indexed_chunks": indexed_chunks}
