from psycopg_pool import AsyncConnectionPool
from psycopg.rows import dict_row


async def upsert_thread(pool: AsyncConnectionPool, thread_id: str, user_id: str, title: str):

    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                INSERT INTO threads (thread_id, user_id, title, updated_at)
                VALUES (%s, %s, %s, NOW())
                ON CONFLICT (thread_id) 
                DO UPDATE SET updated_at = NOW()
            """, (thread_id, user_id, title))


async def get_user_threads(pool: AsyncConnectionPool, user_id: str):
    """
    Fetches chats using the passed pool.
    """
    async with pool.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute("""
                SELECT thread_id, title, created_at 
                FROM threads 
                WHERE user_id = %s 
                ORDER BY updated_at DESC
            """, (user_id,))
            
            results = await cur.fetchall()
            return results
        
