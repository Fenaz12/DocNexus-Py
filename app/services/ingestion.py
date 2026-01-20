import shutil
import re
from pathlib import Path
from fastapi import UploadFile
from functools import lru_cache

# REMOVED: All docling, pytorch, and easyocr imports
# REMOVED: chunking libraries

from app.core.config import settings
from app.services.vector_store import get_vector_store_service, VectorStoreService

class IngestionService:
    # Keep these constants so validation doesn't break
    ALLOWED_EXTENSIONS = {
        "PDF": {".pdf"},
        "IMAGE": {".png", ".jpg", ".jpeg", ".tiff", ".bmp"},
        "DOCX": {".docx"},
        "HTML": {".html", ".htm"},
        "PPTX": {".pptx"},
        "ASCIIDOC": {".asciidoc", ".adoc"},
        "CSV": {".csv"},
        "MD": {".md", ".markdown"},
    }

    SUPPORTED_EXTENSIONS_FLAT = {
        ext for exts in ALLOWED_EXTENSIONS.values() for ext in exts
    }

    def __init__(self):
        # REMOVED: Pipeline setup, converter initialization, and model loading
        pass

    def validate_file(self, filename: str) -> bool:
        """Checks if the file extension is allowed."""
        ext = Path(filename).suffix.lower()
        return ext in self.SUPPORTED_EXTENSIONS_FLAT

    def _sanitize_filename(self, filename: str) -> str:
        clean_name = re.sub(r'[^a-zA-Z0-9_.-]', '_', filename)
        return clean_name

    def savefile(self, file: UploadFile, user_id: str) -> Path:
        """Keeps file saving logic so uploads don't crash the server immediately"""
        user_dir = settings.BASE_UPLOAD_DIR / user_id
        user_dir.mkdir(parents=True, exist_ok=True)

        clean_filename = self._sanitize_filename(file.filename)
        destination_path = user_dir / clean_filename

        try:
            with destination_path.open("wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
        finally:
            file.file.close()
            
        return destination_path
    
    # --- MOCKED METHODS BELOW ---
    
    def docling_conversions(self, destination_paths: list[Path]):
        print("⚠️ DEMO MODE: Docling conversion disabled.")
        return {} # Return empty dict to prevent crashes

    def chunk_documents(self, conversions:dict, user_id: str, filename_to_db_id: dict):
        print("⚠️ DEMO MODE: Chunking disabled.")
        return [] # Return empty list

    def run_ingestion_pipeline(self, filepaths: list[Path], user_id:str,
                               vector_service: VectorStoreService):
        print("⚠️ DEMO MODE: Pipeline disabled.")
        return 0

@lru_cache()
def get_ingestion_service():
    return IngestionService()