#!/usr/bin/env python3
"""
Gmail email import function to populate raw entries from latest emails.
Takes user_id and token, creates one raw entry per email using Gmail API format.
"""

import asyncio
from uuid import UUID
from typing import List, Dict, Any
import httpx

from db.session import SessionLocal
from db.models import RawEntry, IntegrationToken
from db.embedding import embed_document
from sqlalchemy import select
from integrations.messaging import send_raw_entry_notification
import os
from datetime import datetime, timedelta


async def get_stored_gmail_token(user_id: UUID, refresh_if_needed: bool = True) -> str:
    """
    Get stored Gmail token for a user, refreshing if needed.

    Args:
        user_id: The user's UUID
        refresh_if_needed: Whether to automatically refresh expired tokens

    Returns:
        The stored access token (refreshed if needed)

    Raises:
        ValueError: If no token is found
    """
    db = SessionLocal()
    try:
        token_record = db.execute(
            select(IntegrationToken).where(
                IntegrationToken.user_id == user_id,
                IntegrationToken.integration_type == "gmail"
            )
        ).scalar_one_or_none()

        if not token_record:
            raise ValueError(f"No Gmail token found for user {user_id}")

        # Check if token needs refresh
        if refresh_if_needed and _token_needs_refresh(token_record):
            print(f"Gmail token expired for user {user_id}, attempting refresh...")

            try:
                new_token_data = await _refresh_gmail_token(token_record.refresh_token)

                # Update the stored token
                token_record.access_token = new_token_data["access_token"]

                # Update expiration metadata
                expires_at = datetime.utcnow() + timedelta(seconds=new_token_data["expires_in"])
                token_record.token_metadata = {
                    "expires_at": expires_at.isoformat(),
                    "expires_in": new_token_data["expires_in"]
                }

                db.commit()
                print(f"Gmail token refreshed successfully for user {user_id}")

            except Exception as e:
                print(f"Failed to refresh Gmail token for user {user_id}: {e}")
                raise ValueError(f"Gmail token expired and refresh failed: {e}")

        return token_record.access_token
    finally:
        db.close()


def _token_needs_refresh(token_record: IntegrationToken) -> bool:
    """Check if a token needs to be refreshed."""
    if not token_record.token_metadata:
        return False

    expires_at_str = token_record.token_metadata.get("expires_at")
    if not expires_at_str:
        return False

    try:
        expires_at = datetime.fromisoformat(expires_at_str.replace('Z', '+00:00'))
        # Refresh if token expires within 5 minutes
        return datetime.utcnow() >= (expires_at - timedelta(minutes=5))
    except Exception:
        return False


async def _refresh_gmail_token(refresh_token: str) -> Dict[str, Any]:
    """
    Refresh Gmail access token using refresh token.

    Args:
        refresh_token: The refresh token

    Returns:
        Dict containing new token data

    Raises:
        Exception: If refresh fails
    """
    # Get OAuth credentials from environment
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")

    if not all([client_id, client_secret]):
        raise Exception("Gmail OAuth credentials not configured")

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://oauth2.googleapis.com/token",
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": client_id,
                "client_secret": client_secret,
            }
        )

        if response.status_code != 200:
            raise Exception(f"Failed to refresh token: {response.status_code} {response.text}")

        return response.json()


async def import_latest_gmail_emails(user_id: UUID, gmail_token: str = None, max_results: int = 10) -> Dict[str, Any]:
    """
    Import the latest emails from Gmail for a user.

    Args:
        user_id: The user's UUID
        gmail_token: Gmail access token (optional, will use stored token if not provided)
        max_results: Maximum number of emails to import (default: 10)

    Returns:
        Dict with results summary
    """

    # If no token provided, try to get stored token
    if not gmail_token:
        try:
            gmail_token = await get_stored_gmail_token(user_id)
        except ValueError as e:
            return {
                "status": "error",
                "message": str(e),
                "emails_processed": 0
            }

    print(f"Starting Gmail import for user {user_id} (max {max_results} emails)")

    # Get database session
    db = SessionLocal()

    try:
        # 1. Get list of latest emails
        print("Fetching latest emails...")
        email_ids = await _get_latest_email_ids(gmail_token, max_results)
        print(f"   Found {len(email_ids)} emails")

        if not email_ids:
            return {
                "status": "success",
                "message": "No emails found",
                "emails_processed": 0
            }

        # 2. Process each email
        print("Processing emails...")
        processed_count = 0

        for i, email_id in enumerate(email_ids, 1):
            try:
                print(f"   [{i}/{len(email_ids)}] Processing email: {email_id}")

                # Check if we already have this email
                existing_entry_query = select(RawEntry).where(
                    RawEntry.user_id == user_id,
                    RawEntry.source == "gmail",
                    RawEntry.source_id == email_id
                )
                existing_entry = db.execute(existing_entry_query).scalar_one_or_none()

                if existing_entry:
                    print(f"   Email {email_id} already imported, skipping")
                    continue

                # Get full email details
                email_data = await _get_email_details(gmail_token, email_id)

                if not email_data:
                    print(f"   Failed to get details for email {email_id}")
                    continue

                # Create raw entry with full Gmail format
                raw_entry_content = {
                    "gmail_message": email_data,  # Full message object from Gmail API
                    "source": "gmail",
                    "import_metadata": {
                        "imported_at": asyncio.get_event_loop().time(),
                        "message_id": email_id,
                        "thread_id": email_data.get("threadId"),
                        "snippet": email_data.get("snippet", "")
                    }
                }

                # Generate embedding from email content
                text_for_embedding = _extract_email_text(email_data)
                embedding = embed_document(text_for_embedding)

                # Create and save raw entry
                raw_entry = RawEntry(
                    user_id=user_id,
                    source="gmail",
                    source_id=email_id,  # Store message ID for efficient lookups
                    content=raw_entry_content,
                    embedding=embedding
                )

                db.add(raw_entry)
                db.flush()  # Ensure the entry gets an ID
                processed_count += 1

                # Send the raw entry to AI agent for processing
                try:
                    await send_raw_entry_notification(user_id, raw_entry, {
                        "message_id": email_id,
                        "thread_id": email_data.get("threadId"),
                        "subject": _extract_header(email_data, "Subject"),
                        "from": _extract_header(email_data, "From"),
                        "text_preview": text_for_embedding[:200] + "..." if len(text_for_embedding) > 200 else text_for_embedding
                    })
                    print(f"   Raw entry created with ID: {raw_entry.id} - notification sent")
                except Exception as send_error:
                    print(f"   Warning: Failed to send notification for email {email_id}: {send_error}")
                    print(f"   Raw entry created with ID: {raw_entry.id} - notification failed")
                    # Continue processing even if notification sending fails

                # Rate limiting - be respectful to Gmail API
                await asyncio.sleep(0.1)

            except Exception as e:
                print(f"   Error processing email {email_id}: {e}")
                continue

        # Commit all entries
        db.commit()

        result = {
            "status": "success",
            "message": f"Successfully imported {processed_count} emails",
            "emails_processed": processed_count,
            "total_emails_found": len(email_ids)
        }

        print(f"Import complete: {processed_count}/{len(email_ids)} emails processed")
        return result

    except Exception as e:
        db.rollback()
        print(f"Import failed: {e}")
        return {
            "status": "error",
            "message": str(e),
            "emails_processed": 0
        }

    finally:
        db.close()


