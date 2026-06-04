"""
SQLAlchemy ORM Models for Tender Evaluation Platform
"""
from datetime import datetime
from enum import Enum
from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime, Text, 
    ForeignKey, Enum as SQLEnum, JSON, Index, LargeBinary
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship


Base = declarative_base()


class UserRole(str, Enum):
    """User roles in the system"""
    USER = "user"
    ADMIN = "admin"
    PROCUREMENT_OFFICER = "procurement_officer"


class EvaluationStatus(str, Enum):
    """Status of tender evaluation"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    MANUAL_REVIEW = "manual_review"
    FAILED = "failed"


class EligibilityDecision(str, Enum):
    """Eligibility decision outcomes"""
    ELIGIBLE = "eligible"
    NOT_ELIGIBLE = "not_eligible"
    NEEDS_MANUAL_REVIEW = "needs_manual_review"


class CriterionType(str, Enum):
    """Types of tender criteria"""
    FINANCIAL = "financial"
    TECHNICAL = "technical"
    COMPLIANCE = "compliance"
    MANDATORY = "mandatory"
    OPTIONAL = "optional"


class User(Base):
    """User entity"""
    __tablename__ = "users"
    __table_args__ = (Index("idx_users_email", "email"),)
    
    id = Column(String, primary_key=True)
    email = Column(String, unique=True, nullable=False)
    full_name = Column(String, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(SQLEnum(UserRole), default=UserRole.USER)
    is_active = Column(Boolean, default=True)
    organization = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    tenders = relationship("Tender", back_populates="created_by_user")
    audit_logs = relationship("AuditLog", back_populates="user")
    reviews = relationship("Review", back_populates="reviewing_user")


class EmailVerificationCode(Base):
    """One-time email verification code for public signup"""
    __tablename__ = "email_verification_codes"
    __table_args__ = (
        Index("idx_email_verification_email", "email"),
        Index("idx_email_verification_expires", "expires_at"),
    )

    id = Column(String, primary_key=True)
    email = Column(String, nullable=False)
    code_hash = Column(String, nullable=False)
    full_name = Column(String, nullable=False)
    organization = Column(String, nullable=True)
    password_hash = Column(String, nullable=False)
    attempts = Column(Integer, default=0)
    consumed = Column(Boolean, default=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Tender(Base):
    """Tender document entity"""
    __tablename__ = "tenders"
    __table_args__ = (Index("idx_tenders_created_at", "created_at"),)
    
    id = Column(String, primary_key=True)
    tender_number = Column(String, unique=True, nullable=False)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    file_path = Column(String, nullable=False)
    file_name = Column(String, nullable=False)
    file_type = Column(String, nullable=True)  # pdf, docx, etc
    
    # Content
    extracted_text = Column(Text, nullable=True)
    raw_data = Column(JSON, nullable=True)
    
    # Metadata
    tender_date = Column(DateTime, nullable=True)
    last_date = Column(DateTime, nullable=True)
    issuing_authority = Column(String, nullable=True)
    estimated_value = Column(Float, nullable=True)
    
    # Processing
    extraction_status = Column(String, default="pending")
    extraction_error = Column(Text, nullable=True)
    
    created_by = Column(String, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    created_by_user = relationship("User", back_populates="tenders")
    criteria = relationship("TenderCriterion", back_populates="tender", cascade="all, delete-orphan")
    bidders = relationship("Bidder", back_populates="tender")
    evaluations = relationship("Evaluation", back_populates="tender")
    audit_logs = relationship("AuditLog", back_populates="tender")


class TenderCriterion(Base):
    """Eligibility criteria extracted from tender"""
    __tablename__ = "tender_criteria"
    __table_args__ = (Index("idx_criteria_tender", "tender_id"),)
    
    id = Column(String, primary_key=True)
    tender_id = Column(String, ForeignKey("tenders.id"), nullable=False)
    criterion_id = Column(String, nullable=False)  # e.g., FIN_001
    
    criterion_type = Column(SQLEnum(CriterionType), nullable=False)
    description = Column(String, nullable=False)
    
    # For numeric criteria
    operator = Column(String, nullable=True)  # >=, <=, ==, >, <
    value = Column(Float, nullable=True)
    unit = Column(String, nullable=True)  # crore, percentage, etc
    
    # For text/choice criteria
    allowed_values = Column(JSON, nullable=True)
    
    is_mandatory = Column(Boolean, default=True)
    confidence = Column(Float, default=0.95)
    
    # Source information
    source_page = Column(Integer, nullable=True)
    source_text = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    tender = relationship("Tender", back_populates="criteria")


class Bidder(Base):
    """Bidder entity"""
    __tablename__ = "bidders"
    __table_args__ = (Index("idx_bidders_tender", "tender_id"),)
    
    id = Column(String, primary_key=True)
    tender_id = Column(String, ForeignKey("tenders.id"), nullable=False)
    
    company_name = Column(String, nullable=False)
    gst_number = Column(String, nullable=True, unique=True)
    pan_number = Column(String, nullable=True, unique=True)
    contact_email = Column(String, nullable=True)
    contact_phone = Column(String, nullable=True)
    
    # Extracted data
    extracted_data = Column(JSON, nullable=True)
    
    # Evaluation status
    evaluation_status = Column(
        SQLEnum(EvaluationStatus), 
        default=EvaluationStatus.PENDING
    )
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    tender = relationship("Tender", back_populates="bidders")
    documents = relationship("BidderDocument", back_populates="bidder", cascade="all, delete-orphan")
    evaluations = relationship("Evaluation", back_populates="bidder")
    extracted_fields = relationship("ExtractedField", back_populates="bidder")


class BidderDocument(Base):
    """Documents submitted by bidder"""
    __tablename__ = "bidder_documents"
    __table_args__ = (Index("idx_bidder_docs_bidder", "bidder_id"),)
    
    id = Column(String, primary_key=True)
    bidder_id = Column(String, ForeignKey("bidders.id"), nullable=False)
    
    file_name = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    file_type = Column(String, nullable=True)  # pdf, docx, image, etc
    
    document_type = Column(String, nullable=True)  # balance_sheet, certificate, etc
    
    # Content
    extracted_text = Column(Text, nullable=True)
    raw_data = Column(JSON, nullable=True)
    
    # Processing
    extraction_status = Column(String, default="pending")
    extraction_error = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    bidder = relationship("Bidder", back_populates="documents")


class ExtractedField(Base):
    """Extracted field values from bidder documents"""
    __tablename__ = "extracted_fields"
    __table_args__ = (Index("idx_extracted_bidder", "bidder_id"),)
    
    id = Column(String, primary_key=True)
    bidder_id = Column(String, ForeignKey("bidders.id"), nullable=False)
    
    field_name = Column(String, nullable=False)  # turnover, gst_number, etc
    field_value = Column(String, nullable=False)
    field_type = Column(String, nullable=True)  # string, numeric, date, etc
    
    # Extraction details
    source_document = Column(String, nullable=True)
    confidence = Column(Float, default=0.90)
    extraction_method = Column(String, nullable=True)  # ocr, regex, ai, manual
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    bidder = relationship("Bidder", back_populates="extracted_fields")


class Evaluation(Base):
    """Evaluation result for bidder against tender"""
    __tablename__ = "evaluations"
    __table_args__ = (Index("idx_evaluations_tender", "tender_id"),)
    
    id = Column(String, primary_key=True)
    tender_id = Column(String, ForeignKey("tenders.id"), nullable=False)
    bidder_id = Column(String, ForeignKey("bidders.id"), nullable=False)
    
    # Decision
    overall_decision = Column(SQLEnum(EligibilityDecision), nullable=False)
    overall_confidence = Column(Float, default=0.0)
    
    # Details
    decision_summary = Column(Text, nullable=True)
    criteria_results = Column(JSON, nullable=True)  # List of criterion evaluations
    
    # Metadata
    evaluation_method = Column(String, default="ai")  # ai, manual, hybrid
    evaluated_at = Column(DateTime, default=datetime.utcnow)
    
    # Manual review
    is_reviewed = Column(Boolean, default=False)
    manual_decision = Column(SQLEnum(EligibilityDecision), nullable=True)
    review_comments = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    tender = relationship("Tender", back_populates="evaluations")
    bidder = relationship("Bidder", back_populates="evaluations")


class ReviewQueue(Base):
    """Queue for manual review of evaluations"""
    __tablename__ = "review_queue"
    __table_args__ = (Index("idx_review_queue_status", "status"),)
    
    id = Column(String, primary_key=True)
    evaluation_id = Column(String, unique=True, nullable=False)
    
    reason = Column(String, nullable=False)  # low_confidence, ambiguous_ocr, missing_docs
    priority = Column(Integer, default=0)
    
    status = Column(String, default="pending")  # pending, in_review, completed, rejected
    assigned_to = Column(String, ForeignKey("users.id"), nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Review(Base):
    """Manual review record"""
    __tablename__ = "reviews"
    __table_args__ = (Index("idx_reviews_reviewed_by", "reviewed_by"),)
    
    id = Column(String, primary_key=True)
    evaluation_id = Column(String, nullable=False)
    
    reviewed_by = Column(String, ForeignKey("users.id"), nullable=False)
    decision = Column(SQLEnum(EligibilityDecision), nullable=False)
    comments = Column(Text, nullable=True)
    
    approved = Column(Boolean, default=False)
    overridden = Column(Boolean, default=False)
    
    reviewed_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    reviewing_user = relationship("User", back_populates="reviews")


class AuditLog(Base):
    """Audit log for tracking all actions"""
    __tablename__ = "audit_logs"
    __table_args__ = (Index("idx_audit_logs_timestamp", "timestamp"),)
    
    id = Column(String, primary_key=True)
    
    user_id = Column(String, ForeignKey("users.id"), nullable=True)
    action = Column(String, nullable=False)  # upload, evaluate, review, export
    entity_type = Column(String, nullable=False)  # tender, bidder, evaluation
    entity_id = Column(String, nullable=True)
    
    tender_id = Column(String, ForeignKey("tenders.id"), nullable=True)
    
    details = Column(JSON, nullable=True)
    status = Column(String, default="success")  # success, failure, pending
    error_message = Column(Text, nullable=True)
    
    ip_address = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    
    timestamp = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="audit_logs")
    tender = relationship("Tender", back_populates="audit_logs")


class VectorEmbedding(Base):
    """Store vector embeddings for RAG"""
    __tablename__ = "vector_embeddings"
    __table_args__ = (Index("idx_vector_embeddings_type", "embedding_type"),)
    
    id = Column(String, primary_key=True)
    
    embedding_type = Column(String, nullable=False)  # tender_chunk, bidder_chunk
    source_id = Column(String, nullable=False)  # tender_id or bidder_id
    chunk_text = Column(Text, nullable=False)
    chunk_index = Column(Integer, nullable=True)
    
    embedding_model = Column(String, default="sentence-transformers/all-MiniLM-L6-v2")
    
    # ChromaDB reference
    chromadb_id = Column(String, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
