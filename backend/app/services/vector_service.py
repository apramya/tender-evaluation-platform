"""
Vector indexing and retrieval using ChromaDB and sentence-transformers.
"""
import logging
import hashlib
import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.database import VectorEmbedding
from app.services.document_processor import DocumentProcessor
from app.utils.config import settings

logger = logging.getLogger(__name__)


class VectorService:
    """Optional RAG/vector-search service."""

    _client = None
    _collection = None
    _model = None

    @classmethod
    def enabled(cls) -> bool:
        return settings.VECTOR_SEARCH_ENABLED

    @classmethod
    def _get_model(cls):
        if cls._model is None:
            from sentence_transformers import SentenceTransformer

            cls._model = SentenceTransformer(settings.EMBEDDINGS_MODEL)
        return cls._model

    @staticmethod
    def _fallback_embedding(text: str, dimensions: int = 384) -> List[float]:
        vector = [0.0] * dimensions
        words = text.lower().split()
        for word in words:
            digest = hashlib.sha256(word.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign

        norm = sum(value * value for value in vector) ** 0.5
        if norm == 0:
            return vector
        return [value / norm for value in vector]

    @classmethod
    def _encode_texts(cls, texts: List[str]) -> List[List[float]]:
        try:
            model = cls._get_model()
            return model.encode(texts, normalize_embeddings=True).tolist()
        except ImportError:
            logger.warning("sentence-transformers is not installed; using fallback vector embeddings")
            return [cls._fallback_embedding(text) for text in texts]
        except Exception as e:
            logger.warning("sentence-transformers embedding failed; using fallback embeddings: %s", e)
            return [cls._fallback_embedding(text) for text in texts]

    @classmethod
    def _get_collection(cls):
        if cls._collection is None:
            import chromadb

            cls._client = chromadb.PersistentClient(path=settings.CHROMA_PERSIST_DIR)
            cls._collection = cls._client.get_or_create_collection("tender_documents")
        return cls._collection

    @classmethod
    async def index_text(
        cls,
        db: AsyncSession,
        *,
        source_type: str,
        source_id: str,
        text: str,
    ) -> int:
        if not cls.enabled() or not text:
            return 0

        try:
            collection = cls._get_collection()
            chunks = [
                chunk.strip()
                for chunk in DocumentProcessor.chunk_text(text)
                if chunk.strip()
            ]
            if not chunks:
                return 0

            existing = await db.execute(
                select(VectorEmbedding).where(VectorEmbedding.source_id == source_id)
            )
            for row in existing.scalars().all():
                await db.delete(row)

            try:
                collection.delete(where={"source_id": source_id})
            except Exception:
                logger.debug("No existing Chroma records to delete for %s", source_id)

            embeddings = cls._encode_texts(chunks)
            ids = [str(uuid.uuid4()) for _ in chunks]
            metadatas: List[Dict[str, Any]] = [
                {
                    "source_type": source_type,
                    "source_id": source_id,
                    "chunk_index": index,
                }
                for index, _ in enumerate(chunks)
            ]

            collection.add(
                ids=ids,
                documents=chunks,
                embeddings=embeddings,
                metadatas=metadatas,
            )

            for index, chunk in enumerate(chunks):
                db.add(VectorEmbedding(
                    id=str(uuid.uuid4()),
                    embedding_type=source_type,
                    source_id=source_id,
                    chunk_text=chunk,
                    chunk_index=index,
                    embedding_model=settings.EMBEDDINGS_MODEL,
                    chromadb_id=ids[index],
                ))

            return len(chunks)
        except Exception as e:
            logger.warning("Vector indexing skipped for %s/%s: %s", source_type, source_id, e)
            return 0

    @classmethod
    async def query(
        cls,
        *,
        query_text: str,
        source_type: Optional[str] = None,
        source_id: Optional[str] = None,
        limit: int = 5,
    ) -> List[str]:
        if not cls.enabled() or not query_text:
            return []

        try:
            collection = cls._get_collection()
            embedding = cls._encode_texts([query_text])[0]
            where: Dict[str, str] = {}
            if source_type:
                where["source_type"] = source_type
            if source_id:
                where["source_id"] = source_id

            result = collection.query(
                query_embeddings=[embedding],
                n_results=limit,
                where=where or None,
            )
            documents = result.get("documents") or []
            return documents[0] if documents else []
        except Exception as e:
            logger.warning("Vector query skipped: %s", e)
            return []
