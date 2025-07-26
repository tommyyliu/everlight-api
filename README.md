# Everlight API Service

A REST API service for the Everlight platform handling CRUD operations and integrations.

## Overview

This service handles:
- User management
- Journal entries CRUD
- Notes management
- Raw entries processing
- Integration token management
- Slate operations
- Message persistence

## Setup

1. Install dependencies:
```bash
uv pip install -r requirements.txt
```

2. Set up environment variables:
```bash
cp .env.example .env
# Edit .env with your actual values
```

3. Run the service:
```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

## API Endpoints

- `GET /health` - Health check
- `POST /users` - Create user
- `GET /users/{user_id}` - Get user
- `POST /journal-entries` - Create journal entry
- `GET /journal-entries` - List journal entries
- `POST /notes` - Create note
- `GET /notes` - List notes
- `POST /raw-entries` - Create raw entry
- `GET /raw-entries` - List raw entries
- `GET /slate/{user_id}` - Get slate
- `PUT /slate/{user_id}` - Update slate
- `POST /messages` - Send message
- `GET /messages` - List messages

## Architecture

The service provides REST API endpoints for all CRUD operations and manages integrations. It communicates with the everlight-agents service for AI processing and shares the same database.