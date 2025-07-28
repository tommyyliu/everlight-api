from typing import Annotated
from uuid import UUID
import os
import httpx

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import select

from auth.user_auth import get_current_user
from db import models
from db.session import get_db_session

router = APIRouter(
    prefix="/integrations",
    tags=["integrations"],
)

CurrentUser = Annotated[models.User, Depends(get_current_user)]


class NotionConnectRequest(BaseModel):
    """Request to connect Notion using OAuth code and load all pages."""
    code: str


class IntegrationResponse(BaseModel):
    """Response for integration operations."""
    status: str
    message: str
    task_id: str = None


class WebhookPayload(BaseModel):
    """Webhook payload containing verification token."""
    verification_token: str


class WebhookResponse(BaseModel):
    """Response for webhook operations."""
    status: str
    message: str


@router.post("/notion/connect", response_model=IntegrationResponse)
async def connect_notion(
    code: str,
    background_tasks: BackgroundTasks,
    db: Annotated[Session, Depends(get_db_session)],
    user: CurrentUser
):
    """
    Connect Notion using OAuth code, exchange for access token, store in DB, and load all accessible pages.
    """
    
    try:
        # Exchange code for access token
        access_token = await _exchange_notion_code_for_token(code)
        
        # Store or update the access token in the database
        await _store_integration_token(db, user.id, "notion", access_token)
        
        # Generate a simple task ID for tracking
        import time
        task_id = f"notion_import_{user.id}_{int(time.time())}"
        
        # Start the background import task
        background_tasks.add_task(
            _import_notion_pages_background,
            user.id,
            access_token,
            task_id
        )
        
        return IntegrationResponse(
            status="started",
            message="Notion connected successfully. Import started. This may take a few minutes depending on how many pages you have.",
            task_id=task_id
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to connect Notion: {str(e)}"
        )


@router.get("/notion/status")
def get_notion_status(
    db: Annotated[Session, Depends(get_db_session)],
    user: CurrentUser
):
    """
    Check if user has Notion connected and any Notion data imported.
    """
    
    try:
        # Check if user has a stored Notion token
        token_record = db.execute(
            select(models.IntegrationToken).where(
                models.IntegrationToken.user_id == user.id,
                models.IntegrationToken.integration_type == "notion"
            )
        ).scalar_one_or_none()
        
        # Count existing Notion raw entries for this user
        from sqlalchemy import func
        
        count_query = select(func.count(models.RawEntry.id)).where(
            models.RawEntry.user_id == user.id,
            models.RawEntry.source == "notion"
        )
        
        notion_count = db.execute(count_query).scalar()
        
        return {
            "is_connected": token_record is not None,
            "has_notion_data": notion_count > 0,
            "notion_pages_count": notion_count,
            "user_id": str(user.id),
            "connected_at": token_record.created_at.isoformat() if token_record else None
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get Notion status: {str(e)}"
        )


@router.delete("/notion/disconnect")
async def disconnect_notion(
    db: Annotated[Session, Depends(get_db_session)],
    user: CurrentUser
):
    """
    Disconnect Notion by removing stored access token.
    """
    
    try:
        # Find and delete the stored token
        token_record = db.execute(
            select(models.IntegrationToken).where(
                models.IntegrationToken.user_id == user.id,
                models.IntegrationToken.integration_type == "notion"
            )
        ).scalar_one_or_none()
        
        if not token_record:
            raise HTTPException(
                status_code=404,
                detail="No Notion connection found for user"
            )
        
        db.delete(token_record)
        db.commit()
        
        return {
            "status": "success",
            "message": "Notion disconnected successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to disconnect Notion: {str(e)}"
        )


