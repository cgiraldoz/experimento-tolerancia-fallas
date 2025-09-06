import os
import json
import time
import random
import logging
import threading
from datetime import datetime
from flask import Flask, request, jsonify
from kafka import KafkaConsumer, KafkaProducer
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)

# Configuración de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuración
KAFKA_BOOTSTRAP_SERVERS = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092')
POSTGRES_URL = os.getenv('POSTGRES_URL', 'postgresql://postgres:postgres@localhost:5432/experimento')
SERVICE_NAME = os.getenv('SERVICE_NAME', 'inventory-svc')
INSTANCE_ID = os.getenv('INSTANCE_ID', '1')

# Variables para inyección de fallas
FAILURE_INJECTED = False
FAILURE_TYPE = None
FAILURE_PROBABILITY = 0.0
LATENCY_MS = 0
INCORRECT_PRODUCT = None

# Kafka Consumer y Producer
consumer = None
producer = None

def get_kafka_consumer():
    global consumer
    if consumer is None:
        consumer = KafkaConsumer(
            'order-events',
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            value_deserializer=lambda m: json.loads(m.decode('utf-8')),
            group_id=f'inventory-group-{INSTANCE_ID}',
            auto_offset_reset='latest',
            enable_auto_commit=True
        )
    return consumer

def get_kafka_producer():
    global producer
    if producer is None:
        producer = KafkaProducer(
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
            key_serializer=lambda k: k.encode('utf-8') if k else None
        )
    return producer

def get_db_connection():
    return psycopg2.connect(POSTGRES_URL)

def log_request_metrics(endpoint, method, status_code, latency_ms):
    """Registra métricas de request en la base de datos"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO request_metrics (service_name, endpoint, method, status_code, latency_ms) VALUES (%s, %s, %s, %s, %s)",
            (f"{SERVICE_NAME}-{INSTANCE_ID}", endpoint, method, status_code, latency_ms)
        )
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        logger.error(f"Error logging metrics: {e}")

def inject_failure():
    """Inyecta fallas según la configuración"""
    global FAILURE_INJECTED, FAILURE_TYPE, FAILURE_PROBABILITY, LATENCY_MS, INCORRECT_PRODUCT
    
    if not FAILURE_INJECTED:
        return
    
    if FAILURE_TYPE == 'crash':
        logger.error(f"CRASH INJECTED in {SERVICE_NAME}-{INSTANCE_ID}")
        os._exit(1)
    
    elif FAILURE_TYPE == 'latency' and LATENCY_MS > 0:
        sleep_time = random.uniform(LATENCY_MS * 0.8, LATENCY_MS * 1.2)
        logger.info(f"LATENCY INJECTED: sleeping {sleep_time}ms")
        time.sleep(sleep_time / 1000.0)
    
    elif FAILURE_TYPE == 'intermittent' and random.random() < FAILURE_PROBABILITY:
        logger.error(f"INTERMITTENT ERROR INJECTED in {SERVICE_NAME}-{INSTANCE_ID}")
        raise Exception("Intermittent error injected")
    
    elif FAILURE_TYPE == 'incorrect_response':
        # Esta falla se maneja en el endpoint de consulta
        pass

def process_order_event(message):
    """Procesa eventos de órdenes desde Kafka"""
    try:
        order_data = message.value
        order_id = order_data['order_id']
        action = order_data['action']
        
        logger.info(f"Processing order event: {order_id}, action: {action}")
        
        if action == 'reserve':
            product_id = order_data['product_id']
            quantity = order_data['quantity']
            
            # Inyectar falla si está configurada
            inject_failure()
            
            # Procesar reserva
            success = reserve_inventory(product_id, quantity, order_id)
            
            # Publicar resultado
            result_event = {
                'order_id': order_id,
                'product_id': product_id,
                'quantity': quantity,
                'action': 'reserve_result',
                'success': success,
                'instance_id': INSTANCE_ID,
                'timestamp': datetime.utcnow().isoformat()
            }
            
            kafka_producer = get_kafka_producer()
            kafka_producer.send('inventory-results', key=order_id, value=result_event)
            kafka_producer.flush()
            
        elif action == 'cancel':
            # Procesar cancelación
            success = cancel_reservation(order_id)
            
            result_event = {
                'order_id': order_id,
                'action': 'cancel_result',
                'success': success,
                'instance_id': INSTANCE_ID,
                'timestamp': datetime.utcnow().isoformat()
            }
            
            kafka_producer = get_kafka_producer()
            kafka_producer.send('inventory-results', key=order_id, value=result_event)
            kafka_producer.flush()
            
    except Exception as e:
        logger.error(f"Error processing order event: {e}")
        
        # Publicar error
        error_event = {
            'order_id': order_data.get('order_id', 'unknown'),
            'error': str(e),
            'instance_id': INSTANCE_ID,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        kafka_producer = get_kafka_producer()
        kafka_producer.send('error-queue', value=error_event)
        kafka_producer.flush()

def reserve_inventory(product_id, quantity, order_id):
    """Reserva inventario para una orden"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Verificar disponibilidad
        cursor.execute(
            "SELECT available_quantity FROM inventory WHERE product_id = %s",
            (product_id,)
        )
        result = cursor.fetchone()
        
        if not result:
            cursor.close()
            conn.close()
            return False
        
        available = result[0]
        
        if available < quantity:
            cursor.close()
            conn.close()
            logger.warning(f"Insufficient inventory for {product_id}: requested {quantity}, available {available}")
            return False
        
        # Realizar reserva
        cursor.execute(
            "UPDATE inventory SET available_quantity = available_quantity - %s, reserved_quantity = reserved_quantity + %s WHERE product_id = %s",
            (quantity, quantity, product_id)
        )
        
        if cursor.rowcount == 0:
            cursor.close()
            conn.close()
            return False
        
        conn.commit()
        cursor.close()
        conn.close()
        
        logger.info(f"Reserved {quantity} units of {product_id} for order {order_id}")
        return True
        
    except Exception as e:
        logger.error(f"Error reserving inventory: {e}")
        return False

