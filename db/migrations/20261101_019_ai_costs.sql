-- Bảng giá và usage chi phí cho các model AI bên thứ ba.
-- Giá lưu theo USD / 1 triệu token. Mọi phép tính dùng cost_micro_usd (1 USD = 1e6).

CREATE TABLE IF NOT EXISTS ai_models (
    id BIGSERIAL PRIMARY KEY,
    model_key TEXT NOT NULL UNIQUE,
    provider TEXT NOT NULL,
    display_name TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('llm', 'embedding', 'rerank')),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS ai_price_versions (
    id BIGSERIAL PRIMARY KEY,
    model_id BIGINT NOT NULL REFERENCES ai_models(id) ON DELETE CASCADE,
    effective_from TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    effective_to TIMESTAMPTZ,
    currency TEXT NOT NULL DEFAULT 'USD',
    input_cache_hit_per_m NUMERIC(12, 6),
    input_cache_miss_per_m NUMERIC(12, 6),
    output_per_m NUMERIC(12, 6),
    embedding_per_m NUMERIC(12, 6),
    rerank_per_m NUMERIC(12, 6),
    peak_multiplier NUMERIC(8, 4) NOT NULL DEFAULT 1,
    peak_timezone TEXT NOT NULL DEFAULT 'Asia/Ho_Chi_Minh',
    peak_windows JSONB NOT NULL DEFAULT '[]'::jsonb,
    input_tiers JSONB NOT NULL DEFAULT '[]'::jsonb,
    note TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_ai_price_active
    ON ai_price_versions (model_id)
    WHERE effective_to IS NULL;

CREATE TABLE IF NOT EXISTS ai_usage_events (
    id BIGSERIAL PRIMARY KEY,
    trace_id TEXT NOT NULL DEFAULT '',
    stage TEXT NOT NULL,
    model_key TEXT NOT NULL,
    input_tokens BIGINT NOT NULL DEFAULT 0,
    cached_tokens BIGINT NOT NULL DEFAULT 0,
    output_tokens BIGINT NOT NULL DEFAULT 0,
    embedding_tokens BIGINT NOT NULL DEFAULT 0,
    rerank_tokens BIGINT NOT NULL DEFAULT 0,
    is_peak BOOLEAN NOT NULL DEFAULT FALSE,
    input_tier TEXT NOT NULL DEFAULT '',
    price_version_id BIGINT REFERENCES ai_price_versions(id),
    cost_micro_usd BIGINT NOT NULL DEFAULT 0,
    success BOOLEAN NOT NULL DEFAULT TRUE,
    error TEXT NOT NULL DEFAULT '',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ai_usage_occurred
    ON ai_usage_events (occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_ai_usage_model
    ON ai_usage_events (model_key, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_ai_usage_trace
    ON ai_usage_events (trace_id);

INSERT INTO ai_models (model_key, provider, display_name, kind)
VALUES
    ('deepseek-v4.1-flash', 'deepseek', 'DeepSeek V4.1 Flash', 'llm'),
    ('qwen3.7-flash', 'qwen', 'Qwen3.7 Flash', 'llm'),
    ('qwen3.7-text-embedding', 'qwen', 'Qwen3.7 Text Embedding', 'embedding'),
    ('qwen3-rerank', 'qwen', 'Qwen3 Rerank', 'rerank')
ON CONFLICT (model_key) DO NOTHING;

-- DeepSeek: giá off-peak; peak multiplier 2. Peak 07:30-23:30 Asia/Ho_Chi_Minh.
INSERT INTO ai_price_versions (
    model_id, effective_from, input_cache_hit_per_m, input_cache_miss_per_m,
    output_per_m, peak_multiplier, peak_timezone, peak_windows, note
)
SELECT id, NOW(), 0.003, 0.15, 0.60, 2,
       'Asia/Ho_Chi_Minh',
       '[{"start":"07:30","end":"23:30"}]'::jsonb,
       'DeepSeek V4.1 Flash: off-peak; peak x2'
FROM ai_models
WHERE model_key = 'deepseek-v4.1-flash'
  AND NOT EXISTS (
      SELECT 1 FROM ai_price_versions p
      WHERE p.model_id = ai_models.id AND p.effective_to IS NULL
  );

-- Qwen3.7 Flash: tier theo input; giá khu vực Singapore.
INSERT INTO ai_price_versions (
    model_id, effective_from, input_tiers, note
)
SELECT id, NOW(),
       '[
          {"max_input_tokens":32000,"input_per_m":0.03,"output_per_m":0.13},
          {"max_input_tokens":256000,"input_per_m":0.10,"output_per_m":0.40},
          {"max_input_tokens":1000000,"input_per_m":0.20,"output_per_m":0.80}
        ]'::jsonb,
       'Qwen3.7 Flash: tier theo độ dài input (Singapore)'
FROM ai_models
WHERE model_key = 'qwen3.7-flash'
  AND NOT EXISTS (
      SELECT 1 FROM ai_price_versions p
      WHERE p.model_id = ai_models.id AND p.effective_to IS NULL
  );

INSERT INTO ai_price_versions (model_id, effective_from, embedding_per_m, note)
SELECT id, NOW(), 0.07, 'Qwen3.7 Text Embedding'
FROM ai_models
WHERE model_key = 'qwen3.7-text-embedding'
  AND NOT EXISTS (
      SELECT 1 FROM ai_price_versions p
      WHERE p.model_id = ai_models.id AND p.effective_to IS NULL
  );

INSERT INTO ai_price_versions (model_id, effective_from, rerank_per_m, note)
SELECT id, NOW(), 0.10, 'Qwen3 Rerank'
FROM ai_models
WHERE model_key = 'qwen3-rerank'
  AND NOT EXISTS (
      SELECT 1 FROM ai_price_versions p
      WHERE p.model_id = ai_models.id AND p.effective_to IS NULL
  );
