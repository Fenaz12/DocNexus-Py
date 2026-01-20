from fastapi import APIRouter
from app.api.endpoints import ingest, chat, auth

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(ingest.router, prefix="/files", tags=["Ingestion"])
api_router.include_router(chat.router, prefix="/chat", tags=["Chat"])
