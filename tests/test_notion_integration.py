"""
Tests for Notion integration functionality
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from uuid import uuid4

# Test imports
def test_notion_importer_imports():
    """Test that the Notion importer can be imported successfully"""
    from integrations.notion_importer import populate_raw_entries_from_notion
    assert populate_raw_entries_from_notion is not None


def test_embedding_module_imports():
    """Test that the embedding module can be imported"""
    from db.embedding import embed_document, embed_query
    assert embed_document is not None
    assert embed_query is not None


@pytest.mark.asyncio
async def test_populate_raw_entries_no_token():
    """Test that the function handles missing token gracefully"""
    from integrations.notion_importer import populate_raw_entries_from_notion
    
    user_id = uuid4()
    
    # Mock the database session to avoid actual DB calls
    with patch('integrations.notion_importer.SessionLocal') as mock_session:
        mock_db = MagicMock()
        mock_session.return_value = mock_db
        mock_db.execute.return_value.scalar_one_or_none.return_value = None
        
        result = await populate_raw_entries_from_notion(user_id)
        
        assert result["status"] == "error"
        assert "No Notion token found" in result["message"]
        assert result["pages_processed"] == 0


@pytest.mark.asyncio
async def test_populate_raw_entries_with_token():
    """Test the main import function with a mock token"""
    from integrations.notion_importer import populate_raw_entries_from_notion
    
    user_id = uuid4()
    fake_token = "fake_notion_token"
    
    # Mock the Notion client
    with patch('integrations.notion_importer.AsyncClient') as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value = mock_client
        
        # Mock the search response (no pages found)
        mock_client.search.return_value = {
            "results": [],
            "has_more": False
        }
        
        # Mock the database session
        with patch('integrations.notion_importer.SessionLocal') as mock_session:
            mock_db = MagicMock()
            mock_session.return_value = mock_db
            
            result = await populate_raw_entries_from_notion(user_id, fake_token)
            
            assert result["status"] == "success"
            assert result["message"] == "No pages found"
            assert result["pages_processed"] == 0


def test_extract_simple_text():
    """Test the text extraction function"""
    from integrations.notion_importer import _extract_simple_text
    
    # Mock page with title
    page = {
        "properties": {
            "Name": {
                "type": "title",
                "title": [
                    {
                        "type": "text",
                        "text": {"content": "Test Page Title"}
                    }
                ]
            }
        }
    }
    
    # Mock blocks with content
    blocks = [
        {
            "type": "paragraph",
            "paragraph": {
                "rich_text": [
                    {
                        "type": "text",
                        "text": {"content": "This is some content."}
                    }
                ]
            }
        }
    ]
    
    result = _extract_simple_text(page, blocks)
    assert "Test Page Title" in result
    assert "This is some content." in result


@pytest.mark.asyncio
async def test_get_stored_notion_token():
    """Test retrieving stored Notion token"""
    from integrations.notion_importer import get_stored_notion_token
    
    user_id = uuid4()
    
    # Mock successful token retrieval
    with patch('integrations.notion_importer.SessionLocal') as mock_session:
        mock_db = MagicMock()
        mock_session.return_value = mock_db
        
        mock_token = MagicMock()
        mock_token.access_token = "stored_token_123"
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_token
        
        result = await get_stored_notion_token(user_id)
        assert result == "stored_token_123"


@pytest.mark.asyncio
async def test_get_stored_notion_token_not_found():
    """Test handling when no stored token is found"""
    from integrations.notion_importer import get_stored_notion_token
    
    user_id = uuid4()
    
    # Mock no token found
    with patch('integrations.notion_importer.SessionLocal') as mock_session:
        mock_db = MagicMock()
        mock_session.return_value = mock_db
        mock_db.execute.return_value.scalar_one_or_none.return_value = None
        
        with pytest.raises(ValueError, match="No Notion token found"):
            await get_stored_notion_token(user_id)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])