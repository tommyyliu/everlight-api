#!/usr/bin/env python3
"""
Simple function to populate raw entries from Notion pages.
Takes user_id and token, creates one raw entry per page using full Notion API format.
"""

import asyncio
import sys
from uuid import UUID
from typing import List, Dict, Any

try:
    from notion_client import AsyncClient
except ImportError:
    print("notion-client not installed. Run: pip install notion-client")
    sys.exit(1)

from db.session import SessionLocal
from db.models import RawEntry, IntegrationToken
from db.embedding import embed_document
from sqlalchemy import select


async def get_stored_notion_token(user_id: UUID) -> str:
    """
    Get stored Notion token for a user.
    
    Args:
        user_id: The user's UUID
        
    Returns:
        The stored access token
        
    Raises:
        ValueError: If no token is found
    """
    db = SessionLocal()
    try:
        token_record = db.execute(
            select(IntegrationToken).where(
                IntegrationToken.user_id == user_id,
                IntegrationToken.integration_type == "notion"
            )
        ).scalar_one_or_none()
        
        if not token_record:
            raise ValueError(f"No Notion token found for user {user_id}")
        
        return token_record.access_token
    finally:
        db.close()


async def populate_raw_entries_from_notion(user_id: UUID, notion_token: str = None) -> Dict[str, Any]:
    """
    Populate raw entries from all accessible Notion pages for a user.
    
    Args:
        user_id: The user's UUID
        notion_token: Notion integration token (optional, will use stored token if not provided)
        
    Returns:
        Dict with results summary
    """
    
    # If no token provided, try to get stored token
    if not notion_token:
        try:
            notion_token = await get_stored_notion_token(user_id)
        except ValueError as e:
            return {
                "status": "error",
                "message": str(e),
                "pages_processed": 0
            }
    
    print(f"Starting Notion import for user {user_id}")
    
    # Initialize Notion client
    client = AsyncClient(auth=notion_token)
    rate_limit_delay = 0.4  # 3 requests per second max
    
    # Get database session
    db = SessionLocal()
    
    try:
        # 1. Discover all pages
        print("Discovering pages...")
        pages = await _get_all_pages(client, rate_limit_delay)
        print(f"   Found {len(pages)} pages")
        
        if not pages:
            return {
                "status": "success",
                "message": "No pages found",
                "pages_processed": 0
            }
        
        # 2. Process each page
        print("Processing pages...")
        processed_count = 0
        
        for i, page in enumerate(pages, 1):
            try:
                print(f"   [{i}/{len(pages)}] Processing page: {page.get('id', 'unknown')}")
                
                # Get full page details
                full_page = await client.pages.retrieve(page["id"])
                await asyncio.sleep(rate_limit_delay)
                
                # Get all blocks for the page
                blocks = await _get_all_blocks(client, page["id"], rate_limit_delay)
                
                # Create raw entry with full Notion format
                raw_entry_content = {
                    "notion_page": full_page,  # Full page object from Notion API
                    "notion_blocks": blocks,   # Full blocks array from Notion API
                    "source": "notion",
                    "import_metadata": {
                        "imported_at": asyncio.get_event_loop().time(),
                        "page_id": page["id"],
                        "block_count": len(blocks)
                    }
                }
                
                # Generate embedding from a simple text representation
                text_for_embedding = _extract_simple_text(full_page, blocks)
                embedding = embed_document(text_for_embedding)
                
                # Create and save raw entry
                raw_entry = RawEntry(
                    user_id=user_id,
                    source="notion",
                    content=raw_entry_content,
                    embedding=embedding
                )
                
                db.add(raw_entry)
                db.flush()  # Ensure the entry gets an ID
                processed_count += 1
                
                # Note: AI agent communication not available in everlight-api
                # In everlight-b2, this would send messages to Eforos for processing
                print(f"   Raw entry created with ID: {raw_entry.id}")
                
            except Exception as e:
                print(f"   Error processing page {page.get('id')}: {e}")
                continue
        
        # Commit all entries
        db.commit()
        
        result = {
            "status": "success",
            "message": f"Successfully imported {processed_count} pages",
            "pages_processed": processed_count,
            "total_pages_found": len(pages)
        }
        
        print(f"Import complete: {processed_count}/{len(pages)} pages processed")
        return result
        
    except Exception as e:
        db.rollback()
        print(f"Import failed: {e}")
        return {
            "status": "error",
            "message": str(e),
            "pages_processed": 0
        }
        
    finally:
        db.close()


async def _get_all_pages(client: AsyncClient, rate_limit_delay: float) -> List[Dict[str, Any]]:
    """Get all accessible pages from Notion."""
    pages = []
    has_more = True
    start_cursor = None
    
    while has_more:
        try:
            response = await client.search(
                filter={"property": "object", "value": "page"},
                start_cursor=start_cursor,
                page_size=100
            )
            
            pages.extend(response["results"])
            has_more = response["has_more"]
            start_cursor = response.get("next_cursor")
            
            if has_more:
                await asyncio.sleep(rate_limit_delay)
                
        except Exception as e:
            print(f"Error fetching pages: {e}")
            break
    
    return pages


async def _get_all_blocks(client: AsyncClient, page_id: str, rate_limit_delay: float) -> List[Dict[str, Any]]:
    """Get all blocks from a page."""
    blocks = []
    has_more = True
    start_cursor = None
    
    while has_more:
        try:
            response = await client.blocks.children.list(
                block_id=page_id,
                start_cursor=start_cursor,
                page_size=100
            )
            
            blocks.extend(response["results"])
            has_more = response["has_more"]
            start_cursor = response.get("next_cursor")
            
            if has_more:
                await asyncio.sleep(rate_limit_delay)
                
        except Exception as e:
            print(f"Error fetching blocks for page {page_id}: {e}")
            break
    
    return blocks


def _extract_simple_text(page: Dict[str, Any], blocks: List[Dict[str, Any]]) -> str:
    """Extract simple text representation for embedding generation."""
    
    # Get page title
    title_parts = []
    properties = page.get("properties", {})
    for prop_name, prop_data in properties.items():
        if prop_data.get("type") == "title":
            title_array = prop_data.get("title", [])
            for text_obj in title_array:
                if text_obj.get("type") == "text":
                    title_parts.append(text_obj["text"]["content"])
    
    title = "".join(title_parts) if title_parts else "Untitled"
    
    # Extract text from blocks
    text_parts = [title]
    
    for block in blocks:
        block_type = block.get("type", "")
        block_data = block.get(block_type, {})
        
        # Extract rich text from common block types
        if "rich_text" in block_data:
            for text_obj in block_data["rich_text"]:
                if text_obj.get("type") == "text":
                    text_parts.append(text_obj["text"]["content"])
    
    return " ".join(text_parts)


# Example usage function
async def example_usage():
    """Example of how to use the function."""
    from uuid import uuid4
    
    # Example user ID (in real usage, this would come from your auth system)
    user_id = uuid4()
    
    # Get token from user
    token = input("Enter your Notion integration token: ").strip()
    
    if not token:
        print("No token provided")
        return
    
    # Run the import
    result = await populate_raw_entries_from_notion(user_id, token)
    
    print(f"\nFinal Result:")
    print(f"   Status: {result['status']}")
    print(f"   Message: {result['message']}")
    print(f"   Pages processed: {result['pages_processed']}")
    
    if result['status'] == 'success' and result['pages_processed'] > 0:
        print(f"\nRaw entries created! Check your database:")
        print(f"   SELECT * FROM raw_entries WHERE source = 'notion' ORDER BY created_at DESC;")


if __name__ == "__main__":
    asyncio.run(example_usage())