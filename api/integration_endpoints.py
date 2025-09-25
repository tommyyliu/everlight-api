from typing import Annotated, Union
from uuid import UUID
import os
import httpx
import hmac
import hashlib
import json

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request, Header
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


class GmailConnectRequest(BaseModel):
    """Request to connect Gmail using OAuth code."""
    code: str


class IntegrationResponse(BaseModel):
    """Response for integration operations."""
    status: str
    message: str
    task_id: str = None


class NotionWebhookVerification(BaseModel):
    """Notion webhook verification payload."""
    verification_token: str


class NotionWebhookEvent(BaseModel):
    """Notion webhook event payload based on actual Notion webhook structure."""
    id: str
    timestamp: str
    workspace_id: str
    workspace_name: str
    subscription_id: str
    integration_id: str
    authors: list[dict]
    attempt_number: int
    entity: dict  # Contains id and type
    type: str  # Event type like "page.created", "page.content_updated"
    data: dict  # Contains parent info and updated_blocks for content updates


# Union type for the webhook payload
NotionWebhookPayload = Union[NotionWebhookVerification, NotionWebhookEvent]


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
    Connect Notion using OAuth code.
    Backend will exchange for access token, store in DB, and load all accessible pages.
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


@router.post("/webhook/{user_uuid}/notion")
async def handle_notion_webhook(
    user_uuid: UUID,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Annotated[Session, Depends(get_db_session)],
    x_notion_signature: Annotated[str, Header(alias="X-Notion-Signature")] = None
):
    """
    Unified Notion webhook endpoint that handles both verification challenges and events.
    Includes signature verification for security.
    """
    try:
        # Get the raw request body for signature verification
        body = await request.body()
        
        # Parse the JSON payload
        try:
            payload_dict = json.loads(body.decode())
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid JSON payload")
        
        # Verify that the user exists
        user_query = select(models.User).where(models.User.id == user_uuid)
        user = db.execute(user_query).scalar_one_or_none()
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Determine payload type and parse accordingly
        if "verification_token" in payload_dict:
            payload = NotionWebhookVerification.model_validate(payload_dict)
        else:
            payload = NotionWebhookEvent.model_validate(payload_dict)
            
            # For actual events (not verification), verify the signature
            if x_notion_signature:
                # Get the stored verification token
                webhook_token_query = select(models.WebhookToken).where(
                    models.WebhookToken.user_id == user_uuid,
                    models.WebhookToken.source == "notion"
                )
                webhook_token = db.execute(webhook_token_query).scalar_one_or_none()
                
                if webhook_token:
                    # Verify the signature
                    if not _verify_notion_signature(body, webhook_token.verification_token, x_notion_signature):
                        raise HTTPException(status_code=401, detail="Invalid webhook signature")
                else:
                    print("Warning: No verification token found for signature validation")
            else:
                print("Warning: No X-Notion-Signature header provided")
        
        # Handle verification challenge
        if isinstance(payload, NotionWebhookVerification):
            print(f"Received verification challenge for user {user_uuid}")
            
            # Store the verification token
            existing_token_query = select(models.WebhookToken).where(
                models.WebhookToken.user_id == user_uuid,
                models.WebhookToken.source == "notion"
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
                    source="notion"
                )
                db.add(webhook_token)
            
            db.commit()
            
            # Return success response for verification
            return WebhookResponse(
                status="success",
                message="Webhook verification token stored successfully"
            )
        
        # Handle actual events
        elif isinstance(payload, NotionWebhookEvent):
            print(f"Received {payload.type} event for user {user_uuid}")
            
            # Check if user has a webhook token (verification should have happened first)
            webhook_token_query = select(models.WebhookToken).where(
                models.WebhookToken.user_id == user_uuid,
                models.WebhookToken.source == "notion"
            )
            webhook_token = db.execute(webhook_token_query).scalar_one_or_none()
            
            if not webhook_token:
                raise HTTPException(
                    status_code=404, 
                    detail="No webhook verification found. Please complete webhook setup first."
                )
            
            # Process different event types
            if payload.type in ["page.created", "page.content_updated"]:
                # Extract page ID from the entity field
                page_id = payload.entity.get("id")
                print(f"Extracted page_id: {page_id} from entity: {payload.entity}")
                
                if not page_id:
                    raise HTTPException(status_code=400, detail="No page ID found in entity data")
                
                # Verify this is a page entity
                if payload.entity.get("type") != "page":
                    return WebhookResponse(
                        status="success",
                        message=f"Entity type {payload.entity.get('type')} not supported"
                    )
                
                print(f"Queueing background task for user {user_uuid}, page {page_id}, event {payload.type}")
                
                # Process the page in the background
                background_tasks.add_task(
                    _process_notion_page_event,
                    user_uuid,
                    page_id,
                    payload.type,
                    payload.id
                )
                
                return WebhookResponse(
                    status="success",
                    message=f"Notion {payload.type} event queued for processing"
                )
            
            elif payload.type == "page.deleted":
                # For deleted pages, we might want to mark them as deleted or remove them
                page_id = payload.entity.get("id")
                print(f"Page {page_id} was deleted for user {user_uuid}")

                return WebhookResponse(
                    status="success",
                    message="Page deletion event acknowledged"
                )
            
            else:
                # Unsupported event type - acknowledge but don't process
                print(f"Unsupported Notion event type: {payload.type}")
                return WebhookResponse(
                    status="success",
                    message=f"Event type {payload.type} acknowledged but not processed"
                )
        
        else:
            # This shouldn't happen with proper Union type handling
            raise HTTPException(
                status_code=400, 
                detail="Invalid payload format"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to process Notion webhook: {str(e)}")


def _verify_notion_signature(body: bytes, verification_token: str, signature_header: str) -> bool:
    """
    Verify Notion webhook signature using HMAC-SHA256.
    
    Args:
        body: Raw request body bytes
        verification_token: The stored verification token from initial webhook setup
        signature_header: The X-Notion-Signature header value
        
    Returns:
        True if signature is valid, False otherwise
    """
    try:
        # Extract the signature from the header (format: "sha256=<signature>")
        if not signature_header.startswith("sha256="):
            return False
        
        received_signature = signature_header[7:]  # Remove "sha256=" prefix
        
        # Calculate the expected signature
        expected_signature = hmac.new(
            verification_token.encode('utf-8'),
            body,
            hashlib.sha256
        ).hexdigest()
        
        # Use timing-safe comparison to prevent timing attacks
        return hmac.compare_digest(expected_signature, received_signature)
        
    except Exception as e:
        print(f"Error verifying signature: {e}")
        return False


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


async def _exchange_gmail_code_for_tokens(code: str) -> dict:
    """
    Exchange OAuth code for Gmail access and refresh tokens.
    """
    # Get Gmail OAuth credentials from environment
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    redirect_uri = os.getenv("GOOGLE_REDIRECT_URI")

    if not all([client_id, client_secret, redirect_uri]):
        raise HTTPException(
            status_code=500,
            detail="Gmail OAuth credentials not configured"
        )

    # Exchange code for tokens
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://oauth2.googleapis.com/token",
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": client_id,
                "client_secret": client_secret,
            }
        )

        if response.status_code != 200:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to exchange code for tokens: {response.text}"
            )

        token_data = response.json()

        # Calculate expiration time
        from datetime import datetime, timedelta
        expires_at = datetime.utcnow() + timedelta(seconds=token_data["expires_in"])

        return {
            "access_token": token_data["access_token"],
            "refresh_token": token_data.get("refresh_token"),
            "expires_in": token_data["expires_in"],
            "expires_at": expires_at.isoformat()
        }


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


