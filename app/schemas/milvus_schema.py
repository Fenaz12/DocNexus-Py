# app/models/milvus_schema.py
from pymilvus import FieldSchema, CollectionSchema, DataType

def get_rag_collection_schema(embedding_dim: int = 1024) -> CollectionSchema:
    """
    Defines the table structure for the RAG system.
    """
    print(f"🔨 Generating Schema with dim={embedding_dim}...")
    
    # 1. Primary Key
    pk = FieldSchema(
        name="pk", 
        dtype=DataType.VARCHAR, 
        is_primary=True, 
        auto_id=True, 
        max_length=100
    )
    
    # 2. Dense Vector (Embeddings)
    # The dimension must match your model (e.g., bge-m3 = 1024)
    dense = FieldSchema(
        name="dense", 
        dtype=DataType.FLOAT_VECTOR, 
        dim=embedding_dim
    )
    
    # 3. Sparse Vector (BM25 Keyword Search)
    sparse = FieldSchema(
        name="sparse", 
        dtype=DataType.SPARSE_FLOAT_VECTOR
    )
    
    # 4. Text Content (The actual chunk text)
    text = FieldSchema(
        name="text", 
        dtype=DataType.VARCHAR, 
        max_length=65535
    )
    
    # 5. User ID (For Multi-Tenancy/Security)
    user_id = FieldSchema(
        name="user_id", 
        dtype=DataType.VARCHAR, 
        max_length=100
    )

    # 6. Source Filename (Optional but useful metadata)
    filename = FieldSchema(
        name="filename", 
        dtype=DataType.VARCHAR, 
        max_length=255
    )

    schema = CollectionSchema(
        fields=[pk, dense, sparse, text, user_id, filename],
        description="RAG Collection with User ID filtering",
        enable_dynamic_field=True 
    )
    
    return schema