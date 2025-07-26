# Journal Endpoints Integration Tests

This directory contains comprehensive integration tests for the journal endpoints using `testing.postgresql` for database testing.

## Test Structure

### Files
- `test_journal_endpoints.py` - Main test file with all journal endpoint tests
- `conftest.py` - Pytest configuration and shared fixtures
- `test_runner.py` - Simple script to run tests

### Test Coverage

The tests cover the following scenarios:

#### Journal Entry Creation (`POST /journal`)
- ✅ Successful entry creation with title
- ✅ Successful entry creation without title
- ✅ Proper week/month calculation for various dates
- ✅ Authentication required
- ✅ Invalid token handling
- ✅ Missing required fields validation
- ✅ Database persistence verification

#### Journal Entry Deletion (`DELETE /journal/{entry_id}`)
- ✅ Successful entry deletion
- ✅ Entry not found handling
- ✅ Unauthorized user access prevention
- ✅ Authentication required
- ✅ Database cleanup verification

#### Edge Cases
- ✅ Week calculation across year boundaries
- ✅ Leap year handling
- ✅ Timezone handling
- ✅ User isolation (users can only access their own entries)

## Running Tests

### Prerequisites
Make sure you have PostgreSQL installed on your system as `testing.postgresql` requires it.

### Install Dependencies
```bash
cd everlight-api
pip install pytest testing-postgresql
```

### Run Tests
```bash
# Run all journal tests
python tests/test_runner.py

# Or use pytest directly
pytest tests/test_journal_endpoints.py -v

# Run specific test
pytest tests/test_journal_endpoints.py::TestJournalEndpoints::test_create_journal_entry_success -v
```

## Test Database

The tests use `testing.postgresql` which:
- Creates a temporary PostgreSQL instance for each test session
- Automatically cleans up after tests complete
- Provides full database isolation
- Supports all PostgreSQL features including pgvector extensions

## Authentication Mocking

Tests mock Firebase authentication using `unittest.mock.patch` to:
- Simulate valid user tokens
- Test authentication failure scenarios
- Control user identity for authorization tests

## Test Data

Tests create minimal test data:
- A test user with known UUID and Firebase ID
- Journal entries with various timestamps for date calculation testing
- Multiple users for authorization testing

Each test method starts with a clean database state to ensure test isolation.