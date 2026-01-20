from dotenv import load_dotenv
load_dotenv()

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from psycopg_pool import AsyncConnectionPool

from app.core.config import settings
from app.api.router import api_router
from app.services.vector_store import vector_store_service 
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver 

import os
from pathlib import Path
from dotenv import load_dotenv

# 1. Define the path explicitly relative to this file
# This says: "Get the folder where main.py is, and look for .env inside it"
env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=env_path)



@asynccontextmanager
async def lifespan(app: FastAPI):

    # 1. Initialize Vector Store (Milvus)
    print("🔌 Checking Vector Store connection...")
    vector_store_service.ensure_vectoredb_exists()

    # 2. Initialize Postgres Pool
    print("🏊 Creating Database Pool...")
    app.state.pool = AsyncConnectionPool(
        conninfo=settings.DB_URI,
        max_size=20,
        kwargs={"autocommit": True, "prepare_threshold": None},
        open=False
    )
    await app.state.pool.open()
    checkpointer = AsyncPostgresSaver(app.state.pool)
    await checkpointer.setup()
    print("✅ All systems ready!")
    
    yield 
    
    print("🛑 Shutting down...")
    await app.state.pool.close()
    print("👋 Goodbye!")

# Initialize the app with the lifespan logic
app = FastAPI(lifespan=lifespan)

# Add CORS Middleware (Security)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register your routes
app.include_router(api_router)

@app.get("/")
def health_check():
    return {"status": "running"}