async def _process_notion_page_event(user_id: UUID, page_id: str, event_type: str, event_id: str):
    """
    Background task to process a single Notion page event.
    This runs outside the request context.
    """
    
    # Use print statements for Cloud Run logging instead of logger
    print(f"[BACKGROUND TASK] Processing Notion {event_type} event {event_id} for user {user_id}, page {page_id}")
    
    try:
        # Import our Notion function - use direct import instead of path manipulation
        from integrations.notion_importer import create_or_update_notion_page
        
        # Process the page - the function will retrieve the stored token internally
        result = await create_or_update_notion_page(user_id, page_id)
        
        print(f"[BACKGROUND TASK] Notion page processing completed for user {user_id}: {result}")
        
    except ImportError as e:
        print(f"[BACKGROUND TASK] Import failed for user {user_id}, page {page_id} (event: {event_id}): {e}")
    except Exception as e:
        print(f"[BACKGROUND TASK] Notion page processing failed for user {user_id}, page {page_id} (event: {event_id}): {e}")
        import traceback
        print(f"[BACKGROUND TASK] Full traceback: {traceback.format_exc()}")


async def _import_notion_pages_background(user_id: UUID, notion_token: str, task_id: str):
    """
    Background task to import all Notion pages for a user.
    This runs outside the request context.
    """
    
    # Use print statements for Cloud Run logging instead of logger
    print(f"[BACKGROUND TASK] Starting Notion import for user {user_id} (task: {task_id})")
    
    try:
        # Import our Notion function - use direct import instead of path manipulation
        from integrations.notion_importer import populate_raw_entries_from_notion
        
        # Run the import
        result = await populate_raw_entries_from_notion(user_id, notion_token)
        
        print(f"[BACKGROUND TASK] Notion import completed for user {user_id}: {result}")
        
        # Individual raw entries are sent to agents during import process
        # No need for bulk notification since each entry is processed individually
        
        # TODO: Could store task results in database or send notification to user

    except ImportError as e:
        print(f"[BACKGROUND TASK] Import failed for user {user_id} (task: {task_id}): {e}")
    except Exception as e:
        print(f"[BACKGROUND TASK] Notion import failed for user {user_id} (task: {task_id}): {e}")
        import traceback
        print(f"[BACKGROUND TASK] Full traceback: {traceback.format_exc()}")
        # TODO: Could store error status or notify user of failure


