"""
Tests for Notion importer messaging functionality
"""
import pytest
import os
from unittest.mock import patch, AsyncMock, MagicMock
from uuid import uuid4


def test_send_message_function_exists():
    """Test that send_message function is available"""
    from integrations.notion_importer import send_message
    assert send_message is not None


@pytest.mark.asyncio
async def test_send_raw_entry_notification_no_url():
    """Test notification when AI_AGENT_SERVICE_URL is not configured"""
    from integrations.notion_importer import _send_raw_entry_notification
    
    user_id = uuid4()
    mock_raw_entry = MagicMock()
    mock_raw_entry.id = uuid4()
    mock_raw_entry.content = {"test": "content"}
    
    # Test with no URL configured
    with patch.dict(os.environ, {}, clear=True):
        # Should not raise an exception, just skip silently
        await _send_raw_entry_notification(user_id, mock_raw_entry, {"test": "metadata"})


@pytest.mark.asyncio
async def test_send_raw_entry_notification_with_url():
    """Test notification when AI_AGENT_SERVICE_URL is configured"""
    from integrations.notion_importer import _send_raw_entry_notification
    
    user_id = uuid4()
    mock_raw_entry = MagicMock()
    mock_raw_entry.id = uuid4()
    mock_raw_entry.content = {"test": "content"}
    mock_raw_entry.created_at.isoformat.return_value = "2024-01-01T00:00:00"
    
    # Mock httpx client
    with patch('integrations.notion_importer.httpx.AsyncClient') as mock_client:
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_client.return_value.__aenter__.return_value.post.return_value = mock_response
        
        # Test with URL configured
        with patch.dict(os.environ, {
            'AI_AGENT_SERVICE_URL': 'http://localhost:8001',
            'AI_AGENT_SERVICE_TOKEN': 'test_token'
        }):
            await _send_raw_entry_notification(user_id, mock_raw_entry, {"test": "metadata"})
            
            # Verify the HTTP call was made
            mock_client.return_value.__aenter__.return_value.post.assert_called_once()


def test_environment_variables_example():
    """Test that .env.example contains required variables"""
    with open('.env.example', 'r') as f:
        env_content = f.read()
    
    required_vars = [
        'AI_AGENT_SERVICE_URL',
        'AI_AGENT_SERVICE_TOKEN',
        'DATABASE_URL',
        'GOOGLE_API_KEY',
        'NOTION_CLIENT_ID'
    ]
    
    for var in required_vars:
        assert var in env_content, f"Required environment variable {var} not found in .env.example"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])