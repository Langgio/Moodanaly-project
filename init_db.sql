-- 互動紀錄表：儲存 Hume AI 辨識結果
CREATE TABLE interactions (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(50) NOT NULL,
    family_id INTEGER NOT NULL,
    emotion_label VARCHAR(50),
    emotion_score FLOAT,
    confidence FLOAT,
    is_uncertain BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 建立索引以加速需求 4 的最近情緒查詢
CREATE INDEX idx_interactions_user_created ON interactions (user_id, created_at DESC);

-- 照護日誌表
CREATE TABLE care_logs (
    id SERIAL PRIMARY KEY,
    elder_id VARCHAR(50) NOT NULL,
    log_date DATE NOT NULL,
    summary TEXT,
    emotion_metrics JSONB, -- 儲存當日情緒分布
    log_type VARCHAR(20) DEFAULT 'DAILY',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT idx_care_logs_elder_date_type UNIQUE (elder_id, log_date, log_type)
);