async def _get_latest_email_ids(gmail_token: str, max_results: int) -> List[str]:
    """Get list of latest email IDs from Gmail."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://gmail.googleapis.com/gmail/v1/users/me/messages",
                headers={"Authorization": f"Bearer {gmail_token}"},
                params={
                    "maxResults": max_results,
                    "q": "in:inbox"  # Only get emails from inbox
                }
            )

            if response.status_code != 200:
                print(f"Error fetching email list: {response.status_code} {response.text}")
                return []

            data = response.json()
            messages = data.get("messages", [])
            return [msg["id"] for msg in messages]

    except Exception as e:
        print(f"Error fetching email IDs: {e}")
        return []


async def _get_email_details(gmail_token: str, email_id: str) -> Dict[str, Any]:
    """Get full email details from Gmail API."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{email_id}",
                headers={"Authorization": f"Bearer {gmail_token}"},
                params={"format": "full"}  # Get full email content including body
            )

            if response.status_code != 200:
                print(f"Error fetching email {email_id}: {response.status_code} {response.text}")
                return None

            return response.json()

    except Exception as e:
        print(f"Error fetching email details for {email_id}: {e}")
        return None


def _extract_email_text(email_data: Dict[str, Any]) -> str:
    """Extract text content from Gmail message for embedding."""
    text_parts = []

    # Get headers for subject and sender
    subject = _extract_header(email_data, "Subject")
    from_addr = _extract_header(email_data, "From")

    if subject:
        text_parts.append(f"Subject: {subject}")
    if from_addr:
        text_parts.append(f"From: {from_addr}")

    # Get email body content
    body_text = _extract_body_text(email_data.get("payload", {}))
    if body_text:
        text_parts.append(body_text)

    # Fallback to snippet if no body found
    if not body_text:
        snippet = email_data.get("snippet", "")
        if snippet:
            text_parts.append(snippet)

    return "\n".join(text_parts)


def _extract_header(email_data: Dict[str, Any], header_name: str) -> str:
    """Extract specific header value from Gmail message."""
    headers = email_data.get("payload", {}).get("headers", [])
    for header in headers:
        if header.get("name", "").lower() == header_name.lower():
            return header.get("value", "")
    return ""


def _extract_body_text(payload: Dict[str, Any]) -> str:
    """Extract text body from Gmail message payload."""
    text_parts = []

    # If payload has parts, iterate through them
    if "parts" in payload:
        for part in payload["parts"]:
            text_parts.append(_extract_body_text(part))
    else:
        # Single part message
        mime_type = payload.get("mimeType", "")
        if mime_type == "text/plain":
            body = payload.get("body", {})
            data = body.get("data", "")
            if data:
                # Gmail API returns base64url encoded data
                import base64
                try:
                    decoded = base64.urlsafe_b64decode(data + "=" * (4 - len(data) % 4))
                    text_parts.append(decoded.decode("utf-8", errors="ignore"))
                except Exception as e:
                    print(f"Error decoding email body: {e}")
        elif mime_type == "text/html":
            # For HTML emails, we could extract text, but for simplicity just note it's HTML
            body = payload.get("body", {})
            data = body.get("data", "")
            if data:
                import base64
                try:
                    decoded = base64.urlsafe_b64decode(data + "=" * (4 - len(data) % 4))
                    html_content = decoded.decode("utf-8", errors="ignore")
                    # Simple HTML tag removal for basic text extraction
                    import re
                    text = re.sub('<[^<]+?>', '', html_content)
                    text_parts.append(text)
                except Exception as e:
                    print(f"Error decoding HTML email body: {e}")

    return "\n".join(filter(None, text_parts))