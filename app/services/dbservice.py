import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Json
from app.core.config import settings
from datetime import datetime

class FileDBService:
    def __init__(self):
        # Synchronous connection string for Celery
        self.dsn = settings.DB_URI

    def get_connection(self):
        return psycopg.connect(self.dsn, row_factory=dict_row, autocommit=True)

    def create_file_record(self, user_id: str, filename: str, path: str, file_size: str):
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO user_files (user_id, filename, file_path, file_size, status, stage, job_stats)
                    VALUES (%s, %s, %s, %s, 'processing', 'queued', '{}')
                    RETURNING id
                """, (user_id, filename, str(path), file_size))
                return cur.fetchone()['id']

    def update_progress(self, file_id: int, stage: str, status: str = 'processing', job_stats: dict = None):
        """
        Updates the stage and dumps the full stats dictionary into JSONB
        """
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                # We use Json(job_stats) to ensure it serializes correctly for Postgres
                cur.execute("""
                    UPDATE user_files 
                    SET stage = %s, 
                        status = %s, 
                        job_stats = %s,
                        updated_at = %s
                    WHERE id = %s
                """, (stage, status, Json(job_stats) if job_stats else None, datetime.now(), file_id))

    def mark_failed(self, file_id: int, error: str):
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE user_files 
                    SET status = 'failed', error_message = %s, updated_at = %s
                    WHERE id = %s
                """, (str(error), datetime.now(), file_id))


    def get_file_by_name(self, user_id: str, filename: str):
        """Get a single file record by filename"""
        
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, user_id, filename, file_path,file_size,  status, stage, 
                        job_stats, error_message, created_at, updated_at
                    FROM user_files
                    WHERE user_id = %s AND filename = %s
                    ORDER BY created_at DESC
                    LIMIT 1
                """, (user_id, filename))
                return cur.fetchone()


    def get_user_files(self, user_id: str):
        """Get all files for a user with their metadata"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, user_id, filename, file_path, file_size, status, stage, 
                        job_stats, error_message, created_at, updated_at
                    FROM user_files
                    WHERE user_id = %s
                    ORDER BY created_at DESC
                """, (user_id,))
                return cur.fetchall()


    def get_file_metadata(self, file_id: int, user_id: str):
        """Get detailed metadata for a specific file"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, user_id, filename, file_path, file_size, status, stage, 
                        job_stats, error_message, created_at, updated_at
                    FROM user_files
                    WHERE id = %s AND user_id = %s
                """, (file_id, user_id))
                return cur.fetchone()
    
    def get_file_by_id(self, file_id: int):
        """Get a single file record by ID"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, user_id, filename, file_path, status, stage, 
                        job_stats, error_message, created_at, updated_at
                    FROM user_files
                    WHERE id = %s
                """, (file_id,))
                return cur.fetchone()



file_db = FileDBService()