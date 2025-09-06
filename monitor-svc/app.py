import os
import json
import time
import logging
import threading
import requests
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
from kafka import KafkaConsumer
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)

# Configuración de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuración
KAFKA_BOOTSTRAP_SERVERS = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092')
POSTGRES_URL = os.getenv('POSTGRES_URL', 'postgresql://postgres:postgres@localhost:5432/experimento')
SERVICE_NAME = os.getenv('SERVICE_NAME', 'monitor-svc')

# Configuración de monitoreo
HEALTH_CHECK_INTERVAL = 0.2  # 200ms
HEALTH_CHECK_TIMEOUT = 1.0   # 1 segundo
CONSECUTIVE_FAILURES_THRESHOLD = 3
RECOVERY_THRESHOLD = 5

# URLs de los servicios a monitorear
INVENTORY_SERVICES = [
    {'name': 'inventory-svc-1', 'url': 'http://inventory-svc-1:5000/health'},
    {'name': 'inventory-svc-2', 'url': 'http://inventory-svc-2:5000/health'},
    {'name': 'inventory-svc-3', 'url': 'http://inventory-svc-3:5000/health'}
]

# Estado de monitoreo
monitoring_state = {
    'inventory-svc-1': {'status': 'ON', 'consecutive_failures': 0, 'consecutive_successes': 0, 'last_check': None},
    'inventory-svc-2': {'status': 'ON', 'consecutive_failures': 0, 'consecutive_successes': 0, 'last_check': None},
    'inventory-svc-3': {'status': 'ON', 'consecutive_failures': 0, 'consecutive_successes': 0, 'last_check': None}
}

# Kafka Consumer
consumer = None

def get_kafka_consumer():
    global consumer
    if consumer is None:
        consumer = KafkaConsumer(
            'error-queue',
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            value_deserializer=lambda m: json.loads(m.decode('utf-8')),
            group_id='monitor-group',
            auto_offset_reset='latest',
            enable_auto_commit=True
        )
    return consumer

def get_db_connection():
    return psycopg2.connect(POSTGRES_URL)

def log_request_metrics(endpoint, method, status_code, latency_ms):
    """Registra métricas de request en la base de datos"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO request_metrics (service_name, endpoint, method, status_code, latency_ms) VALUES (%s, %s, %s, %s, %s)",
            (SERVICE_NAME, endpoint, method, status_code, latency_ms)
        )
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        logger.error(f"Error logging metrics: {e}")

def update_instance_status(service_name, instance_id, status, failure_type=None):
    """Actualiza el estado de una instancia en la base de datos"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Actualizar o insertar estado
        cursor.execute(
            """
            INSERT INTO instance_status (service_name, instance_id, status, last_health_check, updated_at)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (service_name, instance_id)
            DO UPDATE SET status = %s, last_health_check = %s, updated_at = %s
            """,
            (service_name, instance_id, status, datetime.utcnow(), datetime.utcnow(),
             status, datetime.utcnow(), datetime.utcnow())
        )
        
        # Si hay cambio de estado, registrar en auditoría
        if status == 'OFF' and failure_type:
            cursor.execute(
                "INSERT INTO failure_audit (service_name, instance_id, failure_type, detected_at) VALUES (%s, %s, %s, %s)",
                (service_name, instance_id, failure_type, datetime.utcnow())
            )
        
        conn.commit()
        cursor.close()
        conn.close()
        
        logger.info(f"Updated {service_name}-{instance_id} status to {status}")
        
    except Exception as e:
        logger.error(f"Error updating instance status: {e}")

def perform_health_check(service_info):
    """Realiza health check a un servicio"""
    service_name = service_info['name']
    url = service_info['url']
    
    try:
        start_time = time.time()
        response = requests.get(url, timeout=HEALTH_CHECK_TIMEOUT)
        latency_ms = int((time.time() - start_time) * 1000)
        
        if response.status_code == 200:
            data = response.json()
            if data.get('status') == 'UP':
                return True, latency_ms, None
            else:
                return False, latency_ms, f"Service reported status: {data.get('status')}"
        else:
            return False, latency_ms, f"HTTP {response.status_code}"
            
    except requests.exceptions.Timeout:
        return False, int(HEALTH_CHECK_TIMEOUT * 1000), "Timeout"
    except requests.exceptions.ConnectionError:
        return False, 0, "Connection error"
    except Exception as e:
        return False, 0, str(e)