def cancel_reservation(order_id):
    """Cancela una reserva de inventario"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Obtener detalles de la orden
        cursor.execute(
            "SELECT product_id, quantity FROM orders WHERE order_id = %s",
            (order_id,)
        )
        result = cursor.fetchone()
        
        if not result:
            cursor.close()
            conn.close()
            return False
        
        product_id, quantity = result
        
        # Liberar reserva
        cursor.execute(
            "UPDATE inventory SET available_quantity = available_quantity + %s, reserved_quantity = reserved_quantity - %s WHERE product_id = %s",
            (quantity, quantity, product_id)
        )
        
        conn.commit()
        cursor.close()
        conn.close()
        
        logger.info(f"Cancelled reservation for order {order_id}: {quantity} units of {product_id}")
        return True
        
    except Exception as e:
        logger.error(f"Error cancelling reservation: {e}")
        return False

def kafka_consumer_thread():
    """Thread para consumir mensajes de Kafka"""
    try:
        kafka_consumer = get_kafka_consumer()
        logger.info(f"Starting Kafka consumer for {SERVICE_NAME}-{INSTANCE_ID}")
        
        for message in kafka_consumer:
            process_order_event(message)
            
    except Exception as e:
        logger.error(f"Kafka consumer error: {e}")

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
    try:
        # Inyectar falla si está configurada
        inject_failure()
        
        return jsonify({
            'status': 'UP',
            'service': f"{SERVICE_NAME}-{INSTANCE_ID}",
            'timestamp': datetime.utcnow().isoformat(),
            'failure_injected': FAILURE_INJECTED,
            'failure_type': FAILURE_TYPE
        })
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({
            'status': 'DOWN',
            'service': f"{SERVICE_NAME}-{INSTANCE_ID}",
            'error': str(e),
            'timestamp': datetime.utcnow().isoformat()
        }), 500

@app.route('/inventory/<product_id>', methods=['GET'])
def get_inventory(product_id):
    """Consulta inventario de un producto"""
    try:
        # Inyectar falla si está configurada
        inject_failure()
        
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute(
            "SELECT * FROM inventory WHERE product_id = %s",
            (product_id,)
        )
        inventory = cursor.fetchone()
        
        cursor.close()
        conn.close()
        
        if not inventory:
            return jsonify({'error': 'Product not found'}), 404
        
        # Inyectar respuesta incorrecta si está configurada
        if FAILURE_TYPE == 'incorrect_response' and INCORRECT_PRODUCT == product_id:
            # Devolver cantidad incorrecta
            inventory['available_quantity'] = inventory['available_quantity'] + 1000
            logger.warning(f"INCORRECT RESPONSE INJECTED for product {product_id}")
        
        response_data = {
            'product_id': inventory['product_id'],
            'available_quantity': inventory['available_quantity'],
            'reserved_quantity': inventory['reserved_quantity'],
            'instance_id': INSTANCE_ID,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        return jsonify(response_data), 200
        
    except Exception as e:
        logger.error(f"Error getting inventory for {product_id}: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/inventory', methods=['GET'])
def get_all_inventory():
    """Consulta todo el inventario"""
    try:
        inject_failure()
        
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute("SELECT * FROM inventory ORDER BY product_id")
        inventory_list = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        response_data = {
            'inventory': [dict(item) for item in inventory_list],
            'instance_id': INSTANCE_ID,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        return jsonify(response_data), 200
        
    except Exception as e:
        logger.error(f"Error getting all inventory: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/inject-failure', methods=['POST'])
def inject_failure_endpoint():
    """Endpoint para inyectar fallas (solo para testing)"""
    global FAILURE_INJECTED, FAILURE_TYPE, FAILURE_PROBABILITY, LATENCY_MS, INCORRECT_PRODUCT
    
    data = request.get_json()
    failure_type = data.get('type')
    
    if failure_type == 'crash':
        FAILURE_INJECTED = True
        FAILURE_TYPE = 'crash'
        logger.info(f"Crash failure injected in {SERVICE_NAME}-{INSTANCE_ID}")
        
    elif failure_type == 'latency':
        FAILURE_INJECTED = True
        FAILURE_TYPE = 'latency'
        LATENCY_MS = data.get('latency_ms', 1000)
        logger.info(f"Latency failure injected: {LATENCY_MS}ms")
        
    elif failure_type == 'intermittent':
        FAILURE_INJECTED = True
        FAILURE_TYPE = 'intermittent'
        FAILURE_PROBABILITY = data.get('probability', 0.5)
        logger.info(f"Intermittent failure injected: {FAILURE_PROBABILITY} probability")
        
    elif failure_type == 'incorrect_response':
        FAILURE_INJECTED = True
        FAILURE_TYPE = 'incorrect_response'
        INCORRECT_PRODUCT = data.get('product_id')
        logger.info(f"Incorrect response failure injected for product: {INCORRECT_PRODUCT}")
        
    elif failure_type == 'clear':
        FAILURE_INJECTED = False
        FAILURE_TYPE = None
        FAILURE_PROBABILITY = 0.0
        LATENCY_MS = 0
        INCORRECT_PRODUCT = None
        logger.info(f"All failures cleared in {SERVICE_NAME}-{INSTANCE_ID}")
    
    return jsonify({
        'message': f'Failure injection updated for {SERVICE_NAME}-{INSTANCE_ID}',
        'failure_injected': FAILURE_INJECTED,
        'failure_type': FAILURE_TYPE
    })

if __name__ == '__main__':
    # Iniciar consumer de Kafka en thread separado
    consumer_thread = threading.Thread(target=kafka_consumer_thread, daemon=True)
    consumer_thread.start()
    
    app.run(host='0.0.0.0', port=5000, debug=True)