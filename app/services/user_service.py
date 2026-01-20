from typing import Optional
import uuid
from psycopg_pool import AsyncConnectionPool
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

async def create_user(pool: AsyncConnectionPool, email: str, password: str) -> dict:
    """Create a new user in the database"""
    password_hash = pwd_context.hash(password)
    username = email.split('@')[0]  # Simple username from email
    
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            try:
                await cur.execute(
                    """
                    INSERT INTO users (email, username, password_hash)
                    VALUES (%s, %s, %s)
                    RETURNING id, email, username, created_at
                    """,
                    (email, username, password_hash)
                )
                row = await cur.fetchone()
                if row:
                    return {
                        "id": str(row[0]),
                        "email": row[1],
                        "username": row[2],
                        "created_at": row[3]
                    }
            except Exception as e:
                if "unique constraint" in str(e).lower():
                    raise ValueError("Email already registered")
                raise e

async def get_user_by_email(pool: AsyncConnectionPool, email: str) -> Optional[dict]:
    """Retrieve user by email"""
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT id, email, username, password_hash, is_active
                FROM users
                WHERE email = %s
                """,
                (email,)
            )
            row = await cur.fetchone()
            if row:
                return {
                    "id": str(row[0]),
                    "email": row[1],
                    "username": row[2],
                    "password_hash": row[3],
                    "is_active": row[4]
                }
            return None

async def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against hash"""
    return pwd_context.verify(plain_password, hashed_password)

async def get_user_by_id(pool: AsyncConnectionPool, user_id: str) -> Optional[dict]:
    """Retrieve user by ID"""
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT id, email, username, is_active
                FROM users
                WHERE id = %s
                """,
                (uuid.UUID(user_id),)
            )
            row = await cur.fetchone()
            if row:
                return {
                    "id": str(row[0]),
                    "email": row[1],
                    "username": row[2],
                    "is_active": row[3]
                }
            return None
