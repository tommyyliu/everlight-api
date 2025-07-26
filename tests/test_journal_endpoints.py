"""
Integration tests for journal endpoints using testing.postgresql
"""
import os
import pytest
import testing.postgresql
from datetime import datetime, timezone
from uuid import uuid4
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Import our application modules
from main import app
from db.models import Base, User, JournalEntry
from db.session import get_db_session


class TestJournalEndpoints:
    """Test class for journal endpoint integration tests"""
    
    @classmethod
    def setup_class(cls):
        """Set up test database and client"""
        # Create a temporary PostgreSQL instance
        cls.postgresql = testing.postgresql.Postgresql()
        
        # Create database engine and session
        # Use psycopg instead of psycopg2 for the connection
        url = cls.postgresql.url().replace('postgresql://', 'postgresql+psycopg://')
        cls.engine = create_engine(url)
        cls.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=cls.engine)
        
        # Create all tables
        Base.metadata.create_all(bind=cls.engine)
        
        # Override the get_db_session dependency
        def override_get_db_session():
            db = cls.SessionLocal()
            try:
                yield db
            finally:
                db.close()
        
        app.dependency_overrides[get_db_session] = override_get_db_session
        
        # Create test client
        cls.client = TestClient(app)
        
        # Create a test user
        cls.test_user_id = uuid4()
        cls.test_user_firebase_id = "test_firebase_user_123"
        cls.test_user_email = "test@example.com"
        
        db = cls.SessionLocal()
        test_user = User(
            id=cls.test_user_id,
            firebase_user_id=cls.test_user_firebase_id,
            email=cls.test_user_email
        )
        db.add(test_user)
        db.commit()
        db.close()
    
    @classmethod
    def teardown_class(cls):
        """Clean up test database"""
        cls.postgresql.stop()
    
    def setup_method(self):
        """Set up for each test method"""
        # Clear journal entries before each test
        db = self.SessionLocal()
        db.query(JournalEntry).delete()
        db.commit()
        db.close()
    
    def mock_firebase_auth(self, user_id=None):
        """Mock Firebase authentication to return our test user"""
        if user_id is None:
            user_id = self.test_user_firebase_id
            
        mock_claims = {
            "user_id": user_id,
            "email": self.test_user_email
        }
        
        return patch('auth.user_auth.auth.verify_id_token', return_value=mock_claims)
    
    def test_create_journal_entry_success(self):
        """Test successful journal entry creation"""
        with self.mock_firebase_auth():
            # Test data
            journal_data = {
                "title": "Test Entry",
                "content": "This is a test journal entry content.",
                "local_timestamp": "2024-01-15T10:30:00+00:00"
            }
            
            # Make request
            response = self.client.post(
                "/journal",
                json=journal_data,
                headers={"Authorization": "Bearer fake_token"}
            )
            
            # Assertions
            assert response.status_code == 200
            data = response.json()
            
            assert data["title"] == journal_data["title"]
            assert data["content"] == journal_data["content"]
            assert data["user_id"] == str(self.test_user_id)
            assert "id" in data
            assert "created_at" in data
            assert data["week"] == "2024-W03"  # ISO week for 2024-01-15
            assert data["month"] == "2024-01"
    
    def test_create_journal_entry_without_title(self):
        """Test journal entry creation without title (should work)"""
        with self.mock_firebase_auth():
            journal_data = {
                "content": "Entry without title",
                "local_timestamp": "2024-06-20T15:45:00+00:00"
            }
            
            response = self.client.post(
                "/journal",
                json=journal_data,
                headers={"Authorization": "Bearer fake_token"}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["title"] is None
            assert data["content"] == journal_data["content"]
            assert data["week"] == "2024-W25"  # ISO week for 2024-06-20
            assert data["month"] == "2024-06"
    
    def test_create_journal_entry_unauthorized(self):
        """Test journal entry creation without authentication"""
        journal_data = {
            "title": "Unauthorized Entry",
            "content": "This should fail",
            "local_timestamp": "2024-01-15T10:30:00+00:00"
        }
        
        response = self.client.post("/journal", json=journal_data)
        assert response.status_code == 403  # No Authorization header
    
    def test_create_journal_entry_invalid_token(self):
        """Test journal entry creation with invalid Firebase token"""
        with patch('auth.user_auth.auth.verify_id_token', side_effect=Exception("Invalid token")):
            journal_data = {
                "title": "Invalid Token Entry",
                "content": "This should fail",
                "local_timestamp": "2024-01-15T10:30:00+00:00"
            }
            
            response = self.client.post(
                "/journal",
                json=journal_data,
                headers={"Authorization": "Bearer invalid_token"}
            )
            
            assert response.status_code == 500
    
    def test_create_journal_entry_missing_content(self):
        """Test journal entry creation with missing required content"""
        with self.mock_firebase_auth():
            journal_data = {
                "title": "Entry without content",
                "local_timestamp": "2024-01-15T10:30:00+00:00"
                # Missing content field
            }
            
            response = self.client.post(
                "/journal",
                json=journal_data,
                headers={"Authorization": "Bearer fake_token"}
            )
            
            assert response.status_code == 422  # Validation error
    
    def test_delete_journal_entry_success(self):
        """Test successful journal entry deletion"""
        with self.mock_firebase_auth():
            # First create an entry
            db = self.SessionLocal()
            entry = JournalEntry(
                title="Entry to Delete",
                content="This entry will be deleted",
                local_timestamp=datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc),
                user_id=self.test_user_id,
                week="2024-W03",
                month="2024-01"
            )
            db.add(entry)
            db.commit()
            db.refresh(entry)
            entry_id = entry.id
            db.close()
            
            # Now delete it
            response = self.client.delete(
                f"/journal/{entry_id}",
                headers={"Authorization": "Bearer fake_token"}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["id"] == str(entry_id)
            assert data["title"] == "Entry to Delete"
            
            # Verify it's actually deleted from database
            db = self.SessionLocal()
            deleted_entry = db.query(JournalEntry).filter(JournalEntry.id == entry_id).first()
            assert deleted_entry is None
            db.close()
    
    def test_delete_journal_entry_not_found(self):
        """Test deletion of non-existent journal entry"""
        with self.mock_firebase_auth():
            fake_id = uuid4()
            response = self.client.delete(
                f"/journal/{fake_id}",
                headers={"Authorization": "Bearer fake_token"}
            )
            
            assert response.status_code == 404
            assert "Entry not found" in response.json()["detail"]
    
    def test_delete_journal_entry_unauthorized_user(self):
        """Test deletion of entry by different user (should fail)"""
        # Create entry with one user
        db = self.SessionLocal()
        other_user_id = uuid4()
        other_user = User(
            id=other_user_id,
            firebase_user_id="other_user_firebase_123",
            email="other@example.com"
        )
        db.add(other_user)
        
        entry = JournalEntry(
            title="Other User's Entry",
            content="This belongs to another user",
            local_timestamp=datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc),
            user_id=other_user_id,
            week="2024-W03",
            month="2024-01"
        )
        db.add(entry)
        db.commit()
        db.refresh(entry)
        entry_id = entry.id
        db.close()
        
        # Try to delete with different user
        with self.mock_firebase_auth():
            response = self.client.delete(
                f"/journal/{entry_id}",
                headers={"Authorization": "Bearer fake_token"}
            )
            
            assert response.status_code == 403
            assert "Unauthorized" in response.json()["detail"]
    
    def test_delete_journal_entry_unauthorized(self):
        """Test journal entry deletion without authentication"""
        fake_id = uuid4()
        response = self.client.delete(f"/journal/{fake_id}")
        assert response.status_code == 403
    
    def test_week_and_month_calculation(self):
        """Test correct week and month calculation for various dates"""
        test_cases = [
            ("2024-01-01T00:00:00+00:00", "2024-W01", "2024-01"),  # New Year
            ("2024-12-31T23:59:59+00:00", "2025-W01", "2024-12"),  # New Year's Eve (ISO week belongs to next year)
            ("2024-07-04T12:00:00+00:00", "2024-W27", "2024-07"),  # Mid year
            ("2024-02-29T12:00:00+00:00", "2024-W09", "2024-02"),  # Leap year
        ]
        
        with self.mock_firebase_auth():
            for timestamp, expected_week, expected_month in test_cases:
                journal_data = {
                    "title": f"Test for {timestamp}",
                    "content": "Testing date calculations",
                    "local_timestamp": timestamp
                }
                
                response = self.client.post(
                    "/journal",
                    json=journal_data,
                    headers={"Authorization": "Bearer fake_token"}
                )
                
                assert response.status_code == 200
                data = response.json()
                assert data["week"] == expected_week, f"Week mismatch for {timestamp}"
                assert data["month"] == expected_month, f"Month mismatch for {timestamp}"
                
                # Clean up
                self.setup_method()
    
    def test_journal_entry_persistence(self):
        """Test that journal entries are properly persisted in database"""
        with self.mock_firebase_auth():
            journal_data = {
                "title": "Persistence Test",
                "content": "Testing database persistence",
                "local_timestamp": "2024-03-15T14:30:00+00:00"
            }
            
            response = self.client.post(
                "/journal",
                json=journal_data,
                headers={"Authorization": "Bearer fake_token"}
            )
            
            assert response.status_code == 200
            entry_id = response.json()["id"]
            
            # Verify in database directly
            db = self.SessionLocal()
            db_entry = db.query(JournalEntry).filter(JournalEntry.id == entry_id).first()
            
            assert db_entry is not None
            assert db_entry.title == journal_data["title"]
            assert db_entry.content == journal_data["content"]
            assert db_entry.user_id == self.test_user_id
            assert db_entry.week == "2024-W11"
            assert db_entry.month == "2024-03"
            
            db.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])