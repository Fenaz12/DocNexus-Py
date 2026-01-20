from typing import Annotated
from fastapi import APIRouter, File, UploadFile, HTTPException
from fastapi import Depends
from app.api.endpoints.dependencies import get_current_user_id
from app.services.ingestion import get_ingestion_service, IngestionService
from app.services.tasks import task_ingest_files
import traceback
from celery.result import AsyncResult
from app.core.celery_app import celery_app
from app.core.config import settings
from app.services.dbservice import file_db
from app.services.vector_store import get_vector_store_service, VectorStoreService
import json

router = APIRouter()


@router.post("/upload/")
async def create_upload_files(
    files: Annotated[list[UploadFile], File(description="Multiple files as UploadFile")],
    user_id: str = Depends(get_current_user_id),
    ingestion_service: IngestionService = Depends(get_ingestion_service),
):

    for file in files:
        if not ingestion_service.validate_file(file.filename):
            raise HTTPException(
                status_code=400,
                detail=f"File type not supported. Allowed: {ingestion_service.ALLOWED_EXTENSIONS}"
            )
    
    file_paths = []
    file_ids = []
    file_records = []
    
    try:
        for file in files:
            saved_path = ingestion_service.savefile(file, user_id)
            file_size = saved_path.stat().st_size
            
            # DB Record created as usual
            fid = file_db.create_file_record(user_id, file.filename, str(saved_path), file_size)
            
            file_paths.append(saved_path)
            file_ids.append(fid)
            file_records.append({
                "id": fid,
                "filename": file.filename,
                "status": "processing",
                "stage": "queued"
            })
        
        str_paths = [str(p) for p in file_paths]
        
        task = task_ingest_files.delay(str_paths, file_ids, user_id)
        
        return {
            "status": "processing_started",
            "task_id": task.id,
            "files_queued": len(file_paths),
            "files": file_records,
            "message": "Demo Mode: Files uploaded (Ingestion Skipped)."
        }
        
    except Exception as e:
        print("❌ ERROR TRACEBACK:")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Processing files failed: {str(e)}")


@router.get("/task/{task_id}")
async def get_task_status(
    task_id: str,
    user_id: str = Depends(get_current_user_id)
):
    """
    New File upload - not used in demo
    """
    task = AsyncResult(task_id, app=celery_app)
    
    response = {
        'state': task.state,
        'status': 'Unknown state',
        'stage_data': {}
    }

    if task.state == 'PENDING':
        response['status'] = 'Task is queued...'
    elif task.state == 'PROGRESS':
        response.update({
            'current_stage': task.info.get('current_stage', ''),
            'progress': task.info.get('progress', 0),
            'status': task.info.get('status', ''),
            'stage_data': task.info.get('stage_data', {}) 
        })
    elif task.state == 'SUCCESS':
        response.update({
            'result': task.result,
            'status': 'Completed successfully',
            'stage_data': task.info.get('final_stats', {}) 
        })
    elif task.state == 'FAILURE':
        response['status'] = str(task.info)
    
    return response


@router.get("/user-files/")
async def get_user_files(user_id: str = Depends(get_current_user_id)):
    """
    Standard file listing.
    """
    user_dir = settings.BASE_UPLOAD_DIR / user_id
    if not user_dir.exists():
        return {"files": []}
    
    files = []
    for file_path in user_dir.iterdir():
        if file_path.is_file():
            stat = file_path.stat()
            files.append({
                "name": file_path.name,
                "size": stat.st_size,
                "uploaded_at": stat.st_mtime,
                "path": str(file_path)
            })
    files.sort(key=lambda x: x["uploaded_at"], reverse=True)
    return {"files": files}

@router.get("/")
async def get_user_files_with_metadata(user_id: str = Depends(get_current_user_id)):
    """
    Get jobstats from db
    """
    try:
        files = file_db.get_user_files(user_id)
        response_files = []
        for file in files:
            response_files.append({
                "id": file['id'],
                "name": file['filename'],
                "size": file['file_size'],  
                "uploaded_at": file['created_at'].timestamp() if file['created_at'] else None,
                "status": file['status'],
                "stage": file['stage'],
                "job_stats": file['job_stats'] or {}, # <--- REAL DATA HERE
                "error_message": file['error_message']
            })
        return {"files": response_files}
    except Exception as e:
        print(f"❌ Error fetching files: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch files: {str(e)}")

@router.get("/{filename}/metadata")
async def get_file_metadata(filename: str, user_id: str = Depends(get_current_user_id)):
    """
    get complted file details
    """
    try:
        file_record = file_db.get_file_by_name(user_id, filename)
        if not file_record:
            raise HTTPException(status_code=404, detail="File not found")
        
        return {
            "id": file_record['id'],
            "filename": file_record['filename'],
            "status": file_record['status'],
            "stage": file_record['stage'],
            "job_stats": file_record['job_stats'] or {}, 
            "error_message": file_record['error_message'],
            "created_at": file_record['created_at'].isoformat() if file_record['created_at'] else None,
            "updated_at": file_record['updated_at'].isoformat() if file_record['updated_at'] else None
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error fetching metadata: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch metadata: {str(e)}")

@router.get("/{file_id}/chunks")
async def get_file_chunks(
    file_id: int,
    user_id: str = Depends(get_current_user_id),
    limit: int = 1000,
    vector_service: VectorStoreService = Depends(get_vector_store_service)
):
    """
    Fetch chunks from milvus
    """
    try:
        file_record = file_db.get_file_by_id(file_id)
        if not file_record or str(file_record['user_id']) != user_id:
            raise HTTPException(status_code=404, detail="File not found")

        chunks = vector_service.get_chunks_by_file_id(
            user_id=user_id,
            file_id=file_id,
            limit=limit
        )
                
        formatted_chunks = []
        for chunk in chunks:
            formatted_chunks.append({
                "content": chunk.page_content,
                "type": chunk.metadata.get("type", "text"),
                "page": chunk.metadata.get("page", None),
                "chars": len(chunk.page_content),
                "source": chunk.metadata.get("filename", ""),
                "doc_id": chunk.metadata.get("doc_id"),
                "ref": chunk.metadata.get("ref")
            })
            
        return {"chunks": formatted_chunks, "total": len(formatted_chunks)}
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error fetching chunks: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to fetch chunks: {str(e)}")