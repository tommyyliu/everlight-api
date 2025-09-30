# Everlight API Service

A comprehensive REST API service for Everlight that provides journal management, Notion integration, and AI-powered content processing.

## Features

### Core Functionality
- **Journal Endpoints** - Create, read, update, delete journal entries
- **Notion Integration** - OAuth connection and automatic page import
- **Firebase Authentication** - Secure user management
- **Vector Embeddings** - Google Gemini-powered content embeddings
- **PostgreSQL Database** - With pgvector for similarity search

### API Endpoints
- `POST /journal` - Create journal entries
- `DELETE /journal/{entry_id}` - Delete journal entries
- `POST /integrations/notion/connect` - Connect Notion workspace
- `GET /integrations/notion/status` - Check Notion connection status
- `DELETE /integrations/notion/disconnect` - Disconnect Notion
- `GET /health` - Health check

## Setup

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Environment Variables
```bash
cp .env.example .env
# Configure your environment variables:
# - Database connection
# - Firebase credentials
# - Google Gemini API key
# - Notion OAuth credentials
# - AI Agent Service URL and token
```

Key environment variables:
- `DATABASE_URL` - PostgreSQL connection string
- `GOOGLE_APPLICATION_CREDENTIALS` - Firebase service account
- `GOOGLE_API_KEY` - For Gemini embeddings
- `NOTION_CLIENT_ID` / `NOTION_CLIENT_SECRET` - Notion OAuth
- `AI_AGENT_SERVICE_URL` - URL of AI agent service (e.g., everlight-agents)
- `AI_AGENT_SERVICE_TOKEN` - Optional bearer token for agent service auth

### 3. Run the Service
```bash
uvicorn main:app --reload
```

## Testing

### Run All Tests
```bash
# Smart test runner with fallbacks
python run_tests.py

# Or use pytest directly
pytest tests/ -v
```

### 4. Deploy
```gcloud run deploy --source .```

### Test Coverage
- **Journal Endpoints** - Full CRUD operations with authentication
- **Notion Integration** - Import functionality and error handling
- **Database Integration** - Both SQLite and PostgreSQL testing
- **Authentication** - Firebase token validation

## API Documentation

Once running, visit:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## Architecture

### Database Models
- `User` - Firebase-authenticated users
- `JournalEntry` - User journal entries with metadata
- `RawEntry` - Imported content with embeddings
- `IntegrationToken` - OAuth tokens for external services

### Key Components
- **FastAPI** - Web framework with automatic OpenAPI docs
- **SQLAlchemy** - Database ORM with async support
- **Firebase Admin** - Authentication and user management
- **Google Gemini** - AI embeddings and content processing
- **Notion Client** - Workspace integration and content import
- **pgvector** - Vector similarity search capabilities

## Integration Features

### Notion Integration
- OAuth 2.0 authentication flow
- Automatic page discovery and import
- Text extraction from all block types
- Rate-limited API calls (3 req/sec)
- Background processing with progress tracking
- Vector embedding generation for AI processing

### Future Integrations
- Gmail integration (placeholder endpoints ready)
- Calendar integration (placeholder endpoints ready)

## Security

- Firebase ID token validation
- User data isolation
- Encrypted integration tokens
- CORS configuration for web clients
- Input validation with Pydantic models

## Monitoring

- Health check endpoint
- Comprehensive error handling
- Request/response logging
- Database connection monitoring