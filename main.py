from api import journal_endpoints, integration_endpoints, brief_endpoints

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Everlight API Service")

origins = [
    "http://localhost",
    "http://localhost:5173",
    "http://localhost:5173/",
    "http://localhost:5174",
    "http://localhost:5174/",
    "https://b5d2af84.everlight-97q.pages.dev/",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(journal_endpoints.router)
app.include_router(integration_endpoints.router)
app.include_router(brief_endpoints.router)

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "everlight-api"}