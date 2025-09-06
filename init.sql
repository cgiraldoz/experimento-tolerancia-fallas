-- Tabla para estado de instancias
CREATE TABLE IF NOT EXISTS instance_status (
    id SERIAL PRIMARY KEY,
    service_name VARCHAR(100) NOT NULL,
    instance_id VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'ON', -- ON, OFF
    last_health_check TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(service_name, instance_id)
);

-- Tabla para auditoría de fallas
CREATE TABLE IF NOT EXISTS failure_audit (
    id SERIAL PRIMARY KEY,
    service_name VARCHAR(100) NOT NULL,
    instance_id VARCHAR(50) NOT NULL,
    failure_type VARCHAR(50) NOT NULL, -- crash, latency, incorrect_response, intermittent
    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP,
    ttd_ms INTEGER, -- Time to detect
    ttr_ms INTEGER  -- Time to removal
);

-- Tabla para métricas de requests
CREATE TABLE IF NOT EXISTS request_metrics (
    id SERIAL PRIMARY KEY,
    service_name VARCHAR(100) NOT NULL,
    endpoint VARCHAR(200) NOT NULL,
    method VARCHAR(10) NOT NULL,
    status_code INTEGER NOT NULL,
    latency_ms INTEGER NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tabla para eventos de votación
CREATE TABLE IF NOT EXISTS voting_events (
    id SERIAL PRIMARY KEY,
    request_id VARCHAR(100) NOT NULL,
    service_name VARCHAR(100) NOT NULL,
    instance_id VARCHAR(50) NOT NULL,
    response_data JSONB,
    response_time_ms INTEGER,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tabla para órdenes
CREATE TABLE IF NOT EXISTS orders (
    id SERIAL PRIMARY KEY,
    order_id VARCHAR(100) UNIQUE NOT NULL,
    product_id VARCHAR(100) NOT NULL,
    quantity INTEGER NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING', -- PENDING, CONFIRMED, CANCELLED
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tabla para inventario
CREATE TABLE IF NOT EXISTS inventory (
    id SERIAL PRIMARY KEY,
    product_id VARCHAR(100) UNIQUE NOT NULL,
    available_quantity INTEGER NOT NULL DEFAULT 0,
    reserved_quantity INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Insertar datos iniciales de inventario
INSERT INTO inventory (product_id, available_quantity) VALUES 
    ('PROD-001', 1000),
    ('PROD-002', 500),
    ('PROD-003', 750)
ON CONFLICT (product_id) DO NOTHING;

-- Insertar estado inicial de instancias
INSERT INTO instance_status (service_name, instance_id, status) VALUES 
    ('inventory-svc', '1', 'ON'),
    ('inventory-svc', '2', 'ON'),
    ('inventory-svc', '3', 'ON')
ON CONFLICT (service_name, instance_id) DO NOTHING;

-- Índices para optimizar consultas
CREATE INDEX IF NOT EXISTS idx_request_metrics_timestamp ON request_metrics(timestamp);
CREATE INDEX IF NOT EXISTS idx_request_metrics_service ON request_metrics(service_name);
CREATE INDEX IF NOT EXISTS idx_voting_events_request_id ON voting_events(request_id);
CREATE INDEX IF NOT EXISTS idx_failure_audit_detected_at ON failure_audit(detected_at);
CREATE INDEX IF NOT EXISTS idx_instance_status_service ON instance_status(service_name);