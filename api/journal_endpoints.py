from datetime import datetime
from typing import Optional, Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy.orm import Session

from auth.user_auth import get_current_user
from db import models
from db.session import get_db_session

router = APIRouter(
    prefix="/journal",
    tags=["journal"],
)


CurrentUser = Annotated[models.User, Depends(get_current_user)]

class JournalPost(BaseModel):
    """
    The post body for a new journal entry. userid and timestamp are added automatically.
    """
    title: Optional[str] = Field(None, examples=["My Awesome Day"])
    content: str = Field(examples=["Today, I learned about FastAPI response models!"])
    # Time on user's computer.
    local_timestamp: datetime = Field(examples=["2008-09-15T15:53:00+05:00"])


class JournalEntry(JournalPost): # Inherits title, content
    """
    Represents a journal entry as stored and returned by the API.
    """
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(examples=["UUID here"])
    user_id: UUID = Field(examples=["UUID here"])
    created_at: datetime = Field(..., examples=[datetime.now()])
    # Derived based on user's time.
    week: str = Field(examples=["2025-W20"]) # ISO year and week number
    month: str = Field(examples=["2025-5"]) # Year and month number


@router.post("", response_model=JournalEntry)
def create_entry(
        entry_post: JournalPost,
        db: Annotated[Session, Depends(get_db_session)],
        user: CurrentUser):
    # NOTE: The year for the month and week may differ around New Years.
    year, week_num, _ = entry_post.local_timestamp.isocalendar()
    derived_week = f"{year}-W{week_num:02d}" # Ensure week number is two digits
    derived_month = f"{entry_post.local_timestamp.year}-{entry_post.local_timestamp.month:02d}"

    db_entry = models.JournalEntry(
        title=entry_post.title,
        content=entry_post.content,
        local_timestamp=entry_post.local_timestamp,
        user_id=user.id, # Convert string to UUID for the model
        week=derived_week,
        month=derived_month
    )

    db.add(db_entry)
    db.commit()
    db.refresh(db_entry) # Refresh the instance to get DB-generated values (like id, created_at)

    return db_entry


@router.delete("/{entry_id}", response_model=JournalEntry)
def delete_entry(
        entry_id: UUID,
        db: Annotated[Session, Depends(get_db_session)],
        user: CurrentUser):
    db_entry = db.query(models.JournalEntry).filter(models.JournalEntry.id == entry_id).first()
    if not db_entry:
        raise HTTPException(status_code=404, detail="Entry not found")

    if db_entry.user_id != user.id:
        raise HTTPException(status_code=403, detail="Unauthorized")

    db.delete(db_entry)
    db.commit()

    return db_entry




