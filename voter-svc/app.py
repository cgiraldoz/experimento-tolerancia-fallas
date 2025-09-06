import os
import json
import time
import logging
import statistics
import requests
from datetime import datetime
from flask import Flask, request, jsonify
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)

# Configuración de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuración
POSTGRES_URL = os.getenv('POSTGRES_URL', 'postgresql://postgres:postgres@localhost:5432/experimento')
SERVICE_NAME = os.getenv('SERVICE_NAME', 'voter-svc')

# URLs de las instancias de inventory-svc
INVENTORY_INSTANCES = [
    {'id': '1', 'url': 'http://inventory-svc-1:5000'},
    {'id': '2', 'url': 'http://inventory-svc-2:5000'},
    {'id': '3', 'url': 'http://inventory-svc-3:5000'}
]

# Configuración de votación
VOTING_TIMEOUT = 0.3  # 300ms timeout para fan-out
QUORUM_SIZE = 2  # Mínimo 2 de 3 respuestas para quórum

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

def get_active_instances():
    """Obtiene las instancias activas desde la base de datos"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT instance_id FROM instance_status WHERE service_name = 'inventory-svc' AND status = 'ON'"
        )
        active_instances = [row[0] for row in cursor.fetchall()]
        
        cursor.close()
        conn.close()
        
        return active_instances
        
    except Exception as e:
        logger.error(f"Error getting active instances: {e}")
        return ['1', '2', '3']  # Fallback a todas las instancias

def log_voting_event(request_id, service_name, instance_id, response_data, response_time_ms):
    """Registra un evento de votación en la base de datos"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            "INSERT INTO voting_events (request_id, service_name, instance_id, response_data, response_time_ms) VALUES (%s, %s, %s, %s, %s)",
            (request_id, service_name, instance_id, json.dumps(response_data), response_time_ms)
        )
        conn.commit()
        cursor.close()
        conn.close()
        
    except Exception as e:
        logger.error(f"Error logging voting event: {e}")

def make_request_to_instance(instance_id, url, endpoint, timeout=VOTING_TIMEOUT):
    """Hace una petición a una instancia específica"""
    try:
        start_time = time.time()
        response = requests.get(f"{url}{endpoint}", timeout=timeout)
        response_time_ms = int((time.time() - start_time) * 1000)
        
        if response.status_code == 200:
            data = response.json()
            return {
                'success': True,
                'data': data,
                'response_time_ms': response_time_ms,
                'instance_id': instance_id,
                'status_code': response.status_code
            }
        else:
            return {
                'success': False,
                'error': f"HTTP {response.status_code}",
                'response_time_ms': response_time_ms,
                'instance_id': instance_id,
                'status_code': response.status_code
            }
            
    except requests.exceptions.Timeout:
        return {
            'success': False,
            'error': 'Timeout',
            'response_time_ms': int(timeout * 1000),
            'instance_id': instance_id,
            'status_code': 0
        }
    except requests.exceptions.ConnectionError:
        return {
            'success': False,
            'error': 'Connection error',
            'response_time_ms': 0,
            'instance_id': instance_id,
            'status_code': 0
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'response_time_ms': 0,
            'instance_id': instance_id,
            'status_code': 0
        }

def detect_outlier(responses, field='available_quantity'):
    """Detecta outliers en las respuestas usando desviación estándar"""
    try:
        # Filtrar respuestas exitosas
        successful_responses = [r for r in responses if r['success'] and field in r['data']]
        
        if len(successful_responses) < 2:
            return None
        
        # Extraer valores del campo especificado
        values = [r['data'][field] for r in successful_responses]
        
        if len(values) < 2:
            return None
        
        # Calcular media y desviación estándar
        mean_val = statistics.mean(values)
        stdev_val = statistics.stdev(values) if len(values) > 1 else 0
        
        # Si la desviación estándar es muy pequeña, no hay outliers
        if stdev_val < 1:
            return None
        
        # Detectar outliers (valores que se desvían más de 2 desviaciones estándar)
        outliers = []
        for i, value in enumerate(values):
            if abs(value - mean_val) > 2 * stdev_val:
                outliers.append(successful_responses[i]['instance_id'])
        
        return outliers if outliers else None
        
    except Exception as e:
        logger.error(f"Error detecting outliers: {e}")
        return None

