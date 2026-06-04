"""
Idempotent development/demo seed data.

Run inside the backend container:
    python scripts/seed_data.py
"""
import asyncio
import uuid
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.future import select
from sqlalchemy.orm import sessionmaker

from app.models.database import (
    AuditLog,
    Base,
    Bidder,
    CriterionType,
    EligibilityDecision,
    Evaluation,
    EvaluationStatus,
    ExtractedField,
    Tender,
    TenderCriterion,
    User,
    UserRole,
)
from app.services.auth_service import AuthService
from app.utils.config import settings


async def upsert_user(session: AsyncSession, email: str, full_name: str, password: str, role: UserRole, organization: str) -> User:
    result = await session.execute(select(User).where(User.email == email))
    user = result.scalars().first()
    if user:
        user.full_name = full_name
        user.hashed_password = AuthService.hash_password(password)
        user.role = role
        user.organization = organization
        user.is_active = True
        return user

    user = User(
        id=str(uuid.uuid4()),
        email=email,
        full_name=full_name,
        hashed_password=AuthService.hash_password(password),
        role=role,
        organization=organization,
        is_active=True,
    )
    session.add(user)
    return user


async def seed_database() -> None:
    engine = create_async_engine(settings.DATABASE_URL, echo=False, future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        admin_user = await upsert_user(
            session, "admin@tenderevaluation.com", "Admin User", "admin123", UserRole.ADMIN, "Government"
        )
        officer_user = await upsert_user(
            session,
            "officer@tenderevaluation.com",
            "Procurement Officer",
            "officer123",
            UserRole.PROCUREMENT_OFFICER,
            "Ministry of Roads",
        )
        await upsert_user(
            session, "user@tenderevaluation.com", "Project User", "user12345", UserRole.USER, "Client Team"
        )
        await session.flush()

        existing_tender = await session.execute(select(Tender).where(Tender.tender_number == "TENDER-2024-001"))
        if existing_tender.scalars().first():
            await session.commit()
            await engine.dispose()
            print("Seed users refreshed. Sample tender already exists.")
            return

        tender_id = str(uuid.uuid4())
        tender = Tender(
            id=tender_id,
            tender_number="TENDER-2024-001",
            title="Road Construction and Maintenance Project",
            description="Large scale road construction and maintenance project for national highways",
            file_name="tender_2024_001.pdf",
            file_path="./uploads/tender_2024_001.pdf",
            file_type="pdf",
            tender_date=datetime.utcnow(),
            last_date=datetime.utcnow() + timedelta(days=30),
            issuing_authority="Ministry of Road Transport & Highways",
            estimated_value=500000000,
            extraction_status="completed",
            created_by=officer_user.id,
            extracted_text=(
                "Minimum annual turnover of Rs 5 crore is required. ISO 9001 certification is required. "
                "No pending litigation cases are allowed. Minimum 3 similar projects completed in last 5 years."
            ),
            raw_data={"category": "Infrastructure"},
        )
        session.add(tender)

        criteria = [
            TenderCriterion(
                id=str(uuid.uuid4()),
                tender_id=tender_id,
                criterion_id="FIN_001",
                criterion_type=CriterionType.FINANCIAL,
                description="Minimum annual turnover of 5 crore in last 3 years",
                operator=">=",
                value=5,
                unit="crore",
                is_mandatory=True,
                source_page=1,
                source_text="Bidder must have minimum annual turnover of Rs 5 crore",
            ),
            TenderCriterion(
                id=str(uuid.uuid4()),
                tender_id=tender_id,
                criterion_id="TECH_001",
                criterion_type=CriterionType.TECHNICAL,
                description="ISO 9001 certification required",
                is_mandatory=True,
                source_page=2,
                source_text="Bidder must possess ISO 9001 certification",
            ),
            TenderCriterion(
                id=str(uuid.uuid4()),
                tender_id=tender_id,
                criterion_id="COMP_001",
                criterion_type=CriterionType.COMPLIANCE,
                description="No pending litigation cases",
                is_mandatory=True,
                source_page=3,
                source_text="Bidder must not have any pending litigation",
            ),
            TenderCriterion(
                id=str(uuid.uuid4()),
                tender_id=tender_id,
                criterion_id="EXP_001",
                criterion_type=CriterionType.TECHNICAL,
                description="Minimum 3 similar projects completed in last 5 years",
                operator=">=",
                value=3,
                unit="projects",
                is_mandatory=True,
                source_page=4,
                source_text="Bidder must have completed at least 3 similar projects",
            ),
        ]
        session.add_all(criteria)

        bidder1_id = str(uuid.uuid4())
        bidder2_id = str(uuid.uuid4())
        bidders = [
            Bidder(
                id=bidder1_id,
                tender_id=tender_id,
                company_name="ABC Construction Pvt Ltd",
                gst_number="27AABCU1234H1Z0",
                pan_number="AABCU1234H",
                contact_email="bid@abcconstruction.com",
                contact_phone="+91-9876543210",
                evaluation_status=EvaluationStatus.COMPLETED,
                extracted_data={"turnover": "7.5 crore", "similar_projects": 5},
            ),
            Bidder(
                id=bidder2_id,
                tender_id=tender_id,
                company_name="XYZ Engineering Ltd",
                gst_number="27AAXYZ1234H1Z0",
                pan_number="AAXYZ1234H",
                contact_email="tenders@xyzeng.com",
                contact_phone="+91-9876543211",
                evaluation_status=EvaluationStatus.COMPLETED,
                extracted_data={"turnover": "3.2 crore", "similar_projects": 2},
            ),
        ]
        session.add_all(bidders)

        session.add_all([
            ExtractedField(
                id=str(uuid.uuid4()),
                bidder_id=bidder1_id,
                field_name="turnover",
                field_value="7.5 crore",
                field_type="currency",
                confidence=0.94,
                extraction_method="ai",
                source_document="balance_sheet.pdf",
            ),
            ExtractedField(
                id=str(uuid.uuid4()),
                bidder_id=bidder2_id,
                field_name="turnover",
                field_value="3.2 crore",
                field_type="currency",
                confidence=0.89,
                extraction_method="ai",
                source_document="balance_sheet.pdf",
            ),
        ])

        eval1_id = str(uuid.uuid4())
        eval2_id = str(uuid.uuid4())
        session.add_all([
            Evaluation(
                id=eval1_id,
                tender_id=tender_id,
                bidder_id=bidder1_id,
                overall_decision=EligibilityDecision.ELIGIBLE,
                overall_confidence=0.94,
                decision_summary="Bidder meets all mandatory requirements with high confidence.",
                criteria_results=[
                    {"criterion": "Minimum annual turnover >= 5 crore", "extracted_value": "7.5 crore", "source_document": "balance_sheet.pdf", "decision": "PASS", "confidence": 0.94, "reasoning": "Turnover exceeds required threshold."},
                    {"criterion": "ISO 9001 certification required", "extracted_value": "ISO-9001", "source_document": "certificates.pdf", "decision": "PASS", "confidence": 0.91, "reasoning": "Bidder has ISO evidence."},
                ],
                evaluation_method="hybrid",
                is_reviewed=True,
                manual_decision=EligibilityDecision.ELIGIBLE,
            ),
            Evaluation(
                id=eval2_id,
                tender_id=tender_id,
                bidder_id=bidder2_id,
                overall_decision=EligibilityDecision.NOT_ELIGIBLE,
                overall_confidence=0.91,
                decision_summary="Bidder does not meet mandatory financial and experience requirements.",
                criteria_results=[
                    {"criterion": "Minimum annual turnover >= 5 crore", "extracted_value": "3.2 crore", "source_document": "balance_sheet.pdf", "decision": "FAIL", "confidence": 0.94, "reasoning": "Turnover is below threshold."},
                    {"criterion": "Minimum 3 similar projects", "extracted_value": "2 projects", "source_document": "experience.pdf", "decision": "FAIL", "confidence": 0.91, "reasoning": "Project count is below threshold."},
                ],
                evaluation_method="hybrid",
                is_reviewed=True,
                manual_decision=EligibilityDecision.NOT_ELIGIBLE,
            ),
        ])

        session.add(AuditLog(
            id=str(uuid.uuid4()),
            user_id=officer_user.id,
            action="seed_data",
            entity_type="tender",
            entity_id=tender_id,
            tender_id=tender_id,
            status="success",
            details={"sample": True},
        ))

        await session.commit()

    await engine.dispose()
    print("Database seeded successfully.")
    print("Admin: admin@tenderevaluation.com / admin123")
    print("Officer: officer@tenderevaluation.com / officer123")
    print("User: user@tenderevaluation.com / user12345")


if __name__ == "__main__":
    asyncio.run(seed_database())
