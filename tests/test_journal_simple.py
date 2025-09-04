"""
Simplified integration tests for journal endpoints
Can be run without testing.postgresql if needed
"""
import pytest
import os
import tempfile
from datetime import datetime, timezone
from uuid import uuid4
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Import our application modules
from main import app
from db.models import Base, User, JournalEntry
from db.session import get_db_session


def test_app_imports():
    """Basic test to ensure all imports work"""
    assert app is not None
    assert hasattr(app, 'routes')
    
    # Check that our journal routes are registered
    routes = [route.path for route in app.routes]
    assert '/journal' in routes
    assert any('/journal/{entry_id}' in route.path for route in app.routes)


def test_journal_models():
    """Test that our models are properly defined"""
    # Test User model
    user = User(
        firebase_user_id="test_123",
        email="test@example.com"
    )
    assert user.firebase_user_id == "test_123"
    assert user.email == "test@example.com"
    
    # Test JournalEntry model
    entry = JournalEntry(
        title="Test Entry",
        content="Test content",
        local_timestamp=datetime.now(timezone.utc),
        user_id=uuid4(),
        week="2024-W01",
        month="2024-01"
    )
    assert entry.title == "Test Entry"
    assert entry.content == "Test content"


def test_week_month_calculation():
    """Test the week and month calculation logic"""
    
    # Test various dates
    test_cases = [
        (datetime(2024, 1, 1, tzinfo=timezone.utc), "2024-W01", "2024-01"),
        (datetime(2024, 6, 15, tzinfo=timezone.utc), "2024-W24", "2024-06"),
        (datetime(2024, 12, 31, tzinfo=timezone.utc), "2025-W01", "2024-12"),
    ]
    
    for test_date, expected_week, expected_month in test_cases:
        year, week_num, _ = test_date.isocalendar()
        derived_week = f"{year}-W{week_num:02d}"
        derived_month = f"{test_date.year}-{test_date.month:02d}"
        
        assert derived_week == expected_week
        assert derived_month == expected_month


@pytest.mark.skipif(
    os.getenv("SKIP_DB_TESTS") == "true",
    reason="Database tests skipped - set SKIP_DB_TESTS=false to run"
)
def test_journal_endpoints_with_sqlite():
    """Test journal endpoints using SQLite for simpler setup"""
    # Create temporary SQLite database
    db_fd, db_path = tempfile.mkstemp()
    
    try:
        # Create engine with SQLite
        engine = create_engine(f"sqlite:///{db_path}")
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        
        # Create tables
        Base.metadata.create_all(bind=engine)
        
        # Override database dependency
        def override_get_db_session():
            db = SessionLocal()
            try:
                yield db
            finally:
                db.close()
        
        app.dependency_overrides[get_db_session] = override_get_db_session
        
        # Create test client
        client = TestClient(app)
        
        # Create test user
        test_user_id = uuid4()
        db = SessionLocal()
        test_user = User(
            id=test_user_id,
            firebase_user_id="test_firebase_123",
            email="test@example.com"
        )
        db.add(test_user)
        db.commit()
        db.close()
        
        # Mock Firebase auth
        mock_claims = {
            "user_id": "test_firebase_123",
            "email": "test@example.com"
        }
        
        with patch('auth.user_auth.auth.verify_id_token', return_value=mock_claims):
            # Test journal entry creation
            journal_data = {
                "title": "Test Entry",
                "content": "This is a test journal entry.",
                "local_timestamp": "2024-01-15T10:30:00+00:00"
            }
            
            response = client.post(
                "/journal",
                json=journal_data,
                headers={"Authorization": "Bearer fake_token"}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["title"] == "Test Entry"
            assert data["content"] == "This is a test journal entry."
            assert data["week"] == "2024-W03"
            assert data["month"] == "2024-01"
            
            entry_id = data["id"]
            
            # Test journal entry deletion
            response = client.delete(
                f"/journal/{entry_id}",
                headers={"Authorization": "Bearer fake_token"}
            )
            
            assert response.status_code == 200
            deleted_data = response.json()
            assert deleted_data["id"] == entry_id
    
    finally:
        # Clean up
        os.close(db_fd)
        os.unlink(db_path)
        app.dependency_overrides.clear()


def test_authentication_required():
    """Test that authentication is required for journal endpoints"""
    client = TestClient(app)
    
    # Test POST without auth
    response = client.post("/journal", json={
        "content": "Test",
        "local_timestamp": "2024-01-15T10:30:00+00:00"
    })
    assert response.status_code == 403
    
    # Test DELETE without auth
    fake_id = str(uuid4())
    response = client.delete(f"/journal/{fake_id}")
    assert response.status_code == 403


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])