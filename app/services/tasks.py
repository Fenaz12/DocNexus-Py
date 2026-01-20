from app.core.celery_app import celery_app
from app.services.ingestion import get_ingestion_service
from app.services.vector_store import get_vector_store_service
from app.services.dbservice import file_db

from pathlib import Path

from docling.datamodel.document import DocItemLabel


def extract_docling_stats(conversions: dict):
    """
    Parses the Docling output to create detailed stats
    """
    results = {}

    for path, doc in conversions.items():
        filename = path.name if hasattr(path, 'name') else str(path).split('/')[-1]
        total_images = len(doc.pictures)
        images_with_desc = 0
        
        for pic in doc.pictures:
            has_description = False
            if hasattr(pic, "annotations") and pic.annotations:
                for annotation in pic.annotations:
                    if annotation.kind == "description" and annotation.text and annotation.text.strip():
                        has_description = True
                        break

            if has_description:
                images_with_desc += 1

        text_sections = 0
        formulas = 0
        other = 0

        for item in doc.texts:
            if item.label == DocItemLabel.TEXT:
                text_sections += 1
            if item.label == DocItemLabel.PARAGRAPH:
                text_sections += 1
            elif item.label == DocItemLabel.FORMULA:
                formulas += 1
            else:
                other += 1

        total_kv_items = len(doc.key_value_items) if hasattr(doc, "key_value_items") else 0
                
        grand_total_elements = (
            len(doc.texts) + 
            len(doc.pictures) + 
            len(doc.tables) + 
            total_kv_items
        )

        stats = {
            "text_sections": text_sections,
            "formulas": formulas,
            "tables": len(doc.tables),
            "other": other,
            
            # Detailed Image Stats
            "images_total": total_images,
            "images_with_desc": images_with_desc,
            "total_elements_count": grand_total_elements,
            "page_count": len(doc.pages),

        }

        # Construct final object for this file
        results[filename] = {
            "filename": filename,
            "page_count": len(doc.pages),
            "stats": stats
        }

    return results


@celery_app.task(bind=True)
def task_ingest_files(self, file_paths_str: list[str], file_ids: list[int], user_id: str):
    # CHANGE 2: Initialize the services HERE, inside the task
    # This ensures they only load when the worker actually starts processing a job
    ingestion_service = get_ingestion_service()
    vector_store_service = get_vector_store_service()

    path_to_db_id = {}
    filename_to_db_id = {}
    real_paths = [Path(p) for p in file_paths_str]
    
    try:
        for path, fid in zip(real_paths, file_ids):
            path_to_db_id[str(path)] = fid
            filename_to_db_id[path.name] = fid
    except Exception as e:
        print(f"❌ DB Error: {e}")
        return {"status": "failed", "error": "Could not initialize database records"}
    
    files_stats = {filename: {'partitioning': None, 'chunking': None, 'vectorization': None} 
                   for filename in filename_to_db_id.keys()}

    print(f"👷 Worker received {len(file_paths_str)} files to process.")
    
    try:
        self.update_state(
            state='PROGRESS',
            meta={
                'current_stage': 'queued', 
                'progress': 10, 
                'status': 'Files queued for processing',
                'files_stats': files_stats
            }
        )
        
        # PARTITIONING
        self.update_state(
            state='PROGRESS',
            meta={
                'current_stage': 'partitioning', 
                'progress': 30, 
                'status': 'Converting documents with Docling',
                'files_stats': files_stats
            }
        )

        # Now we use the local 'ingestion_service' variable we created above
        conversions = ingestion_service.docling_conversions(real_paths)
        conversions_stats = extract_docling_stats(conversions)

        for filename, file_data in conversions_stats.items():
            fid = filename_to_db_id[filename]
            files_stats[filename]['partitioning'] = file_data['stats']
            
            job_stats = {
                'partitioning': file_data['stats'],
                'chunking': None,
                'vectorization': None
            }
            file_db.update_progress(fid, stage='partitioned', job_stats=job_stats)

        self.update_state(
            state='PROGRESS',
            meta={
                'current_stage': 'partitioning', 
                'progress': 40, 
                'status': 'Partitioning complete',
                'files_stats': files_stats 
            }
        )

        if not conversions:
            raise ValueError("Document conversion failed or returned empty.")

        # CHUNKING
        self.update_state(
            state='PROGRESS',
            meta={
                'current_stage': 'chunking', 
                'progress': 60, 
                'status': 'Creating chunks with hybrid chunker',
                'files_stats': files_stats
            }
        )   
        
        chunks = ingestion_service.chunk_documents(conversions, user_id, filename_to_db_id)
        
        chunks_by_filename = {}
        for chunk in chunks:
            source_path = Path(chunk.metadata['source'])
            filename = source_path.name
            if filename not in chunks_by_filename:
                chunks_by_filename[filename] = []
            chunks_by_filename[filename].append(chunk)

        for filename, fid in filename_to_db_id.items():
            file_chunks = chunks_by_filename.get(filename, [])
            
            avg_size = 0
            if file_chunks:
                total_chars = sum(len(c.page_content) for c in file_chunks)
                avg_size = total_chars // len(file_chunks)
            
            files_stats[filename]['chunking'] = {
                'atomic_elements': files_stats[filename]['partitioning']['total_elements_count'],
                'chunks_created': len(file_chunks),
                'avg_chunk_size': avg_size
            }
            
            job_stats = {
                'partitioning': files_stats[filename]['partitioning'],
                'chunking': files_stats[filename]['chunking'],
                'vectorization': None
            }
            file_db.update_progress(fid, stage='chunked', job_stats=job_stats)

        self.update_state(
            state='PROGRESS',
            meta={
                'current_stage': 'chunking', 
                'progress': 80, 
                'status': 'Hybrid Chunking Completed',
                'files_stats': files_stats  
            }
        )
        
        # VECTORIZATION
        self.update_state(
            state='PROGRESS',
            meta={
                'current_stage': 'vectorization', 
                'progress': 90, 
                'status': 'Storing in vector database',
                'files_stats': files_stats
            }
        )
        
        if chunks:
            # Using the local vector_store_service instance
            vector_store_service.add_chunks(chunks)

        for filename, fid in filename_to_db_id.items():
            file_chunks = chunks_by_filename.get(filename, [])
            
            files_stats[filename]['vectorization'] = {
                'vectors_created': len(file_chunks)
            }
            
            job_stats = {
                'partitioning': files_stats[filename]['partitioning'],
                'chunking': files_stats[filename]['chunking'],
                'vectorization': files_stats[filename]['vectorization']
            }
            file_db.update_progress(fid, stage='completed', status='completed', job_stats=job_stats)

        return {
            "status": "success",
            "processed_count": len(chunks),
            "files": file_paths_str,
            "user_id": user_id,
            "files_stats": files_stats 
        }

    except Exception as e:
        print(f"❌ Task Failed: {e}")
        for fid in path_to_db_id.values():
            file_db.mark_failed(fid, str(e))
        raise e