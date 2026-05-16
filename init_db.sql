CREATE TABLE emotion_logs (
    id SERIAL PRIMARY KEY,
    test_name VARCHAR(255),
    detected_emotions JSONB, -- 儲存情緒字典
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);