import os
import json
import uuid
import time
import logging
from datetime import datetime
from flask import Flask, request, jsonify
from kafka import KafkaProducer
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)

# Configuración de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuración
KAFKA_BOOTSTRAP_SERVERS = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092')
POSTGRES_URL = os.getenv('POSTGRES_URL', 'postgresql://postgres:postgres@localhost:5432/experimento')
SERVICE_NAME = os.getenv('SERVICE_NAME', 'orders-svc')

# Kafka Producer
producer = None

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
            (SERVICE_NAME, endpoint, method, status_code, latency_ms)
        )
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        logger.error(f"Error logging metrics: {e}")

def publish_error_to_kafka(error_data):
    """Publica errores a la cola de errores de Kafka"""
    try:
        kafka_producer = get_kafka_producer()
        kafka_producer.send('error-queue', value=error_data)
        kafka_producer.flush()
        logger.info(f"Error published to Kafka: {error_data}")
    except Exception as e:
        logger.error(f"Failed to publish error to Kafka: {e}")

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

@app.route('/orders', methods=['POST'])
def create_order():
    """Crea una nueva orden y publica evento a Kafka"""
    start_time = time.time()
    
    try:
        data = request.get_json()
        
        if not data or 'product_id' not in data or 'quantity' not in data:
            return jsonify({'error': 'product_id and quantity are required'}), 400
        
        product_id = data['product_id']
        quantity = int(data['quantity'])
        
        if quantity <= 0:
            return jsonify({'error': 'quantity must be positive'}), 400
        
        # Generar ID único para la orden
        order_id = str(uuid.uuid4())
        
        # Guardar orden en base de datos
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO orders (order_id, product_id, quantity, status) VALUES (%s, %s, %s, %s)",
            (order_id, product_id, quantity, 'PENDING')
        )
        conn.commit()
        cursor.close()
        conn.close()
        
        # Publicar evento a Kafka
        order_event = {
            'order_id': order_id,
            'product_id': product_id,
            'quantity': quantity,
            'action': 'reserve',
            'timestamp': datetime.utcnow().isoformat(),
            'service': SERVICE_NAME
        }
        
        kafka_producer = get_kafka_producer()
        kafka_producer.send('order-events', key=order_id, value=order_event)
        kafka_producer.flush()
        
        logger.info(f"Order created: {order_id} for product {product_id}, quantity {quantity}")
        
        return jsonify({
            'order_id': order_id,
            'product_id': product_id,
            'quantity': quantity,
            'status': 'PENDING',
            'message': 'Order created successfully'
        }), 201
        
    except Exception as e:
        error_data = {
            'error': str(e),
            'service': SERVICE_NAME,
            'endpoint': '/orders',
            'timestamp': datetime.utcnow().isoformat(),
            'request_data': data if 'data' in locals() else None
        }
        
        # Publicar error a cola de errores
        publish_error_to_kafka(error_data)
        
        logger.error(f"Error creating order: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/orders/<order_id>/cancel', methods=['POST'])
def cancel_order(order_id):
    """Cancela una orden existente"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Verificar que la orden existe
        cursor.execute("SELECT status FROM orders WHERE order_id = %s", (order_id,))
        result = cursor.fetchone()
        
        if not result:
            cursor.close()
            conn.close()
            return jsonify({'error': 'Order not found'}), 404
        
        current_status = result[0]
        if current_status == 'CANCELLED':
            cursor.close()
            conn.close()
            return jsonify({'error': 'Order already cancelled'}), 400
        
        # Actualizar estado a CANCELLED
        cursor.execute(
            "UPDATE orders SET status = %s, updated_at = %s WHERE order_id = %s",
            ('CANCELLED', datetime.utcnow(), order_id)
        )
        conn.commit()
        cursor.close()
        conn.close()
        
        # Publicar evento de cancelación a Kafka
        cancel_event = {
            'order_id': order_id,
            'action': 'cancel',
            'timestamp': datetime.utcnow().isoformat(),
            'service': SERVICE_NAME
        }
        
        kafka_producer = get_kafka_producer()
        kafka_producer.send('order-events', key=order_id, value=cancel_event)
        kafka_producer.flush()
        
        logger.info(f"Order cancelled: {order_id}")
        
        return jsonify({
            'order_id': order_id,
            'status': 'CANCELLED',
            'message': 'Order cancelled successfully'
        }), 200
        
    except Exception as e:
        error_data = {
            'error': str(e),
            'service': SERVICE_NAME,
            'endpoint': f'/orders/{order_id}/cancel',
            'timestamp': datetime.utcnow().isoformat()
        }
        
        publish_error_to_kafka(error_data)
        
        logger.error(f"Error cancelling order {order_id}: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/orders/<order_id>', methods=['GET'])
def get_order(order_id):
    """Obtiene información de una orden específica"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute(
            "SELECT * FROM orders WHERE order_id = %s",
            (order_id,)
        )
        order = cursor.fetchone()
        
        cursor.close()
        conn.close()
        
        if not order:
            return jsonify({'error': 'Order not found'}), 404
        
        return jsonify(dict(order)), 200
        
    except Exception as e:
        logger.error(f"Error getting order {order_id}: {e}")
        return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)