def health_check_worker():
    """Worker que realiza health checks periódicos"""
    logger.info("Starting health check worker")
    
    while True:
        try:
            for service_info in INVENTORY_SERVICES:
                service_name = service_info['name']
                instance_id = service_name.split('-')[-1]  # Extraer ID de instancia
                
                # Realizar health check
                is_healthy, latency_ms, error_msg = perform_health_check(service_info)
                
                # Actualizar estado local
                current_state = monitoring_state[service_name]
                current_state['last_check'] = datetime.utcnow()
                
                if is_healthy:
                    current_state['consecutive_failures'] = 0
                    current_state['consecutive_successes'] += 1
                    
                    # Si estaba OFF y tiene suficientes éxitos consecutivos, volver a ON
                    if (current_state['status'] == 'OFF' and 
                        current_state['consecutive_successes'] >= RECOVERY_THRESHOLD):
                        current_state['status'] = 'ON'
                        update_instance_status('inventory-svc', instance_id, 'ON')
                        logger.info(f"Service {service_name} recovered and marked as ON")
                    
                else:
                    current_state['consecutive_successes'] = 0
                    current_state['consecutive_failures'] += 1
                    
                    # Si tiene suficientes fallos consecutivos, marcar como OFF
                    if (current_state['status'] == 'ON' and 
                        current_state['consecutive_failures'] >= CONSECUTIVE_FAILURES_THRESHOLD):
                        current_state['status'] = 'OFF'
                        update_instance_status('inventory-svc', instance_id, 'OFF', 'health_check_failure')
                        logger.warning(f"Service {service_name} marked as OFF due to consecutive failures: {error_msg}")
                
                # Log del health check
                logger.debug(f"Health check {service_name}: {'OK' if is_healthy else 'FAIL'} ({latency_ms}ms) - {error_msg or 'OK'}")
            
            time.sleep(HEALTH_CHECK_INTERVAL)
            
        except Exception as e:
            logger.error(f"Error in health check worker: {e}")
            time.sleep(HEALTH_CHECK_INTERVAL)

def error_queue_consumer():
    """Consumer que procesa errores de la cola de Kafka"""
    try:
        kafka_consumer = get_kafka_consumer()
        logger.info("Starting error queue consumer")
        
        for message in kafka_consumer:
            try:
                error_data = message.value
                logger.info(f"Processing error from queue: {error_data}")
                
                # Extraer información del error
                service_name = error_data.get('service', 'unknown')
                instance_id = error_data.get('instance_id', 'unknown')
                error_type = error_data.get('error_type', 'unknown')
                
                # Si es un error de inventory-svc, marcar como OFF
                if 'inventory-svc' in service_name:
                    instance_id = service_name.split('-')[-1] if '-' in service_name else '1'
                    update_instance_status('inventory-svc', instance_id, 'OFF', f'kafka_error_{error_type}')
                    
                    # Actualizar estado local
                    if service_name in monitoring_state:
                        monitoring_state[service_name]['status'] = 'OFF'
                        monitoring_state[service_name]['consecutive_failures'] = CONSECUTIVE_FAILURES_THRESHOLD
                    
                    logger.warning(f"Marked {service_name} as OFF due to error: {error_data}")
                
            except Exception as e:
                logger.error(f"Error processing error message: {e}")
                
    except Exception as e:
        logger.error(f"Error in error queue consumer: {e}")

@app.before_request
def before_request():
    request.start_time = time.time()

@app.after_request
def after_request(response):
    if hasattr(request, 'start_time'):
        latency_ms = int((time.time() - request.start_time) * 1000)
        log_request_metrics(
            request.endpoint,
            request.method,
            response.status_code,
            latency_ms
        )
    return response

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'UP',
        'service': SERVICE_NAME,
        'timestamp': datetime.utcnow().isoformat()
    })

@app.route('/status', methods=['GET'])
def get_status():
    """Obtiene el estado actual de todos los servicios monitoreados"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute(
            "SELECT * FROM instance_status ORDER BY service_name, instance_id"
        )
        instances = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'instances': [dict(instance) for instance in instances],
            'monitoring_state': monitoring_state,
            'timestamp': datetime.utcnow().isoformat()
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting status: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/status/<service_name>/<instance_id>', methods=['GET'])
def get_instance_status(service_name, instance_id):
    """Obtiene el estado de una instancia específica"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute(
            "SELECT * FROM instance_status WHERE service_name = %s AND instance_id = %s",
            (service_name, instance_id)
        )
        instance = cursor.fetchone()
        
        cursor.close()
        conn.close()
        
        if not instance:
            return jsonify({'error': 'Instance not found'}), 404
        
        return jsonify(dict(instance)), 200
        
    except Exception as e:
        logger.error(f"Error getting instance status: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/failures', methods=['GET'])
def get_failures():
    """Obtiene el historial de fallas"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute(
            "SELECT * FROM failure_audit ORDER BY detected_at DESC LIMIT 100"
        )
        failures = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'failures': [dict(failure) for failure in failures],
            'timestamp': datetime.utcnow().isoformat()
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting failures: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/metrics', methods=['GET'])
def get_metrics():
    """Obtiene métricas de los últimos minutos"""
    try:
        minutes = int(request.args.get('minutes', 5))
        since = datetime.utcnow() - timedelta(minutes=minutes)
        
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute(
            """
            SELECT service_name, endpoint, method, status_code, 
                   AVG(latency_ms) as avg_latency, 
                   COUNT(*) as request_count,
                   MAX(latency_ms) as max_latency,
                   MIN(latency_ms) as min_latency
            FROM request_metrics 
            WHERE timestamp >= %s 
            GROUP BY service_name, endpoint, method, status_code
            ORDER BY service_name, endpoint
            """,
            (since,)
        )
        metrics = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'metrics': [dict(metric) for metric in metrics],
            'period_minutes': minutes,
            'since': since.isoformat(),
            'timestamp': datetime.utcnow().isoformat()
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting metrics: {e}")
        return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    # Iniciar workers en threads separados
    health_check_thread = threading.Thread(target=health_check_worker, daemon=True)
    error_consumer_thread = threading.Thread(target=error_queue_consumer, daemon=True)
    
    health_check_thread.start()
    error_consumer_thread.start()
    
    app.run(host='0.0.0.0', port=5000, debug=True)