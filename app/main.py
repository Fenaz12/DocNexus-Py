# app/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from psycopg_pool import AsyncConnectionPool
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver 
from app.core.config import settings
from app.api.router import api_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 Starting Application...")

    # 2. Lazy Load Postgres (Don't crash if it fails)
    try:
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
        print("✅ Database Connected!")
        
    except Exception as e:

        print(f"⚠️ Startup Warning: DB connection failed: {e}")
    print("✅ Server is ready!")
    yield 
    
    print("🛑 Shutting down...")
    if hasattr(app.state, "pool"):
        await app.state.pool.close()

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)

@app.get("/")
def health_check():
    return {"status": "running"}