async def _import_gmail_emails_background(user_id: UUID, gmail_token: str, task_id: str):
    """
    Background task to import latest Gmail emails for a user.
    This runs outside the request context.
    """

    # Use print statements for Cloud Run logging instead of logger
    print(f"[BACKGROUND TASK] Starting Gmail import for user {user_id} (task: {task_id})")

    try:
        # Import our Gmail function - use direct import instead of path manipulation
        from integrations.gmail_importer import import_latest_gmail_emails

        # Run the import (default 10 emails)
        result = await import_latest_gmail_emails(user_id, gmail_token, max_results=10)

        print(f"[BACKGROUND TASK] Gmail import completed for user {user_id}: {result}")

        # Individual raw entries are sent to agents during import process
        # No need for bulk notification since each entry is processed individually

        # TODO: Could store task results in database or send notification to user

    except ImportError as e:
        print(f"[BACKGROUND TASK] Import failed for user {user_id} (task: {task_id}): {e}")
    except Exception as e:
        print(f"[BACKGROUND TASK] Gmail import failed for user {user_id} (task: {task_id}): {e}")
        import traceback
        print(f"[BACKGROUND TASK] Full traceback: {traceback.format_exc()}")
        # TODO: Could store error status or notify user of failure


# Gmail endpoints
@router.post("/gmail/connect", response_model=IntegrationResponse)
async def connect_gmail(
    request: GmailConnectRequest,
    background_tasks: BackgroundTasks,
    db: Annotated[Session, Depends(get_db_session)],
    user: CurrentUser
):
    """
    Connect Gmail using OAuth code and import latest emails.
    Backend will exchange for access token, store in DB, and import emails.
    """
    # Exchange code for access token and refresh token
    token_data = await _exchange_gmail_code_for_tokens(request.code)

    # Store the tokens using the existing helper function
    await _store_integration_token(
        db=db,
        user_id=user.id,
        integration_type="gmail",
        access_token=token_data["access_token"],
        refresh_token=token_data.get("refresh_token"),
        token_metadata={
            "expires_at": token_data["expires_at"],
            "expires_in": token_data["expires_in"]
        }
    )

    # Generate a simple task ID for tracking
    import time
    task_id = f"gmail_import_{user.id}_{int(time.time())}"

    # Start the background import task
    background_tasks.add_task(
        _import_gmail_emails_background,
        user.id,
        token_data["access_token"],
        task_id
    )

    return {
        "status": "success",
        "message": "Gmail connected successfully. Tokens stored and tested.",
        **test_result
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