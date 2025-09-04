from datetime import date, datetime
from typing import List, Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from auth.user_auth import get_current_user
from db import models
from db.session import get_db_session

router = APIRouter(prefix="/briefs", tags=["briefs"])

CurrentUser = Annotated[models.User, Depends(get_current_user)]


class BriefResponse(BaseModel):
    """Response model for brief content."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    utc_date: date
    title: str
    content: str  # Markdown content
    display_at: datetime
    dismissed_at: Optional[datetime]
    created_at: datetime


@router.get("/", response_model=List[BriefResponse])
def get_briefs(
        target_date: date,
        db: Annotated[Session, Depends(get_db_session)],
        user: CurrentUser):
    """Get all briefs for a specific date for the current user."""
    briefs = db.query(models.Brief).filter(
        models.Brief.user_id == user.id,
        models.Brief.utc_date == target_date
    ).order_by(models.Brief.display_at.asc()).all()

    return briefs
