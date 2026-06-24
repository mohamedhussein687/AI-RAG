from functools import lru_cache
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = Field(default="development", alias="APP_ENV")
    production_mode: bool = Field(default=False, alias="PRODUCTION_MODE")
    release_sha: str = Field(default="dev", alias="RELEASE_SHA")

    ai_module_token: str = Field(default="change-me", alias="AI_MODULE_TOKEN")
    spring_gateway_base_url: str = Field(default="", alias="SPRING_GATEWAY_BASE_URL")
    spring_gateway_token: str = Field(default="", alias="SPRING_GATEWAY_TOKEN")

    chat_model: str = Field(default="Qwen/Qwen2.5-7B-Instruct-AWQ", alias="CHAT_MODEL")
    chat_model_revision: str = Field(default="pinned-by-deploy", alias="CHAT_MODEL_REVISION")
    llm_base_url: str = Field(default="http://vllm-chat:8000/v1", alias="LLM_BASE_URL")
    llm_api_key: str = Field(default="local-key", alias="LLM_API_KEY")
    llm_temperature: float = Field(default=0, alias="LLM_TEMPERATURE")

    embedding_model: str = Field(default="BAAI/bge-m3", alias="EMBEDDING_MODEL")
    embedding_model_revision: str = Field(default="pinned-by-deploy", alias="EMBEDDING_MODEL_REVISION")
    embedding_base_url: str = Field(default="http://embedding-service:80", alias="EMBEDDING_BASE_URL")
    embedding_dimension: int = Field(default=1024, alias="EMBEDDING_DIMENSION")

    reranker_model: str = Field(default="BAAI/bge-reranker-v2-m3", alias="RERANKER_MODEL")
    reranker_model_revision: str = Field(default="pinned-by-deploy", alias="RERANKER_MODEL_REVISION")
    reranker_base_url: str = Field(default="http://reranker-service:80", alias="RERANKER_BASE_URL")

    qdrant_url: str = Field(default="http://qdrant:6333", alias="QDRANT_URL")
    qdrant_collection: str = Field(default="construction_chunks", alias="QDRANT_COLLECTION")
    qdrant_business_collection: str = Field(default="business_knowledge", alias="QDRANT_BUSINESS_COLLECTION")
    qdrant_schema_collection: str = Field(default="semantic_catalog", alias="QDRANT_SCHEMA_COLLECTION")
    postgres_url: str = Field(default="postgresql+asyncpg://ai:ai@postgres:5432/ai_rag", alias="POSTGRES_URL")
    index_version: str = Field(default="v1", alias="INDEX_VERSION")

    max_tool_calls: int = Field(default=5, alias="MAX_TOOL_CALLS")
    max_tool_rounds: int = Field(default=3, alias="MAX_TOOL_ROUNDS")
    max_retrieved_chunks: int = Field(default=8, alias="MAX_RETRIEVED_CHUNKS")
    max_chunk_chars: int = Field(default=1600, alias="MAX_CHUNK_CHARS")
    max_total_context_chars: int = Field(default=9000, alias="MAX_TOTAL_CONTEXT_CHARS")
    default_locale: str = Field(default="ar", alias="DEFAULT_LOCALE")
    candidate_count: int = Field(default=50, alias="CANDIDATE_COUNT")
    embedding_batch_size: int = Field(default=16, alias="EMBEDDING_BATCH_SIZE")
    http_timeout_seconds: float = Field(default=30, alias="HTTP_TIMEOUT_SECONDS")
    retry_attempts: int = Field(default=3, alias="RETRY_ATTEMPTS")
    rag_sources_config: str = Field(default="config/rag_sources.yml", alias="RAG_SOURCES_CONFIG")
    ingestion_interval_seconds: int = Field(default=60, alias="INGESTION_INTERVAL_SECONDS")
    mysql_host: str = Field(default="", alias="MYSQL_HOST")
    mysql_port: int = Field(default=3306, alias="MYSQL_PORT")
    mysql_database: str = Field(default="", alias="MYSQL_DATABASE")
    mysql_username: str = Field(default="", validation_alias=AliasChoices("MYSQL_USER", "MYSQL_USERNAME"))
    mysql_password: str = Field(default="", alias="MYSQL_PASSWORD")
    mysql_connect_timeout_seconds: int = Field(default=10, alias="MYSQL_CONNECT_TIMEOUT_SECONDS")
    mysql_query_timeout_seconds: int = Field(default=15, alias="MYSQL_QUERY_TIMEOUT_SECONDS")
    mysql_max_rows: int = Field(default=200, alias="MYSQL_MAX_ROWS")
    schema_aliases_path: str = Field(default="../config/schema_aliases.yml", alias="SCHEMA_ALIASES_PATH")
    schema_source_name: str = Field(default="construction_mysql", alias="SCHEMA_SOURCE_NAME")
    dataset_output_path: str = Field(default="data/training/db_agent_sft.jsonl", alias="TRAINING_DATASET_PATH")
    training_output_dir: str = Field(default="outputs/db-agent-qwen-lora", alias="TRAINING_OUTPUT_DIR")
    training_base_model: str = Field(default="", alias="TRAINING_BASE_MODEL")
    llm_provider: str = Field(default="openai_compatible", alias="LLM_PROVIDER")
    llm_model_name: str = Field(default="", alias="LLM_MODEL_NAME")
    llm_fine_tuned: bool = Field(default=False, alias="LLM_FINE_TUNED")
    llm_max_tokens: int = Field(default=1200, alias="LLM_MAX_TOKENS")
    llm_adapter_path: str = Field(default="", alias="LLM_ADAPTER_PATH")
    llm_merged_model_path: str = Field(default="", alias="LLM_MERGED_MODEL_PATH")
    llm_adapter_serving_mode: str = Field(default="served_model", alias="LLM_ADAPTER_SERVING_MODE")
    llm_training_report_path: str = Field(default="", alias="LLM_TRAINING_REPORT_PATH")

    fake_llm: bool = Field(default=True, alias="FAKE_LLM")
    fake_embeddings: bool = Field(default=True, alias="FAKE_EMBEDDINGS")
    fake_reranker: bool = Field(default=True, alias="FAKE_RERANKER")

    def validate_production(self) -> None:
        if not self.production_mode:
            return
        errors = []
        if self.ai_module_token in {"", "change-me", "test-token"}:
            errors.append("AI_MODULE_TOKEN must be set to a non-default secret")
        if self.fake_llm:
            errors.append("FAKE_LLM must be false")
        if self.fake_embeddings:
            errors.append("FAKE_EMBEDDINGS must be false")
        if self.fake_reranker:
            errors.append("FAKE_RERANKER must be false")
        if self.llm_fine_tuned and not (self.llm_model_name or self.llm_adapter_path or self.llm_merged_model_path):
            errors.append("LLM_FINE_TUNED requires LLM_MODEL_NAME, LLM_ADAPTER_PATH, or LLM_MERGED_MODEL_PATH")
        if self.postgres_url.startswith("sqlite"):
            errors.append("POSTGRES_URL must use PostgreSQL")
        if self.qdrant_url.startswith(":memory:"):
            errors.append("QDRANT_URL must use a real Qdrant service")
        if errors:
            raise RuntimeError("Invalid production configuration: " + "; ".join(errors))


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.validate_production()
    return settings
