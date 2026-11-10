-- Создаем таблицу для задач
CREATE TABLE IF NOT EXISTS tasks (
    id UUID PRIMARY KEY,
    original_filename VARCHAR(255) NOT NULL,
    file_type VARCHAR(50) NOT NULL, -- 'image' или 'video'
    status VARCHAR(50) NOT NULL DEFAULT 'uploaded', -- uploaded, processing, completed, failed
    action VARCHAR(50), -- действие (например, 'convert', 'resize')
    params JSONB, -- параметры действия (например, {"quality": 80})
    source_path VARCHAR(255) NOT NULL,
    result_path VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
