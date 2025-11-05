-- PostgreSQL 초기화 스크립트
-- 시스템 설정 및 모델 설정 저장용

-- 시스템 설정 테이블
CREATE TABLE IF NOT EXISTS system_config (
    config_key VARCHAR(255) PRIMARY KEY,
    config_value TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 모델 설정 테이블
CREATE TABLE IF NOT EXISTS model_config (
    model_name VARCHAR(255) PRIMARY KEY,
    model_type VARCHAR(100) NOT NULL,
    sequence_length INTEGER DEFAULT 30,
    forecast_horizon INTEGER DEFAULT 10,
    anomaly_threshold FLOAT DEFAULT 0.7,
    config_json JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 위성 설정 테이블
CREATE TABLE IF NOT EXISTS satellite_config (
    satellite_id VARCHAR(50) PRIMARY KEY,
    satellite_name VARCHAR(255),
    monitoring_enabled BOOLEAN DEFAULT true,
    config_json JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 서브시스템 설정 테이블
CREATE TABLE IF NOT EXISTS subsystem_config (
    subsystem_name VARCHAR(50) PRIMARY KEY,
    display_name VARCHAR(100),
    features JSONB,
    monitoring_enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 기본 데이터 삽입
INSERT INTO system_config (config_key, config_value, description) VALUES
    ('triton_server_url', 'triton-server:8001', 'Triton Inference Server URL'),
    ('victoria_metrics_url', 'http://victoria-metrics:8428', 'VictoriaMetrics URL'),
    ('kafka_bootstrap_servers', 'kafka:9092', 'Kafka Bootstrap Servers')
ON CONFLICT (config_key) DO NOTHING;

INSERT INTO model_config (model_name, model_type, sequence_length, forecast_horizon, anomaly_threshold) VALUES
    ('lstm_timeseries', 'LSTM', 30, 10, 0.7)
ON CONFLICT (model_name) DO NOTHING;

INSERT INTO satellite_config (satellite_id, satellite_name, monitoring_enabled) VALUES
    ('SAT-001', 'Satellite Alpha', true),
    ('SAT-002', 'Satellite Beta', true),
    ('SAT-003', 'Satellite Gamma', true)
ON CONFLICT (satellite_id) DO NOTHING;

INSERT INTO subsystem_config (subsystem_name, display_name, features, monitoring_enabled) VALUES
    ('eps', 'Electrical Power System', '["battery_voltage", "battery_soc", "battery_current"]'::jsonb, true),
    ('thermal', 'Thermal Control System', '["temp_battery", "temp_obc", "temp_comm"]'::jsonb, true),
    ('aocs', 'Attitude & Orbit Control', '["gyro_x", "gyro_y", "gyro_z"]'::jsonb, true),
    ('comm', 'Communication System', '["rssi", "data_backlog"]'::jsonb, true)
ON CONFLICT (subsystem_name) DO NOTHING;

-- 인덱스 생성
CREATE INDEX IF NOT EXISTS idx_satellite_config_enabled ON satellite_config(monitoring_enabled);
CREATE INDEX IF NOT EXISTS idx_subsystem_config_enabled ON subsystem_config(monitoring_enabled);
