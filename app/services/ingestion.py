import shutil
import re
from pathlib import Path
import time

from fastapi import UploadFile

from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.base_models import InputFormat 
from docling.datamodel.pipeline_options import (
    PdfPipelineOptions, 
    TableFormerMode,
    PictureDescriptionApiOptions,
    EasyOcrOptions
)
from docling.datamodel.accelerator_options import AcceleratorDevice, AcceleratorOptions
from docling_core.transforms.chunker.hybrid_chunker import HybridChunker
from docling_core.types.doc.document import TableItem
from docling_core.types.doc.labels import DocItemLabel

from langchain_core.documents import Document

from fastapi import Depends

from app.core.config import settings
from app.services.vector_store import vector_store_service

class IngestionService:
    ALLOWED_EXTENSIONS = {
        InputFormat.PDF: {".pdf"},
        InputFormat.IMAGE: {".png", ".jpg", ".jpeg", ".tiff", ".bmp"},
        InputFormat.DOCX: {".docx"},
        InputFormat.HTML: {".html", ".htm"},
        InputFormat.PPTX: {".pptx"},
        InputFormat.ASCIIDOC: {".asciidoc", ".adoc"},
        InputFormat.CSV: {".csv"},
        InputFormat.MD: {".md", ".markdown"},
    }

    SUPPORTED_EXTENSIONS_FLAT = {
        ext for exts in ALLOWED_EXTENSIONS.values() for ext in exts
    }

    def __init__(self):
        pipeline_options = self._setup_pipeline_options()
        self.converter = DocumentConverter(
            allowed_formats=[f for f in self.ALLOWED_EXTENSIONS.keys()],
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
            }
        )

    def _get_device_type(self, device_str: str) -> AcceleratorDevice:
        if device_str.lower() == "cuda":
            return AcceleratorDevice.CUDA
        elif device_str.lower() == "cpu":
            return AcceleratorDevice.CPU
        else:
            return AcceleratorDevice.AUTO

    def _setup_pipeline_options(self) -> PdfPipelineOptions:
        
        # Accelerator Options
        accelerator_options = AcceleratorOptions(
            num_threads=settings.DOCLING_NUM_THREADS,
            device=self._get_device_type(settings.DOCLING_DEVICE)
        )

        # Vision Language Model (Ollama) Options
        picture_options = PictureDescriptionApiOptions(
            url=settings.OLLAMA_BASE_URL,
            params=dict(
                model=settings.OLLAMA_VLM_MODEL,
                stream=False,
                options=dict(
                    num_predict=200,
                    temperature=settings.VLM_TEMPERATURE,
                ),
            ),
            prompt=settings.VLM_PROMPT,
            timeout=settings.VLM_TIMEOUT,
        )

        picture_options_open_router = PictureDescriptionApiOptions(
            url=settings.OPEN_ROUTER_VLM_BASE_URL,
            headers={"Authorization": f"Bearer {settings.OPEN_ROUTER_API}"},
            params=dict(
                model=settings.OPEN_ROUTER_VLM_MODEL,
                stream=False,
                options=dict(
                    num_predict=200,
                    temperature=settings.VLM_TEMPERATURE,
                ),
            ),
            prompt=settings.VLM_PROMPT,
            timeout=settings.VLM_TIMEOUT,
        )


        # Main Pipeline Options
        options = PdfPipelineOptions()
        options.do_ocr = True
        options.ocr_options = EasyOcrOptions(
            force_full_page_ocr=True, 
        )
        options.do_table_structure = True
        options.table_structure_options.mode = TableFormerMode.ACCURATE
        options.accelerator_options = accelerator_options
        options.enable_remote_services = True
        options.images_scale = 3
        options.generate_picture_images = True
        options.do_picture_description = True
        options.picture_description_options = picture_options_open_router
        
        return options
    
    
    def validate_file(self, filename: str) -> bool:
        """Checks if the file extension is allowed."""
        ext = Path(filename).suffix.lower()
        # 3. Fast lookup using the pre-calculated set
        return ext in self.SUPPORTED_EXTENSIONS_FLAT

    def _sanitize_filename(self, filename: str) -> str:
        clean_name = re.sub(r'[^a-zA-Z0-9_.-]', '_', filename)
        return clean_name

    def savefile(self, file: UploadFile, user_id: str) -> Path:
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
    
    def docling_conversions(self, destination_paths: list[Path]):
        print("🚀 Converting...")
        conversions = {}
        for path in destination_paths:
            print(f"Processing: {path.name}...")
            
            try:
                result = self.converter.convert(path)

                conversions[path] = result.document
                print(f"✅ Success: {path.name}")
                
                time.sleep(2) 
                
            except Exception as e:
                print(f"❌ Failed: {path.name}")
                print(e)

        print(f"\nCompleted. Converted {len(conversions)} documents.")
        return conversions
    
    #Hybrid Chunking
    def chunk_documents(self, conversions:dict, user_id: str, filename_to_db_id: dict):
        doc_id = 0
        texts: list[Document] = []

        for source, docling_document in conversions.items():
            file_id = filename_to_db_id.get(source.name)

            for chunk in HybridChunker(tokenizer=settings.TOKEN_MODEL_ID,
                                       max_tokens=512,
                                       merge_peers=True).chunk(docling_document):
                items = chunk.meta.doc_items
                if len(items) == 1 and isinstance(items[0], TableItem):
                    continue # process tables later
                refs = " ".join(map(lambda item: item.get_ref().cref, items))
                text = chunk.text
                document = Document(
                    page_content=text,
                    metadata={
                        "doc_id": (doc_id:=doc_id+1),
                        "source": str(source),
                        "file_id": file_id,
                        "filename": source.name,
                        "ref": refs,
                        "user_id": user_id,
                    },

                )
                texts.append(document)

        doc_id = len(texts)

        tables: list[Document] = []
        for source, docling_document in conversions.items():
            file_id = filename_to_db_id.get(source.name)
            for table in docling_document.tables:
                if table.label in [DocItemLabel.TABLE]:
                    page_no = table.prov[0].page_no if table.prov else 0
                    ref = table.get_ref().cref
                    text = table.export_to_markdown(doc=docling_document)
                    document = Document(
                        page_content=text,
                        metadata={
                            "doc_id": (doc_id:=doc_id+1),
                            "source": str(source),
                            "type": "table",
                            "file_id": file_id,
                            "filename": source.name,
                            "page": page_no,
                            "ref": ref,
                            "user_id": user_id,
                        },
                    )
                    tables.append(document)


        print(f"{len(tables)} table documents created")
        print("Chunks created successfully")
        return texts + tables
    


    #Entire Pipleine
    def run_ingestion_pipeline(self, filepaths: list[Path], user_id:str):
        """
        docling -> hybridchunking -> vectordatabase
        """
        conversions = self._docling_conversions(filepaths)
        chunks = self._chunk_documents(conversions, user_id)

        if chunks:
            vector_store_service.add_chunks(chunks)
    
            return len(chunks)


ingestion_service = IngestionService()