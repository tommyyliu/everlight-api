"""
Pytest configuration and fixtures for journal endpoint tests
"""
import pytest
import testing.postgresql
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from main import app
from db.models import Base
from db.session import get_db_session


@pytest.fixture(scope="session")
def postgresql_instance():
    """Create a PostgreSQL instance for the entire test session"""
    postgresql = testing.postgresql.Postgresql()
    yield postgresql
    postgresql.stop()


@pytest.fixture(scope="session")
def test_engine(postgresql_instance):
    """Create a test database engine"""
    engine = create_engine(postgresql_instance.url())
    Base.metadata.create_all(bind=engine)
    return engine


@pytest.fixture(scope="session")
def test_session_factory(test_engine):
    """Create a session factory for tests"""
    return sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture
def test_client(test_session_factory):
    """Create a test client with database dependency override"""
    def override_get_db_session():
        db = test_session_factory()
        try:
            yield db
        finally:
            db.close()
    
    app.dependency_overrides[get_db_session] = override_get_db_session
    
    with TestClient(app) as client:
        yield client
    
    # Clean up dependency override
    app.dependency_overrides.clear()


@pytest.fixture
def test_db_session(test_session_factory):
    """Create a database session for direct database operations in tests"""
    session = test_session_factory()
    try:
        yield session
    finally:
        session.close()