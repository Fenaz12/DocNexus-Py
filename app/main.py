from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from psycopg_pool import AsyncConnectionPool
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver 

from app.core.config import settings
from app.api.router import api_router
# CHANGE 1: Import the function, not the variable
from app.services.vector_store import get_vector_store_service

@asynccontextmanager
async def lifespan(app: FastAPI):

    # 1. Initialize Vector Store (Milvus)
    # CHANGE 2: Call the function to get the instance
    print("🔌 Checking Vector Store connection...")
    try:
        get_vector_store_service().ensure_vectoredb_exists()
    except Exception as e:
        print(f"⚠️ Warning: Vector Store setup failed (Check Milvus Connection): {e}")

    # 2. Initialize Postgres Pool
    print("🏊 Creating Database Pool...")
    try:
        app.state.pool = AsyncConnectionPool(
            conninfo=settings.DB_URI,
            max_size=20,
            kwargs={"autocommit": True, "prepare_threshold": None},
            open=False
        )
        await app.state.pool.open()
        
        # 3. Setup Checkpointer (Create tables if not exist)
        checkpointer = AsyncPostgresSaver(app.state.pool)
        await checkpointer.setup()
        
        print("✅ All systems ready!")
        
        yield 
        
    except Exception as e:
        print(f"❌ Startup Error: {e}")
        # We yield here so the app doesn't crash immediately, giving you a chance to see the logs
        yield
        
    finally:
        # Cleanup
        print("🛑 Shutting down...")
        if hasattr(app.state, "pool"):
            await app.state.pool.close()
        print("👋 Goodbye!")

# Initialize the app with the lifespan logic
app = FastAPI(lifespan=lifespan)

# Add CORS Middleware
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
    return {"status": "running", "env": "production"}