def aggregate_responses(responses, request_id):
    """Agrega respuestas por mayoría y detecta outliers"""
    try:
        # Filtrar respuestas exitosas
        successful_responses = [r for r in responses if r['success']]
        failed_responses = [r for r in responses if not r['success']]
        
        logger.info(f"Voting for request {request_id}: {len(successful_responses)} successful, {len(failed_responses)} failed")
        
        # Si no hay suficientes respuestas exitosas para quórum
        if len(successful_responses) < QUORUM_SIZE:
            logger.warning(f"Insufficient responses for quorum: {len(successful_responses)} < {QUORUM_SIZE}")
            return {
                'success': False,
                'error': 'Insufficient responses for quorum',
                'quorum_achieved': False,
                'successful_responses': len(successful_responses),
                'required_quorum': QUORUM_SIZE
            }
        
        # Detectar outliers en respuestas exitosas
        outliers = detect_outlier(successful_responses)
        
        # Filtrar outliers si se detectan
        if outliers:
            logger.warning(f"Detected outliers: {outliers}")
            # Reportar outliers al monitor
            report_outliers_to_monitor(outliers, request_id)
            # Filtrar respuestas de outliers
            successful_responses = [r for r in successful_responses if r['instance_id'] not in outliers]
        
        # Si después de filtrar outliers no hay quórum
        if len(successful_responses) < QUORUM_SIZE:
            logger.warning(f"Insufficient responses after outlier removal: {len(successful_responses)} < {QUORUM_SIZE}")
            return {
                'success': False,
                'error': 'Insufficient responses after outlier removal',
                'quorum_achieved': False,
                'successful_responses': len(successful_responses),
                'required_quorum': QUORUM_SIZE,
                'outliers_detected': outliers
            }
        
        # Agregar respuestas por mayoría
        if successful_responses[0]['data'].get('inventory'):
            # Respuesta de get_all_inventory
            aggregated_data = aggregate_inventory_list(successful_responses)
        else:
            # Respuesta de get_inventory individual
            aggregated_data = aggregate_single_inventory(successful_responses)
        
        # Calcular métricas de votación
        response_times = [r['response_time_ms'] for r in successful_responses]
        avg_response_time = statistics.mean(response_times)
        max_response_time = max(response_times)
        
        return {
            'success': True,
            'data': aggregated_data,
            'quorum_achieved': True,
            'successful_responses': len(successful_responses),
            'failed_responses': len(failed_responses),
            'outliers_detected': outliers,
            'voting_metrics': {
                'avg_response_time_ms': avg_response_time,
                'max_response_time_ms': max_response_time,
                'participating_instances': [r['instance_id'] for r in successful_responses]
            }
        }
        
    except Exception as e:
        logger.error(f"Error aggregating responses: {e}")
        return {
            'success': False,
            'error': str(e),
            'quorum_achieved': False
        }

def aggregate_single_inventory(responses):
    """Agrega respuestas de consulta individual de inventario"""
    try:
        # Tomar la primera respuesta exitosa como base
        base_response = responses[0]['data']
        
        # Para inventario individual, usar la respuesta con menor latencia
        fastest_response = min(responses, key=lambda x: x['response_time_ms'])
        
        aggregated = {
            'product_id': base_response['product_id'],
            'available_quantity': fastest_response['data']['available_quantity'],
            'reserved_quantity': fastest_response['data']['reserved_quantity'],
            'timestamp': datetime.utcnow().isoformat(),
            'voted_by': fastest_response['instance_id']
        }
        
        return aggregated
        
    except Exception as e:
        logger.error(f"Error aggregating single inventory: {e}")
        return responses[0]['data'] if responses else {}

def aggregate_inventory_list(responses):
    """Agrega respuestas de consulta de todo el inventario"""
    try:
        # Tomar la primera respuesta como base
        base_response = responses[0]['data']
        inventory_list = base_response['inventory']
        
        # Para cada producto, usar la respuesta con menor latencia
        for product in inventory_list:
            product_id = product['product_id']
            
            # Encontrar la respuesta más rápida para este producto
            fastest_for_product = min(responses, key=lambda x: x['response_time_ms'])
            fastest_inventory = next(
                (item for item in fastest_for_product['data']['inventory'] if item['product_id'] == product_id),
                product
            )
            
            product['available_quantity'] = fastest_inventory['available_quantity']
            product['reserved_quantity'] = fastest_inventory['reserved_quantity']
        
        aggregated = {
            'inventory': inventory_list,
            'timestamp': datetime.utcnow().isoformat(),
            'voted_by': 'majority'
        }
        
        return aggregated
        
    except Exception as e:
        logger.error(f"Error aggregating inventory list: {e}")
        return responses[0]['data'] if responses else {'inventory': []}