@router.post("/webhook/{user_uuid}", response_model=WebhookResponse)
async def handle_webhook(
    user_uuid: UUID,
    payload: WebhookPayload,
    db: Annotated[Session, Depends(get_db_session)]
):
    """
    Handle webhook requests for a specific user. 
    Stores the verification token for the user.
    """
    try:
        # Verify that the user exists
        user_query = select(models.User).where(models.User.id == user_uuid)
        user = db.execute(user_query).scalar_one_or_none()
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Check if a webhook token already exists for this user and source
        # For now, we'll assume the source is 'notion' but this could be made dynamic
        source = "notion"  # This could be extracted from headers or made a parameter
        
        existing_token_query = select(models.WebhookToken).where(
            models.WebhookToken.user_id == user_uuid,
            models.WebhookToken.source == source
        )
        existing_token = db.execute(existing_token_query).scalar_one_or_none()
        
        if existing_token:
            # Update existing token
            existing_token.verification_token = payload.verification_token
        else:
            # Create new webhook token
            webhook_token = models.WebhookToken(
                user_id=user_uuid,
                verification_token=payload.verification_token,
                source=source
            )
            db.add(webhook_token)
        
        db.commit()
        
        return WebhookResponse(
            status="success",
            message="Webhook verification token stored successfully"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to process webhook: {str(e)}")


async def _exchange_notion_code_for_token(code: str) -> str:
    """
    Exchange OAuth code for Notion access token.
    """
    # Get Notion OAuth credentials from environment
    client_id = os.getenv("NOTION_CLIENT_ID")
    client_secret = os.getenv("NOTION_CLIENT_SECRET")
    redirect_uri = os.getenv("NOTION_REDIRECT_URI")

    print(client_id, client_secret, redirect_uri)
    if not all([client_id, client_secret, redirect_uri]):
        raise HTTPException(
            status_code=500,
            detail="Notion OAuth credentials not configured"
        )
    
    # Exchange code for token
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.notion.com/v1/oauth/token",
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            json={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
            },
            auth=(client_id, client_secret)
        )
        
        if response.status_code != 200:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to exchange code for token: {response.text}"
            )
        
        token_data = response.json()
        return token_data["access_token"]


async def _store_integration_token(db: Session, user_id: UUID, integration_type: str, access_token: str, refresh_token: str = None, token_metadata: dict = None):
    """
    Store or update integration token in the database.
    """
    # Check if token already exists for this user and integration
    existing_token = db.execute(
        select(models.IntegrationToken).where(
            models.IntegrationToken.user_id == user_id,
            models.IntegrationToken.integration_type == integration_type
        )
    ).scalar_one_or_none()
    
    if existing_token:
        # Update existing token
        existing_token.access_token = access_token
        if refresh_token:
            existing_token.refresh_token = refresh_token
        if token_metadata:
            existing_token.token_metadata = token_metadata
    else:
        # Create new token record
        new_token = models.IntegrationToken(
            user_id=user_id,
            integration_type=integration_type,
            access_token=access_token,
            refresh_token=refresh_token,
            token_metadata=token_metadata
        )
        db.add(new_token)
    
    db.commit()


async def _get_integration_token(db: Session, user_id: UUID, integration_type: str) -> str:
    """
    Retrieve stored integration token for a user.
    """
    token_record = db.execute(
        select(models.IntegrationToken).where(
            models.IntegrationToken.user_id == user_id,
            models.IntegrationToken.integration_type == integration_type
        )
    ).scalar_one_or_none()
    
    if not token_record:
        raise HTTPException(
            status_code=404,
            detail=f"No {integration_type} token found for user"
        )
    
    return token_record.access_token


async def _import_notion_pages_background(user_id: UUID, notion_token: str, task_id: str):
    """
    Background task to import all Notion pages for a user.
    This runs outside the request context.
    """
    
    import asyncio
    import logging
    import sys
    import os
    
    # Add the project root to the path so we can import our modules
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    
    logger = logging.getLogger(__name__)
    
    try:
        # Import our Notion function
        from integrations.notion_importer import populate_raw_entries_from_notion
        
        logger.info(f"Starting Notion import for user {user_id} (task: {task_id})")
        
        # Run the import
        result = await populate_raw_entries_from_notion(user_id, notion_token)
        
        logger.info(f"Notion import completed for user {user_id}: {result}")
        
        # Individual raw entries are sent to Eforos during import process
        # No need for bulk notification since each entry is processed individually
        
        # TODO: Could store task results in database or send notification to user
        
    except Exception as e:
        logger.error(f"Notion import failed for user {user_id} (task: {task_id}): {e}")
        # TODO: Could store error status or notify user of failure


# Future endpoints for other data sources
@router.post("/gmail/connect")
async def connect_gmail(
    # request: GmailConnectRequest,
    background_tasks: BackgroundTasks,
    user: CurrentUser
):
    """
    Future endpoint for Gmail integration.
    """
    return {
        "status": "not_implemented",
        "message": "Gmail integration coming soon"
    }


@router.post("/calendar/connect")
async def connect_calendar(
    # request: CalendarConnectRequest,
    background_tasks: BackgroundTasks,
    user: CurrentUser
):
    """
    Future endpoint for Calendar integration.
    """
    return {
        "status": "not_implemented", 
        "message": "Calendar integration coming soon"
    }