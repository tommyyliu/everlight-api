"""
PostgreSQL integration tests for journal endpoints with pgvector extension
"""
import pytest
import testing.postgresql
from datetime import datetime, timezone
from uuid import uuid4
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Import our application modules
from main import app
from db.session import get_db_session


class TestJournalEndpointsPostgreSQL:
    """Test class for journal endpoint integration tests with PostgreSQL"""
    
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
        
        # Install pgvector extension
        try:
            with cls.engine.connect() as conn:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                conn.commit()
        except Exception as e:
            # If pgvector is not available, skip these tests
            pytest.skip(f"pgvector extension not available: {e}")
        
        # Create only the tables we need for journal tests (excluding vector tables)
        # Create tables manually to avoid vector dependency issues
        with cls.engine.connect() as conn:
            # Create users table
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS users (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    firebase_user_id VARCHAR UNIQUE NOT NULL,
                    email VARCHAR UNIQUE NOT NULL,
                    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL
                )
            """))
            
            # Create journal_entries table
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS journal_entries (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    user_id UUID NOT NULL REFERENCES users(id),
                    title VARCHAR,
                    content TEXT NOT NULL,
                    local_timestamp TIMESTAMP WITHOUT TIME ZONE NOT NULL,
                    week VARCHAR NOT NULL,
                    month VARCHAR NOT NULL,
                    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL
                )
            """))
            
            conn.commit()
        
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
        
        with cls.engine.connect() as conn:
            conn.execute(text("""
                INSERT INTO users (id, firebase_user_id, email)
                VALUES (:id, :firebase_id, :email)
            """), {
                "id": str(cls.test_user_id),
                "firebase_id": cls.test_user_firebase_id,
                "email": cls.test_user_email
            })
            conn.commit()
    
    @classmethod
    def teardown_class(cls):
        """Clean up test database"""
        app.dependency_overrides.clear()
        cls.postgresql.stop()
    
    def setup_method(self):
        """Set up for each test method"""
        # Clear journal entries before each test
        with self.engine.connect() as conn:
            conn.execute(text("DELETE FROM journal_entries"))
            conn.commit()
    
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
        """Test successful journal entry creation with PostgreSQL"""
        with self.mock_firebase_auth():
            # Test data
            journal_data = {
                "title": "PostgreSQL Test Entry",
                "content": "This is a test journal entry using PostgreSQL.",
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
            
            # Verify in database
            with self.engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT title, content, week, month FROM journal_entries 
                    WHERE id = :entry_id
                """), {"entry_id": data["id"]})
                row = result.fetchone()
                assert row is not None
                assert row[0] == journal_data["title"]  # title
                assert row[1] == journal_data["content"]  # content
                assert row[2] == "2024-W03"  # week
                assert row[3] == "2024-01"  # month
    
    def test_delete_journal_entry_success(self):
        """Test successful journal entry deletion with PostgreSQL"""
        with self.mock_firebase_auth():
            # First create an entry directly in database
            entry_id = uuid4()
            with self.engine.connect() as conn:
                conn.execute(text("""
                    INSERT INTO journal_entries (id, title, content, local_timestamp, user_id, week, month)
                    VALUES (:id, :title, :content, :timestamp, :user_id, :week, :month)
                """), {
                    "id": str(entry_id),
                    "title": "Entry to Delete",
                    "content": "This entry will be deleted",
                    "timestamp": datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc),
                    "user_id": str(self.test_user_id),
                    "week": "2024-W03",
                    "month": "2024-01"
                })
                conn.commit()
            
            # Now delete it via API
            response = self.client.delete(
                f"/journal/{entry_id}",
                headers={"Authorization": "Bearer fake_token"}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["id"] == str(entry_id)
            assert data["title"] == "Entry to Delete"
            
            # Verify it's actually deleted from database
            with self.engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT COUNT(*) FROM journal_entries WHERE id = :entry_id
                """), {"entry_id": str(entry_id)})
                count = result.scalar()
                assert count == 0
    
    def test_user_isolation(self):
        """Test that users can only access their own entries"""
        # Create another user
        other_user_id = uuid4()
        with self.engine.connect() as conn:
            conn.execute(text("""
                INSERT INTO users (id, firebase_user_id, email)
                VALUES (:id, :firebase_id, :email)
            """), {
                "id": str(other_user_id),
                "firebase_id": "other_user_firebase_456",
                "email": "other@example.com"
            })
            
            # Create entry for other user
            entry_id = uuid4()
            conn.execute(text("""
                INSERT INTO journal_entries (id, title, content, local_timestamp, user_id, week, month)
                VALUES (:id, :title, :content, :timestamp, :user_id, :week, :month)
            """), {
                "id": str(entry_id),
                "title": "Other User's Entry",
                "content": "This belongs to another user",
                "timestamp": datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc),
                "user_id": str(other_user_id),
                "week": "2024-W03",
                "month": "2024-01"
            })
            conn.commit()
        
        # Try to delete with our test user (should fail)
        with self.mock_firebase_auth():
            response = self.client.delete(
                f"/journal/{entry_id}",
                headers={"Authorization": "Bearer fake_token"}
            )
            
            assert response.status_code == 403
            assert "Unauthorized" in response.json()["detail"]


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])