def report_outliers_to_monitor(outliers, request_id):
    """Reporta outliers detectados al monitor"""
    try:
        # Aquí podrías enviar una notificación al monitor-svc
        # Por ahora, solo logueamos
        logger.warning(f"Outliers detected for request {request_id}: {outliers}")
        
        # Opcional: enviar HTTP request al monitor
        # requests.post('http://monitor-svc:5000/report-outlier', json={
        #     'outliers': outliers,
        #     'request_id': request_id,
        #     'timestamp': datetime.utcnow().isoformat()
        # })
        
    except Exception as e:
        logger.error(f"Error reporting outliers: {e}")

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

@app.route('/inventory/<product_id>', methods=['GET'])
def get_inventory_voted(product_id):
    """Consulta inventario con votación por mayoría"""
    request_id = f"req_{int(time.time() * 1000)}"
    start_time = time.time()
    
    try:
        # Obtener instancias activas
        active_instances = get_active_instances()
        logger.info(f"Active instances for voting: {active_instances}")
        
        # Hacer peticiones a todas las instancias activas
        responses = []
        for instance in INVENTORY_INSTANCES:
            if instance['id'] in active_instances:
                response = make_request_to_instance(
                    instance['id'],
                    instance['url'],
                    f'/inventory/{product_id}'
                )
                responses.append(response)
                
                # Log del evento de votación
                log_voting_event(
                    request_id,
                    'inventory-svc',
                    instance['id'],
                    response.get('data', {}),
                    response['response_time_ms']
                )
        
        # Agregar respuestas
        result = aggregate_responses(responses, request_id)
        
        total_time_ms = int((time.time() - start_time) * 1000)
        result['total_time_ms'] = total_time_ms
        result['request_id'] = request_id
        
        if result['success']:
            return jsonify(result), 200
        else:
            return jsonify(result), 503
            
    except Exception as e:
        logger.error(f"Error in voted inventory query: {e}")
        return jsonify({
            'error': 'Internal server error',
            'request_id': request_id,
            'total_time_ms': int((time.time() - start_time) * 1000)
        }), 500

@app.route('/inventory', methods=['GET'])
def get_all_inventory_voted():
    """Consulta todo el inventario con votación por mayoría"""
    request_id = f"req_{int(time.time() * 1000)}"
    start_time = time.time()
    
    try:
        # Obtener instancias activas
        active_instances = get_active_instances()
        logger.info(f"Active instances for voting: {active_instances}")
        
        # Hacer peticiones a todas las instancias activas
        responses = []
        for instance in INVENTORY_INSTANCES:
            if instance['id'] in active_instances:
                response = make_request_to_instance(
                    instance['id'],
                    instance['url'],
                    '/inventory'
                )
                responses.append(response)
                
                # Log del evento de votación
                log_voting_event(
                    request_id,
                    'inventory-svc',
                    instance['id'],
                    response.get('data', {}),
                    response['response_time_ms']
                )
        
        # Agregar respuestas
        result = aggregate_responses(responses, request_id)
        
        total_time_ms = int((time.time() - start_time) * 1000)
        result['total_time_ms'] = total_time_ms
        result['request_id'] = request_id
        
        if result['success']:
            return jsonify(result), 200
        else:
            return jsonify(result), 503
            
    except Exception as e:
        logger.error(f"Error in voted inventory query: {e}")
        return jsonify({
            'error': 'Internal server error',
            'request_id': request_id,
            'total_time_ms': int((time.time() - start_time) * 1000)
        }), 500

@app.route('/voting-stats', methods=['GET'])
def get_voting_stats():
    """Obtiene estadísticas de votación"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Estadísticas de los últimos 10 minutos
        cursor.execute(
            """
            SELECT 
                COUNT(*) as total_requests,
                AVG(response_time_ms) as avg_response_time,
                MAX(response_time_ms) as max_response_time,
                MIN(response_time_ms) as min_response_time
            FROM voting_events 
            WHERE timestamp >= NOW() - INTERVAL '10 minutes'
            """
        )
        stats = cursor.fetchone()
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'voting_stats': dict(stats),
            'timestamp': datetime.utcnow().isoformat()
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting voting stats: {e}")
        return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)