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
* Nhóm 9 — ngưỡng RAG: ``RRF_K_CONSTANT``, ``RERANKER_*``, ...

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
    #: Bật redirect HTTP -> HTTPS khi ứng dụng nhận trực tiếp request.
    #: Khi chạy sau Cloudflare/Nginx, để ``False`` và redirect tại proxy.
    force_https: bool = False
    log_level: str = "INFO"
    api_v1_prefix: str = "/api/v1"
    #: Nguồn được phép gọi API từ trình duyệt, phân tách bằng dấu phẩy.
    #:
    #: Mặc định gồm **cả** `localhost` và `127.0.0.1`: hai cái này là hai origin khác nhau với
    #: trình duyệt, và thiếu một cái là giao diện dev bị chặn ngay ở CORS dù máy chủ chạy tốt.
    cors_origins: str = (
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173,http://127.0.0.1:4173"
    )
    #: Host được phép gửi request. Bắt buộc đặt ở production.
    allowed_hosts: str = ""
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
    refresh_token_expire_days: int = 30
    # Số lần đăng nhập sai liên tiếp trước khi khóa tài khoản tạm thời.
    max_failed_attempts: int = 5
    # Thời gian khóa sau khi vượt ngưỡng trên (phút).
    lockout_minutes: int = 15

    # ── 1b. RATE LIMIT / PROXY ──────────────────────────────────────────────
    #: Redis dùng cho rate limit. Để trống → fallback in-memory (1 process).
    redis_url: str = ""
    redis_password: str = ""
    postgres_admin_password: str = ""
    cloudflare_tunnel_token: str = ""
    #: IP/CIDR của reverse proxy tin cậy. Chỉ các IP này mới được đọc
    #: X-Forwarded-For/CF-Connecting-IP. Mặc định tin localhost (Nginx).
    trusted_proxy_ips: str = "127.0.0.1,::1"
    login_rate_limit_per_min: int = 10
    register_rate_limit_per_min: int = 5
    refresh_rate_limit_per_min: int = 30
    chat_rate_limit_per_min: int = 10
    admin_llm_rate_limit_per_min: int = 5

    # ── 1c. SHORT-TERM MEMORY ───────────────────────────────────────────────
    # Công tắc rollback: tắt là bỏ qua toàn bộ memory, giữ hành vi cũ.
    memory_enabled: bool = True
    # Phiên khách: cookie token, TTL trượt và dọn nền.
    guest_session_ttl_seconds: int = 600
    guest_cleanup_interval_seconds: int = 60
    guest_cookie_name: str = "dsh_guest_token"
    guest_cookie_secure: bool = False
    # 3 cặp Q/A gần nhất = 6 message (user + assistant).
    memory_recent_messages: int = 6
    # Đủ 10 cặp chưa tóm tắt thì bắt đầu tóm tắt.
    memory_summary_trigger_pairs: int = 10
    # Giữ nguyên 2 cặp gần nhất; 8 cặp cũ còn lại được tóm tắt.
    memory_summary_keep_pairs: int = 2
    # Giới hạn tổng context memory và từng phần.
    memory_max_chars: int = 7_000
    memory_message_max_chars: int = 1_200
    memory_summary_max_chars: int = 1_200

    # ── 1d. MEMORY REWRITE ──────────────────────────────────────────────────
    # Rewrite tách biệt trước parser/grounding; tắt để rollback.
    memory_rewrite_enabled: bool = True
    memory_rewrite_confidence_min: float = 0.70
    memory_rewrite_max_chars: int = 600
    memory_rewrite_timeout_s: float = 5.0
    # Tối đa 2 lần GỌI, nhưng lần 2 chỉ khi lần 1 lỗi tạm thời.
    memory_rewrite_max_attempts: int = 2
    memory_rewrite_retry_delay_s: float = 2.5
    memory_summary_timeout_s: float = 20.0
    memory_summary_retry_delay_s: float = 2.5

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
    # Số tài liệu gửi rerank khi bật **rerank đầy đủ**. Mặc định tính năng này TẮT
    # (đo được: rerank đầy đủ làm giảm độ chính xác mục 7/7 → 4/7), nên biến này chỉ
    # có tác dụng khi ``use_rerank=True``.
    reranker_top_n: int = 15
    # **DÀNH CHO GIAI ĐOẠN 13 — hiện KHÔNG được đọc ở đâu.**
    # Số chunk cuối cùng đưa vào context của câu trả lời. Khác ``top_k`` của trang kiểm
    # thử (người dùng tự chọn để thí nghiệm): đây sẽ là con số cố định của đường chạy
    # thật, gom trong ``retrieval.py``.
    reranker_final_k: int = 5
    # Ngưỡng **CỔNG VÀO** (không phải ngưỡng lọc danh sách rerank).
    # Cách dùng: chấm **một** tài liệu (candidate đầu của RRF) rồi so với ngưỡng này;
    # dưới ngưỡng thì trả context rỗng thay vì đưa ngữ liệu ngoài phạm vi cho LLM.
    # Đo trên 31 câu: trong phạm vi 0,63–0,95 · ngoài phạm vi 0,45–0,54 → 0,60 tách
    # hoàn toàn. Cosine **không** làm được việc này (dải điểm chồng nhau: hợp lệ thấp
    # nhất 0,5250 < rác cao nhất 0,5837).
    # Lưu ý: câu hỏi **dài, nhiều ý** cho điểm thấp hơn — một câu hợp lệ hai phần chỉ đạt
    # 0,6219. Vì vậy cổng được **bỏ qua** khi đã định danh được thủ tục; xem
    # ``backend/app/rag/hybrid.py``.
    reranker_gate_min_score: float = 0.60
    #: Khoảng cách tối thiểu giữa top-1/top-2 khi rerank tên thủ tục đang mơ hồ.
    reranker_procedure_margin: float = 0.02
    #: Điểm tối thiểu của rerank tên thủ tục; dưới ngưỡng thì hỏi lại thay vì đoán.
    reranker_procedure_min_score: float = 0.62
    # Ngưỡng **LỌC TỪNG CHUNK** trong danh sách rerank — khác hẳn ngưỡng cổng ở trên.
    # Để **0,0** (không lọc). Đây là giá trị đúng gần như luôn luôn: khi lọc, chunk
    # đúng nhưng điểm thấp hơn ngưỡng sẽ bị **loại âm thầm** — đo được một câu hỏi hai
    # ý có chunk hồ sơ đúng chỉ đạt 0,5966, tức dưới ngưỡng cổng 0,60. Nếu ai đó truyền
    # 0,60 vào đây, hệ thống mất dữ liệu mà không có log nào.
    chunk_filter_min_score: float = 0.0

    # ── 3. DEEPSEEK — SINH CÂU TRẢ LỜI ───────────────────────────────────────
    deepseek_base_url: str = ""
    deepseek_api_key: str = ""
    synthesizer_model_name: str = ""
    synthesizer_temperature: float = 0.3
    synthesizer_max_tokens: int = 4096

    # ── 5. POSTGRESQL (SSOT) ─────────────────────────────────────────────────
    database_host: str = "localhost"
    database_port: int = 5432
    database_db: str = ""
    database_user: str = ""
    database_password: str = ""
    # Chuỗi gộp, tiện cho SQLAlchemy. Nếu có biến này thì nó thắng các biến rời.
    database_url: str = ""

    # ── 5b. OBJECT STORAGE (SeaweedFS/S3/R2) ────────────────────────────────
    # Lưu file mẫu (Word/PDF) bên ngoài PostgreSQL. Local dùng SeaweedFS;
    # production đổi endpoint/bucket sang S3/R2 mà không sửa code.
    s3_endpoint: str = "http://localhost:8333"
    s3_bucket: str = "procedure-documents"
    s3_access_key: str = "test"
    s3_secret_key: str = "test"
    s3_region: str = "ap-southeast-1"

    # ── 6. NEO4J ─────────────────────────────────────────────────────────────
    neo4j_url: str = "neo4j://127.0.0.1:7687"
    neo4j_username: str = "neo4j"
    neo4j_password: str = ""
    neo4j_database: str = "neo4j"
    # Mọi nút trong đồ thị đều có ``run_id`` để phân biệt bộ dữ liệu (``test`` = 49
    # thủ tục · bộ đầy đủ = 1.909). Truy vấn **bắt buộc** lọc theo giá trị này, nếu
    # không kết quả sẽ trộn hai bộ và đếm trùng. Đổi sang tên run của bộ đầy đủ khi
    # chuyển dữ liệu — không cần sửa code.
    neo4j_run_id: str = "test"
    #: Timeout một truy vấn Cypher (giây). Chặn truy vấn treo làm nghẽn request.
    neo4j_timeout: float = 3.0

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
    rrf_k_constant: int = 60
    # Số candidate **mỗi nhánh** (BM25 và vector) lấy về trước khi trộn RRF.
    # Đây là thông số quyết định **recall**: câu khó bị bỏ sót thì tăng biến này.
    # Để 30 vì RRF cần đủ nguyên liệu trộn mà không làm rerank (nếu bật) chạm giới hạn
    # 500 item của API. Đổi giá trị cần **khởi động lại backend** (settings đọc lúc import).
    hybrid_branch_k: int = 30
    # Số đoạn **đưa vào ngữ cảnh trả lời** (khác ``hybrid_branch_k`` là số đoạn truy xuất).
    #
    # Truy xuất 30 đoạn để chọn đúng, nhưng chỉ đưa 6 đoạn vào ngữ cảnh: mỗi đoạn ~600 ký tự
    # nên 30 đoạn là ~18 000 ký tự — vượt xa nhu cầu trả lời một câu, và làm loãng phần quan
    # trọng. Đo được: nhánh lai từng trả 51–56 mục vào ngữ cảnh cho một câu hỏi.
    hybrid_context_k: int = 10
    # Trọng số hai nhánh trong RRF. **KHÔNG để bằng nhau**: đo trên 30 câu, RRF
    # 50/50 chỉ đạt 5/7 mục đúng (kém hơn vector đơn thuần 7/7), vì BM25 cho mọi
    # chunk của cùng một thủ tục cùng điểm nên đẩy sai mục lên ngang mục đúng.
    # 0,2/0,8 là mức keyword cao nhất còn giữ được 7/7. Xem
    # ``backend/app/rag/hybrid.py::reciprocal_rank_fusion``.
    rrf_keyword_weight: float = 0.2
    rrf_vector_weight: float = 0.8
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
