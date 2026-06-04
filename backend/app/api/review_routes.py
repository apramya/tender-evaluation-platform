"""
Review API routes for manual evaluation
"""
import logging
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.database import ReviewQueue, Review, Evaluation, EligibilityDecision, User, UserRole
from app.schemas.schemas import ReviewAssignRequest, ReviewCreate, ReviewResponse, ReviewQueueItemResponse, UserResponse
from app.services.audit_service import AuditService
from app.utils.dependencies import get_db, get_current_user, get_review_user

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/queue")
async def get_review_queue(
    current_user = Depends(get_review_user),
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 20,
):
    """
    Get review queue items
    """
    result = await db.execute(
        select(ReviewQueue)
        .where(ReviewQueue.status.in_(["pending", "in_review"]))
        .order_by(ReviewQueue.priority.desc())
        .offset(skip)
        .limit(limit)
    )
    items = result.scalars().all()
    
    return {
        "total": len(items),
        "items": items,
    }


@router.get("/assignees")
async def list_review_assignees(
    current_user = Depends(get_review_user),
    db: AsyncSession = Depends(get_db),
):
    """
    List active users who can be assigned manual review work.
    """
    result = await db.execute(
        select(User)
        .where(
            User.is_active == True,
            User.role.in_([UserRole.ADMIN, UserRole.PROCUREMENT_OFFICER]),
        )
        .order_by(User.full_name.asc())
    )
    users = result.scalars().all()
    return {
        "total": len(users),
        "users": [UserResponse.model_validate(user) for user in users],
    }


@router.post("/{review_queue_id}/assign-to-me")
async def assign_review_to_me(
    review_queue_id: str,
    current_user = Depends(get_review_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Assign review queue item to current user
    """
    result = await db.execute(
        select(ReviewQueue).where(ReviewQueue.id == review_queue_id)
    )
    queue_item = result.scalars().first()
    
    if not queue_item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Review queue item not found",
        )
    
    if queue_item.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Item is not pending",
        )
    
    queue_item.assigned_to = current_user.id
    queue_item.status = "in_review"
    AuditService.add_log(
        db,
        user=current_user,
        action="assign_review",
        entity_type="review_queue",
        entity_id=queue_item.id,
        details={"evaluation_id": queue_item.evaluation_id},
    )
    
    await db.commit()
    
    return {"message": "Review assigned to you"}


@router.post("/{review_queue_id}/assign")
async def assign_review(
    review_queue_id: str,
    assignment: ReviewAssignRequest,
    current_user = Depends(get_review_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Assign review queue item to an active admin/procurement officer.
    """
    result = await db.execute(
        select(ReviewQueue).where(ReviewQueue.id == review_queue_id)
    )
    queue_item = result.scalars().first()

    if not queue_item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Review queue item not found",
        )

    if queue_item.status not in {"pending", "in_review"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Item cannot be reassigned",
        )

    user_result = await db.execute(
        select(User).where(User.id == assignment.user_id)
    )
    assignee = user_result.scalars().first()
    if not assignee or not assignee.is_active or assignee.role not in {UserRole.ADMIN, UserRole.PROCUREMENT_OFFICER}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Assignee must be an active admin or procurement officer",
        )

    queue_item.assigned_to = assignee.id
    queue_item.status = "in_review"
    AuditService.add_log(
        db,
        user=current_user,
        action="assign_review",
        entity_type="review_queue",
        entity_id=queue_item.id,
        details={
            "evaluation_id": queue_item.evaluation_id,
            "assigned_to": assignee.id,
            "assigned_to_email": assignee.email,
        },
    )

    await db.commit()

    return {"message": f"Review assigned to {assignee.full_name}"}


@router.post("")
async def submit_review(
    review_data: ReviewCreate,
    current_user = Depends(get_review_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Submit a manual review
    """
    try:
        # Get evaluation
        result = await db.execute(
            select(Evaluation).where(Evaluation.id == review_data.evaluation_id)
        )
        evaluation = result.scalars().first()
        
        if not evaluation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Evaluation not found",
            )
        
        # Create review record
        review = Review(
            id=str(uuid.uuid4()),
            evaluation_id=review_data.evaluation_id,
            reviewed_by=current_user.id,
            decision=EligibilityDecision(review_data.decision),
            comments=review_data.comments,
            approved=review_data.approved,
        )
        
        # Update evaluation
        evaluation.is_reviewed = True
        evaluation.manual_decision = EligibilityDecision(review_data.decision)
        evaluation.review_comments = review_data.comments

        queue_result = await db.execute(
            select(ReviewQueue).where(ReviewQueue.evaluation_id == review_data.evaluation_id)
        )
        queue_item = queue_result.scalars().first()
        if queue_item:
            queue_item.status = "completed"
        
        db.add(review)
        AuditService.add_log(
            db,
            user=current_user,
            action="submit_review",
            entity_type="review",
            entity_id=review.id,
            tender_id=evaluation.tender_id,
            details={
                "evaluation_id": evaluation.id,
                "decision": review_data.decision,
                "approved": review_data.approved,
            },
        )
        await db.commit()
        
        logger.info(f"Review submitted: {review.id}")
        
        return ReviewResponse.model_validate(review)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error submitting review: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to submit review",
        )


@router.get("/{review_id}", response_model=ReviewResponse)
async def get_review(
    review_id: str,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get review details
    """
    result = await db.execute(
        select(Review).where(Review.id == review_id)
    )
    review = result.scalars().first()
    
    if not review:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Review not found",
        )
    
    return review


@router.get("")
async def list_reviews(
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    my_reviews_only: bool = False,
    skip: int = 0,
    limit: int = 20,
):
    """
    List reviews
    """
    query = select(Review)
    
    if my_reviews_only:
        query = query.where(Review.reviewed_by == current_user.id)
    
    query = query.order_by(Review.reviewed_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    reviews = result.scalars().all()
    
    return {
        "total": len(reviews),
        "reviews": reviews,
    }
