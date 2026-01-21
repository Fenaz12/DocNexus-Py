from pymilvus import connections, db, utility, Collection
from langchain_milvus import BM25BuiltInFunction, Milvus
from langchain_openai import OpenAIEmbeddings
from langchain_core.documents import Document
from langchain_classic.retrievers.contextual_compression import ContextualCompressionRetriever
from langchain_community.document_compressors import FlashrankRerank
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.config import settings
from app.schemas.milvus_schema import get_rag_collection_schema
from functools import lru_cache


class VectorStoreService:
    def __init__(self):
        self.embeddings = OpenAIEmbeddings(
            api_key=settings.OPEN_ROUTER_API,
            base_url=settings.OPEN_ROUTER_BASE_URL,
            model=settings.OPEN_ROUTER_EMBEDDING_MODEL)

        self.uri = settings.MILVUS_URI
        self.db_name = "default"
        self.collection_name = "docling_rag_collection"
        self.milvus_token = settings.MILVUS_TOKEN

    def ensure_vectoredb_exists(self):
        """ 
        Check whether the vectordb exisits if not,
        create the db and activate it
        """

        print(f"🔌 Connecting to Milvus at {self.uri}...")
        try:
            # Connect to default to manage DBs
            connections.connect(uri=self.uri, token=self.milvus_token)
            
            db.using_database(self.db_name)

            print(f"✅ Vector Store ready. Using DB: {self.db_name}")
            connections.disconnect("default")
                
        except Exception as e:
            print(f"⚠️ Vector Store Setup Warning: {e}")

    def _get_milvus_instance(self):
        connections.connect(uri=self.uri, token=self.milvus_token, db_name=self.db_name)
        search_params = [{ 
            # Dense
            "params": {"ef": 64}
        },
        { #Sparse
            "params": {"drop_rate_search": 0.2}
        }]
        db.using_database(self.db_name)
        return Milvus(
            connection_args={"uri": self.uri, "db_name": self.db_name, "token":self.milvus_token},
            embedding_function= self.embeddings,
            collection_name=self.collection_name,
            builtin_function=BM25BuiltInFunction(),
            vector_field=["dense", "sparse"],
            search_params= search_params,
            auto_id= True
        )

    def _split_markdown_table(self, doc: Document, chunk_size: int = 1000) -> list[Document]:
        """
        Splits a long Markdown table but PRESERVES the header row for every chunk.
        """
        text = doc.page_content
        lines = text.strip().split('\n')
        
        # 1. Identify Headers (Simple Markdown Heuristic)
        if len(lines) < 3 or "|" not in lines[0]:
            # Not a valid table, return as is (or use standard splitter)
            return [doc]
            
        header_block = lines[:2] # Keep first two lines (Headers + Separator)
        data_rows = lines[2:]
        
        header_len = sum(len(line) for line in header_block) + 2 # +2 for newlines
        
        chunks = []
        current_chunk_rows = []
        current_len = header_len
        
        for row in data_rows:
            row_len = len(row) + 1 # +1 for newline
            
            # If adding this row exceeds chunk size, save current chunk and start new
            if current_len + row_len > chunk_size and current_chunk_rows:
                # Join header + current rows
                chunk_text = "\n".join(header_block + current_chunk_rows)
                
                # Create new doc with same metadata
                new_doc = Document(page_content=chunk_text, metadata=doc.metadata.copy())
                # Add a flag so we know this is a partial table
                new_doc.metadata["split_part"] = "table_chunk"
                chunks.append(new_doc)
                
                # Reset
                current_chunk_rows = []
                current_len = header_len
            
            current_chunk_rows.append(row)
            current_len += row_len
            
        # Add the final remaining rows
        if current_chunk_rows:
            chunk_text = "\n".join(header_block + current_chunk_rows)
            new_doc = Document(page_content=chunk_text, metadata=doc.metadata.copy())
            chunks.append(new_doc)
            
        return chunks
    
    def add_chunks(self, chunks: list[dict]):
        """
        Add chunks to the collections, if it doesnt exist create new collection
        """
        final_chunks = []
        print(f"💾 Received {len(chunks)} chunks for optimizing")
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=5000, chunk_overlap=500, length_function=len
        )

        for doc in chunks:
            # Check if this is a Table (Docling usually tags it, or we check content)
            is_table = (
                doc.metadata.get("type") == "table" or 
                doc.metadata.get("label") == "table" or
                (doc.page_content.strip().startswith("|") and "---" in doc.page_content)
            )
            
            if is_table:
                table_chunks = self._split_markdown_table(doc, chunk_size=1200)
                final_chunks.extend(table_chunks)
            else:
                content_len = len(doc.page_content)
                
                if content_len > 1200:
                    # Case A: Too Big -> Split
                    split_docs = text_splitter.split_documents([doc])
                    final_chunks.extend(split_docs)
                
                elif content_len < 50:
                    # Case B: Too Small -> Merge with Previous
                    if final_chunks and final_chunks[-1].metadata.get("type") != "table":
                        # Append this small text to the end of the previous chunk
                        final_chunks[-1].page_content += f"\n\n{doc.page_content}"
                    else:
                        final_chunks.append(doc)
                
                else:
                    final_chunks.append(doc)

        print(f"💾 Indexing {len(final_chunks)} optimized chunks to Milvus...")


        #Try appending to existing collection
        try:
            
            vector_db = self._get_milvus_instance()
            vector_db.add_documents(final_chunks)

        #If not create new collection
        except Exception as e:
            print(f"Creating new collection: {self.collection_name}")
            print(f"Error details: {e}")

            index_params =[
                # Dense index
                {
                    "metric_type": "COSINE",
                    "index_type": "HNSW",
                    "params": {"M": 16, "efConstruction": 500}
                },
                # Sparse index
                {
                    "index_type": "SPARSE_INVERTED_INDEX",
                    "metric_type": "BM25",
                    "params": {
                        "inverted_index_algo": "DAAT_MAXSCORE", #Algorithm used for building and querying the index
                        "bm25_k1": 1.2, #Controls the term frequency saturation
                        "bm25_b": 0.75 #Controls the extent to which document length is normalized.
                    }
                }
            ]

            Milvus.from_documents(
                connection_args={"uri": self.uri, "db_name": self.db_name, "token": self.milvus_token},
                documents=final_chunks,
                embedding=self.embeddings,
                builtin_function = BM25BuiltInFunction(),
                vector_field= ["dense", "sparse"],
                collection_name=self.collection_name,
                consistency_level="Strong",
                index_params=index_params,
                auto_id = True,
                enable_dynamic_field=True,
                drop_old=True,
            )
        print("✅ Indexing Complete.")

        """
        Add chunks to the collections, if it doesnt exist
        create new collection
        """


        print(f"💾 Indexing {len(chunks)} chunks to Milvus...")
        
        #Try appending to existing collection
        try:
            
            vector_db = self._get_milvus_instance()
            vector_db.add_documents(chunks)

        #If not create new collection
        except Exception as e:
            print(f"Creating new collection: {self.collection_name}")
            print(f"Error details: {e}")

            index_params =[
                # Dense index
                {
                    "metric_type": "COSINE",
                    "index_type": "HNSW",
                    "params": {"M": 16, "efConstruction": 500}
                },
                # Sparse index
                {
                    "index_type": "SPARSE_INVERTED_INDEX",
                    "metric_type": "BM25",
                    "params": {
                        "inverted_index_algo": "DAAT_MAXSCORE", #Algorithm used for building and querying the index
                        "bm25_k1": 1.2, #Controls the term frequency saturation
                        "bm25_b": 0.75 #Controls the extent to which document length is normalized.
                    }
                }
            ]

            Milvus.from_documents(
                connection_args={"uri": self.uri, "token":self.milvus_token, "db_name": self.db_name},
                documents=chunks,
                embedding=self.embeddings,
                builtin_function = BM25BuiltInFunction(),
                vector_field= ["dense", "sparse"],
                collection_name=self.collection_name,
                consistency_level="Strong",
                index_params=index_params,
                auto_id = True,
                enable_dynamic_field=True,
                drop_old=True,
            )
        print("✅ Indexing Complete.")

    def get_chunks_by_file_id(self, user_id: str, file_id: int, limit: int = 1000):
        """
        Retrieve all chunks for a specific file using file_id
        """
        try:
            print(f"🔍 Fetching chunks for file_id={file_id}, user_id={user_id}")
            
            # Connect to Milvus
            connections.connect(uri=self.uri, db_name=self.db_name, token=self.milvus_token)
            db.using_database(self.db_name)
            
            # Get collection
            collection = Collection(self.collection_name)
            collection.load()
            
            # Query with filter expression
            filter_expr = f'user_id == "{user_id}" && file_id == {file_id}'
            
            # ✅ Specify only scalar fields (exclude dense and sparse vectors)
            results = collection.query(
                expr=filter_expr,
                output_fields=["text", "doc_id", "source", "file_id", "filename", "ref", "user_id"],
                limit=limit
            )
            
            print(f"✅ Found {len(results)} chunks for file_id={file_id}")
            
            # Debug: Print first result
            if results:
                print(f"📄 First chunk keys: {results[0].keys()}")
                print(f"📄 First chunk sample: doc_id={results[0].get('doc_id')}, filename={results[0].get('filename')}")
            
            # Transform to Document format
            chunks = []
            for result in results:
                # Extract text
                page_content = result.get("text", "")
                
                # Build metadata dict (exclude text and pk)
                metadata = {
                    "doc_id": result.get("doc_id"),
                    "source": result.get("source"),
                    "file_id": result.get("file_id"),
                    "filename": result.get("filename"),
                    "ref": result.get("ref"),
                    "user_id": result.get("user_id"),
                    # Add other fields if they exist
                    "type": result.get("type"),  # For table chunks
                    "page": result.get("page"),  # For page numbers
                }
                
                # Remove None values
                metadata = {k: v for k, v in metadata.items() if v is not None}
                
                chunks.append(Document(
                    page_content=page_content,
                    metadata=metadata
                ))
            
            connections.disconnect("default")
            return chunks
            
        except Exception as e:
            print(f"❌ Error querying Milvus: {e}")
            import traceback
            traceback.print_exc()
            try:
                connections.disconnect("default")
            except:
                pass
            return []


    def get_retreiver(self, user_id:str):
        vectorstore = self._get_milvus_instance()
        retriever = vectorstore.as_retriever(
            search_type="similarity",
            search_kwargs={
                "k": 20,
                "ranker_type": "rrf",
                "expr": f"user_id == '{user_id}'",
                "ranker_params": {"k": 20}
            }
        )

        return retriever


@lru_cache()
def get_vector_store_service():
    return VectorStoreService()