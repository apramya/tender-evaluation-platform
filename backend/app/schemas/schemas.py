"""
Pydantic schemas for request/response validation
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, EmailStr, Field


# ==================== Auth Schemas ====================

class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    full_name: str
    organization: Optional[str] = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserSignupOtpRequest(UserCreate):
    pass


class UserSignupOtpVerify(BaseModel):
    email: EmailStr
    otp: str = Field(..., min_length=4, max_length=12)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    email: str
    role: str


class UserResponse(BaseModel):
    id: str
    email: str
    full_name: str
    role: str
    organization: Optional[str]
    is_active: bool
    created_at: datetime
    
    class Config:
        from_attributes = True


class UserAdminUpdate(BaseModel):
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    organization: Optional[str] = None
    password: Optional[str] = Field(default=None, min_length=8)
    role: Optional[str] = None
    is_active: Optional[bool] = None


class UserAdminCreate(UserCreate):
    role: str = "user"
    is_active: bool = True


# ==================== Export / Email Schemas ====================

class EmailReportRequest(BaseModel):
    recipients: List[EmailStr] = Field(..., min_length=1, max_length=10)
    cc: Optional[List[EmailStr]] = Field(default=None, max_length=10)
    subject: Optional[str] = Field(default=None, max_length=160)
    message: Optional[str] = Field(default=None, max_length=2000)


# ==================== Tender Schemas ====================

class TenderCriterionCreate(BaseModel):
    criterion_id: str
    criterion_type: str
    description: str
    operator: Optional[str] = None
    value: Optional[float] = None
    unit: Optional[str] = None
    allowed_values: Optional[List[str]] = None
    is_mandatory: bool = True
    source_page: Optional[int] = None


class TenderCriterionResponse(TenderCriterionCreate):
    id: str
    tender_id: str
    confidence: float
    source_text: Optional[str]
    created_at: datetime
    
    class Config:
        from_attributes = True


class TenderCreate(BaseModel):
    title: str
    description: Optional[str] = None
    tender_number: str
    issuing_authority: Optional[str] = None
    last_date: Optional[datetime] = None
    estimated_value: Optional[float] = None


class TenderResponse(TenderCreate):
    id: str
    file_name: str
    file_type: str
    extraction_status: str
    criteria: List[TenderCriterionResponse]
    created_by: str
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class TenderDetailResponse(TenderResponse):
    extracted_text: Optional[str]
    raw_data: Optional[Dict[str, Any]]


# ==================== Bidder Schemas ====================

class BidderDocumentCreate(BaseModel):
    file_name: str
    file_type: str
    document_type: Optional[str] = None


class BidderDocumentResponse(BidderDocumentCreate):
    id: str
    bidder_id: str
    extraction_status: str
    created_at: datetime
    
    class Config:
        from_attributes = True


class ExtractedFieldResponse(BaseModel):
    id: str
    field_name: str
    field_value: str
    field_type: Optional[str]
    confidence: float
    extraction_method: str
    source_document: Optional[str]
    created_at: datetime
    
    class Config:
        from_attributes = True


class BidderCreate(BaseModel):
    tender_id: str
    company_name: str
    gst_number: Optional[str] = None
    pan_number: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None


class BidderResponse(BidderCreate):
    id: str
    evaluation_status: str
    documents: List[BidderDocumentResponse] = []
    extracted_fields: List[ExtractedFieldResponse] = []
    created_at: datetime
    
    class Config:
        from_attributes = True


class BidderDetailResponse(BidderResponse):
    extracted_data: Optional[Dict[str, Any]]


# ==================== Evaluation Schemas ====================

class CriterionEvaluation(BaseModel):
    criterion: str
    extracted_value: Optional[str] = None
    source_document: Optional[str] = None
    source_page: Optional[int] = None
    evidence_snippet: Optional[str] = None
    mandatory: Optional[bool] = True
    decision: str  # PASS, FAIL, NEEDS_REVIEW
    confidence: float
    reasoning: str


class EvaluationResult(BaseModel):
    id: str
    tender_id: str
    bidder_id: str
    overall_decision: str
    overall_confidence: float
    decision_summary: Optional[str]
    criteria_results: List[CriterionEvaluation]
    evaluation_method: str
    is_reviewed: bool
    manual_decision: Optional[str] = None
    evaluated_at: datetime
    
    class Config:
        from_attributes = True


class EvaluationCreate(BaseModel):
    tender_id: str
    bidder_id: str


# ==================== Review Schemas ====================

class ReviewCreate(BaseModel):
    evaluation_id: str
    decision: str  # eligible, not_eligible, needs_manual_review
    comments: Optional[str] = None
    approved: bool = False


class ReviewAssignRequest(BaseModel):
    user_id: str


class ReviewResponse(ReviewCreate):
    id: str
    reviewed_by: str
    overridden: bool
    reviewed_at: datetime
    
    class Config:
        from_attributes = True


class ReviewQueueItemResponse(BaseModel):
    id: str
    evaluation_id: str
    reason: str
    priority: int
    status: str
    assigned_to: Optional[str]
    created_at: datetime
    
    class Config:
        from_attributes = True


# ==================== Audit Schemas ====================

class AuditLogResponse(BaseModel):
    id: str
    user_id: Optional[str]
    action: str
    entity_type: str
    entity_id: Optional[str]
    status: str
    details: Optional[Dict[str, Any]]
    error_message: Optional[str]
    timestamp: datetime
    
    class Config:
        from_attributes = True


# ==================== Export Schemas ====================

class EvaluationReport(BaseModel):
    tender_id: str
    tender_name: str
    bidder_id: str
    company_name: str
    overall_decision: str
    overall_confidence: float
    criteria_results: List[CriterionEvaluation]
    generated_at: datetime


# ==================== Search/Filter Schemas ====================

class EvaluationFilter(BaseModel):
    tender_id: Optional[str] = None
    decision: Optional[str] = None
    status: Optional[str] = None
    reviewed_only: Optional[bool] = False
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None


class BidderFilter(BaseModel):
    tender_id: Optional[str] = None
    evaluation_status: Optional[str] = None
    search_query: Optional[str] = None


class TenderFilter(BaseModel):
    search_query: Optional[str] = None
    status: Optional[str] = None
    created_after: Optional[datetime] = None
    created_before: Optional[datetime] = None
