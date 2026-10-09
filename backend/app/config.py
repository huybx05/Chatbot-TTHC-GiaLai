"""Application settings loaded from environment variables and ``.env``.

**Nguồn chuẩn về tên biến là ``.env`` của dự án.** Không đổi tên biến ở đây mà
không cập nhật cả ``.env`` và ``.env.example`` — ba nơi phải khớp nhau.

Quy ước nhóm biến:

* Nhóm 1 — ứng dụng: ``APP_ENV``, ``DEBUG``, ``LOG_LEVEL``, ``API_V1_PREFIX``,
  ``SECRET_KEY``, ``DATA_ROOT``
* Nhóm 2 — Qwen (router, embedding, reranker): ``QWEN_*``, ``ROUTER_*``,
  ``EMBEDDING_*``, ``RERANKER_*``
* Nhóm 3 — DeepSeek (sinh câu trả lời): ``DEEPSEEK_*``, ``SYNTHESIZER_*``
* Nhóm 4 — LLM sinh FAQ offline: ``FAQ_LLM_*``
* Nhóm 5 — PostgreSQL: ``DATABASE_*``
* Nhóm 6 — Neo4j: ``NEO4J_*``
* Nhóm 7 — Elasticsearch: ``ELASTICSEARCH_*``, ``ELASTIC_*``
* Nhóm 8 — Qdrant: ``QDRANT_*``
* Nhóm 9 — ngưỡng RAG: ``FAQ_CACHE_THRESHOLD``, ``RRF_K_CONSTANT``, ...

Ghi chú về reranker: Qwen rerank **không** dùng được chế độ OpenAI-compatible
(``/compatible-mode/v1``) vì rerank không thuộc chuẩn OpenAI. Nó có endpoint
riêng, khai báo qua ``RERANKER_BASE_URL``.
"""

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration.

    Secrets are never hard-coded here; they come from the environment.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── 1. ỨNG DỤNG ──────────────────────────────────────────────────────────
    app_env: str = "development"
    debug: bool = False
    log_level: str = "INFO"
    api_v1_prefix: str = "/api/v1"
    secret_key: str = ""
    # ``data_root`` trỏ tới cây dữ liệu; dùng đường dẫn TƯƠNG ĐỐI để bản dump
    # chuyển được sang máy khác mà không phải sửa.
    data_root: str = "./data"

    # ── 1b. XÁC THỰC (bảo vệ endpoint /admin) ────────────────────────────────
    # `SECRET_KEY` ở trên là khóa ký JWT. **Bắt buộc** đổi khi lên production —
    # giá trị mặc định trong `.env` chỉ dùng cho máy phát triển.
    jwt_algorithm: str = "HS256"
    # Access token ngắn hạn: nó KHÔNG thu hồi được (JWT không trạng thái), nên
    # cửa sổ rủi ro chính là thời gian sống của nó. 30 phút là mức cân bằng giữa
    # an toàn và số lần phải làm mới.
    access_token_expire_minutes: int = 30
    # Refresh token dài hạn nhưng CÓ thu hồi được (bảng `sessions`).
    refresh_token_expire_days: int = 7
    # Số lần đăng nhập sai liên tiếp trước khi khóa tài khoản tạm thời.
    max_failed_attempts: int = 5
    # Thời gian khóa sau khi vượt ngưỡng trên (phút).
    lockout_minutes: int = 15

    # ── 2. QWEN — ROUTER, EMBEDDING, RERANKER ────────────────────────────────
    qwen_base_url: str = ""
    qwen_api_key: str = ""

    router_model_name: str = ""
    embedding_model_name: str = ""
    reranker_model_name: str = ""

    # Số chiều vector. PHẢI khớp đúng số chiều model nhúng trả về và khớp
    # collection Qdrant — sai số này thì mọi vector nạp vào đều lỗi.
    embedding_dim: int = 1024
    embedding_batch_size: int = 25
    embedding_max_length: int = 2048

    # Reranker có endpoint riêng, KHÔNG dùng chung ``qwen_base_url``
    # (``/compatible-mode/v1`` không hỗ trợ rerank).
    reranker_base_url: str = ""
    reranker_top_n: int = 15
    reranker_final_k: int = 5
    reranker_min_score: float = 0.35

    # ── 3. DEEPSEEK — SINH CÂU TRẢ LỜI ───────────────────────────────────────
    deepseek_base_url: str = ""
    deepseek_api_key: str = ""
    synthesizer_model_name: str = ""
    synthesizer_temperature: float = 0.2
    synthesizer_max_tokens: int = 2048

    # ── 4. FAQ LLM — SINH FAQ OFFLINE ─────────────────────────────────────────
    faq_llm_base_url: str = ""
    faq_llm_api_key: str = ""
    faq_llm_model: str = ""

    # ── 5. POSTGRESQL (SSOT) ─────────────────────────────────────────────────
    database_host: str = "localhost"
    database_port: int = 5432
    database_db: str = ""
    database_user: str = ""
    database_password: str = ""
    # Chuỗi gộp, tiện cho SQLAlchemy. Nếu có biến này thì nó thắng các biến rời.
    database_url: str = ""

    # ── 6. NEO4J ─────────────────────────────────────────────────────────────
    neo4j_url: str = "neo4j://127.0.0.1:7687"
    neo4j_username: str = "neo4j"
    neo4j_password: str = ""
    neo4j_database: str = "neo4j"

    # ── 7. ELASTICSEARCH ─────────────────────────────────────────────────────
    elasticsearch_host: str = "http://localhost:9200"
    elasticsearch_index: str = ""
    elastic_user: str = ""
    elastic_password: str = ""
    elastic_request_timeout: int = 15

    # ── 8. QDRANT ────────────────────────────────────────────────────────────
    qdrant_host: str = "http://localhost:6333"
    qdrant_collection_semantic: str = ""
    qdrant_collection_faq: str = ""
    qdrant_api_key: str = ""

    # ── 9. NGƯỠNG RAG ────────────────────────────────────────────────────────
    faq_cache_threshold: float = 0.90
    rrf_k_constant: int = 60
    router_confidence_threshold: float = 0.85
    max_retry_count: int = 2

    @field_validator("debug", mode="before")
    @classmethod
    def parse_debug(cls, value: object) -> object:
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"release", "prod", "production", "false", "0", "no", "off"}:
                return False
            if normalized in {"dev", "development", "true", "1", "yes", "on"}:
                return True
        return value


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings instance."""
    return Settings()


settings = get_settings()
