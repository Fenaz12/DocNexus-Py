from app.core.celery_app import celery_app
from app.services.dbservice import file_db

# REMOVED: get_ingestion_service, get_vector_store_service (to prevent heavy loads)
# REMOVED: docling imports

@celery_app.task(bind=True)
def task_ingest_files(self, file_paths_str: list[str], file_ids: list[int], user_id: str):
    """
    Mocked task for Demo Version
    """
    print(f"⚠️ DEMO MODE: Skipping processing for {len(file_paths_str)} files.")
    
    # Mark files as failed or completed-with-warning so the UI updates
    try:
        for fid in file_ids:
            # You can set this to 'failed' or 'completed' depending on what you want the UI to show
            file_db.update_progress(
                fid, 
                stage='completed', 
                status='Demo Mode - Ingestion Disabled', 
                job_stats={}
            )
            
        return {
            "status": "skipped",
            "reason": "Demo Mode enabled - Ingestion libraries removed to improve startup time.",
            "files": file_paths_str
        }

    except Exception as e:
        print(f"❌ Error in mock task: {e}")
        return {"status": "failed", "error": str(e)}