from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path
ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
class Settings(BaseSettings):

    #Ingestion Settings
    BASE_UPLOAD_DIR: Path = Path("data/uploads")
    DOCLING_DEVICE: str = "cuda"
    DOCLING_NUM_THREADS: int = 8

    #OpenRouter Settings
    OPEN_ROUTER_API: str
    OPEN_ROUTER_VLM_BASE_URL: str = "https://openrouter.ai/api/v1/chat/completions"
    OPEN_ROUTER_VLM_MODEL: str = "google/gemma-3-12b-it:free"

    OPEN_ROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    OPEN_ROUTER_EMBEDDING_MODEL: str = "openai/text-embedding-3-small"

    OPEN_ROUTER_CHAT_LLM: str = "openai/gpt-4o-mini"
    OPEN_ROUTER_GRADER_LLM: str = "openai/gpt-4o-mini"

    OLLAMA_BASE_URL: str = "http://localhost:11434/v1/chat/completions"
    OLLAMA_VLM_MODEL: str = "llama3.2-vision:latest"
    VLM_TIMEOUT: int = 240
    VLM_TEMPERATURE: float = 0.2
    VLM_PROMPT: str = "Describe this image in three sentences. Be concise and accurate."
    
    #Tokenizer Model Settings
    TOKEN_MODEL_ID: str = "BAAI/bge-m3"

    #Embedding model settings
    
    EMBED_MODEL_ID: str = "bge-m3:latest"


    #Milvus Vector Storage Settings
    MILVUS_HOST: str = "127.0.0.1"
    MILVUS_PORT: int = 19530
    MILVUS_URI: str
    MILVUS_TOKEN: str
    
    #Chat Model Settings
    OLLAMA_MODEL: str = "qwen3:8b"

    #Postgres
    DB_URI: str
    
    model_config = SettingsConfigDict(
            env_file=ENV_PATH, 
            env_file_encoding='utf-8',
            extra='ignore'
        )

settings = Settings()