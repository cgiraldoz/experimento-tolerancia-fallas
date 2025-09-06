import os
import json
import time
import logging
from datetime import datetime, timedelta
from flask import Flask, render_template, jsonify, request
import psycopg2
from psycopg2.extras import RealDictCursor
import pandas as pd
import plotly.graph_objs as go
import plotly.utils
import requests

app = Flask(__name__)

# Configuración de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuración
POSTGRES_URL = os.getenv('POSTGRES_URL', 'postgresql://postgres:postgres@localhost:5432/experimento')
SERVICE_NAME = os.getenv('SERVICE_NAME', 'dashboard')

# URLs de los servicios
SERVICES_URLS = {
    'orders-svc': 'http://localhost:5006',
    'inventory-svc-1': 'http://localhost:5001',
    'inventory-svc-2': 'http://localhost:5002',
    'inventory-svc-3': 'http://localhost:5003',
    'monitor-svc': 'http://localhost:5004',
    'voter-svc': 'http://localhost:5005'
}

def get_db_connection():
    return psycopg2.connect(POSTGRES_URL)

def get_service_health():
    """Obtiene el estado de salud de todos los servicios"""
    health_status = {}
    
    for service_name, url in SERVICES_URLS.items():
        try:
            response = requests.get(f"{url}/health", timeout=2)
            if response.status_code == 200:
                data = response.json()
                health_status[service_name] = {
                    'status': 'UP',
                    'response_time': response.elapsed.total_seconds() * 1000,
                    'data': data
                }
            else:
                health_status[service_name] = {
                    'status': 'DOWN',
                    'response_time': 0,
                    'error': f"HTTP {response.status_code}"
                }
        except Exception as e:
            health_status[service_name] = {
                'status': 'DOWN',
                'response_time': 0,
                'error': str(e)
            }
    
    return health_status

def get_instance_status():
    """Obtiene el estado de las instancias desde la base de datos"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute(
            "SELECT * FROM instance_status ORDER BY service_name, instance_id"
        )
        instances = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return [dict(instance) for instance in instances]
        
    except Exception as e:
        logger.error(f"Error getting instance status: {e}")
        return []

def get_failures_history(hours=24):
    """Obtiene el historial de fallas"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        since = datetime.utcnow() - timedelta(hours=hours)
        cursor.execute(
            """
            SELECT * FROM failure_audit 
            WHERE detected_at >= %s 
            ORDER BY detected_at DESC
            """,
            (since,)
        )
        failures = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return [dict(failure) for failure in failures]
        
    except Exception as e:
        logger.error(f"Error getting failures history: {e}")
        return []

def get_request_metrics(hours=1):
    """Obtiene métricas de requests"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        since = datetime.utcnow() - timedelta(hours=hours)
        cursor.execute(
            """
            SELECT service_name, endpoint, method, status_code, 
                   AVG(latency_ms) as avg_latency, 
                   COUNT(*) as request_count,
                   MAX(latency_ms) as max_latency,
                   MIN(latency_ms) as min_latency,
                   PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY latency_ms) as p95_latency,
                   PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY latency_ms) as p99_latency
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
        
        return [dict(metric) for metric in metrics]
        
    except Exception as e:
        logger.error(f"Error getting request metrics: {e}")
        return []

def get_voting_events(hours=1):
    """Obtiene eventos de votación"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        since = datetime.utcnow() - timedelta(hours=hours)
        cursor.execute(
            """
            SELECT request_id, service_name, instance_id, 
                   AVG(response_time_ms) as avg_response_time,
                   COUNT(*) as vote_count
            FROM voting_events 
            WHERE timestamp >= %s 
            GROUP BY request_id, service_name, instance_id
            ORDER BY timestamp DESC
            LIMIT 100
            """,
            (since,)
        )
        events = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return [dict(event) for event in events]
        
    except Exception as e:
        logger.error(f"Error getting voting events: {e}")
        return []

def get_latency_timeseries(hours=1):
    """Obtiene serie temporal de latencias"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        since = datetime.utcnow() - timedelta(hours=hours)
        cursor.execute(
            """
            SELECT 
                DATE_TRUNC('minute', timestamp) as time_bucket,
                service_name,
                AVG(latency_ms) as avg_latency,
                PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY latency_ms) as p95_latency,
                PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY latency_ms) as p99_latency,
                COUNT(*) as request_count
            FROM request_metrics 
            WHERE timestamp >= %s 
            GROUP BY time_bucket, service_name
            ORDER BY time_bucket, service_name
            """,
            (since,)
        )
        timeseries = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return [dict(row) for row in timeseries]
        
    except Exception as e:
        logger.error(f"Error getting latency timeseries: {e}")
        return []

@app.route('/')
def index():
    """Página principal del dashboard"""
    return render_template('dashboard.html')

@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'UP',
        'service': SERVICE_NAME,
        'timestamp': datetime.utcnow().isoformat()
    })

@app.route('/api/health')
def api_health():
    """API para obtener estado de salud de servicios"""
    return jsonify(get_service_health())

@app.route('/api/instances')
def api_instances():
    """API para obtener estado de instancias"""
    return jsonify(get_instance_status())

@app.route('/api/failures')
def api_failures():
    """API para obtener historial de fallas"""
    hours = request.args.get('hours', 24, type=int)
    return jsonify(get_failures_history(hours))

@app.route('/api/metrics')
def api_metrics():
    """API para obtener métricas de requests"""
    hours = request.args.get('hours', 1, type=int)
    return jsonify(get_request_metrics(hours))

@app.route('/api/voting')
def api_voting():
    """API para obtener eventos de votación"""
    hours = request.args.get('hours', 1, type=int)
    return jsonify(get_voting_events(hours))

@app.route('/api/latency-timeseries')
def api_latency_timeseries():
    """API para obtener serie temporal de latencias"""
    hours = request.args.get('hours', 1, type=int)
    return jsonify(get_latency_timeseries(hours))

@app.route('/api/summary')
def api_summary():
    """API para obtener resumen general del sistema"""
    try:
        # Obtener datos
        health_status = get_service_health()
        instances = get_instance_status()
        failures = get_failures_history(24)
        metrics = get_request_metrics(1)
        
        # Calcular estadísticas
        total_services = len(health_status)
        healthy_services = len([s for s in health_status.values() if s['status'] == 'UP'])
        
        total_instances = len(instances)
        active_instances = len([i for i in instances if i['status'] == 'ON'])
        
        total_failures = len(failures)
        recent_failures = len([f for f in failures if 
                              datetime.fromisoformat(f['detected_at'].replace('Z', '+00:00')) > 
                              datetime.utcnow() - timedelta(hours=1)])
        
        # Calcular métricas de latencia
        if metrics:
            avg_latency = sum(m['avg_latency'] for m in metrics if m['avg_latency']) / len([m for m in metrics if m['avg_latency']])
            max_p95 = max(m['p95_latency'] for m in metrics if m['p95_latency'])
            total_requests = sum(m['request_count'] for m in metrics)
        else:
            avg_latency = 0
            max_p95 = 0
            total_requests = 0
        
        summary = {
            'timestamp': datetime.utcnow().isoformat(),
            'services': {
                'total': total_services,
                'healthy': healthy_services,
                'unhealthy': total_services - healthy_services,
                'health_percentage': (healthy_services / total_services * 100) if total_services > 0 else 0
            },
            'instances': {
                'total': total_instances,
                'active': active_instances,
                'inactive': total_instances - active_instances,
                'availability_percentage': (active_instances / total_instances * 100) if total_instances > 0 else 0
            },
            'failures': {
                'total_24h': total_failures,
                'recent_1h': recent_failures
            },
            'performance': {
                'avg_latency_ms': round(avg_latency, 2),
                'max_p95_latency_ms': round(max_p95, 2),
                'total_requests_1h': total_requests
            }
        }
        
        return jsonify(summary)
        
    except Exception as e:
        logger.error(f"Error getting summary: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/charts/latency')
def api_charts_latency():
    """API para generar gráfico de latencias"""
    try:
        timeseries = get_latency_timeseries(1)
        
        if not timeseries:
            return jsonify({'error': 'No data available'})
        
        # Crear DataFrame
        df = pd.DataFrame(timeseries)
        df['time_bucket'] = pd.to_datetime(df['time_bucket'])
        
        # Crear gráfico
        fig = go.Figure()
        
        for service in df['service_name'].unique():
            service_data = df[df['service_name'] == service]
            fig.add_trace(go.Scatter(
                x=service_data['time_bucket'],
                y=service_data['avg_latency'],
                mode='lines+markers',
                name=f'{service} (Avg)',
                line=dict(width=2)
            ))
            fig.add_trace(go.Scatter(
                x=service_data['time_bucket'],
                y=service_data['p95_latency'],
                mode='lines',
                name=f'{service} (P95)',
                line=dict(dash='dash', width=1),
                opacity=0.7
            ))
        
        fig.update_layout(
            title='Latencia por Servicio (Última Hora)',
            xaxis_title='Tiempo',
            yaxis_title='Latencia (ms)',
            hovermode='x unified'
        )
        
        return jsonify(plotly.utils.PlotlyJSONEncoder().encode(fig))
        
    except Exception as e:
        logger.error(f"Error creating latency chart: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/charts/requests')
def api_charts_requests():
    """API para generar gráfico de requests por minuto"""
    try:
        timeseries = get_latency_timeseries(1)
        
        if not timeseries:
            return jsonify({'error': 'No data available'})
        
        # Crear DataFrame
        df = pd.DataFrame(timeseries)
        df['time_bucket'] = pd.to_datetime(df['time_bucket'])
        
        # Crear gráfico
        fig = go.Figure()
        
        for service in df['service_name'].unique():
            service_data = df[df['service_name'] == service]
            fig.add_trace(go.Bar(
                x=service_data['time_bucket'],
                y=service_data['request_count'],
                name=service,
                opacity=0.7
            ))
        
        fig.update_layout(
            title='Requests por Minuto (Última Hora)',
            xaxis_title='Tiempo',
            yaxis_title='Número de Requests',
            barmode='stack'
        )
        
        return jsonify(plotly.utils.PlotlyJSONEncoder().encode(fig))
        
    except Exception as e:
        logger.error(f"Error creating requests chart: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/charts/failures')
def api_charts_failures():
    """API para generar gráfico de fallas por hora"""
    try:
        failures = get_failures_history(24)
        
        if not failures:
            return jsonify({'error': 'No data available'})
        
        # Crear DataFrame
        df = pd.DataFrame(failures)
        df['detected_at'] = pd.to_datetime(df['detected_at'])
        df['hour'] = df['detected_at'].dt.floor('H')
        
        # Agrupar por hora y tipo de falla
        failure_counts = df.groupby(['hour', 'failure_type']).size().reset_index(name='count')
        
        # Crear gráfico
        fig = go.Figure()
        
        for failure_type in failure_counts['failure_type'].unique():
            type_data = failure_counts[failure_counts['failure_type'] == failure_type]
            fig.add_trace(go.Bar(
                x=type_data['hour'],
                y=type_data['count'],
                name=failure_type,
                opacity=0.7
            ))
        
        fig.update_layout(
            title='Fallas Detectadas por Hora (Últimas 24h)',
            xaxis_title='Hora',
            yaxis_title='Número de Fallas',
            barmode='stack'
        )
        
        return jsonify(plotly.utils.PlotlyJSONEncoder().encode(fig))
        
    except Exception as e:
        logger.error(f"Error creating failures chart: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5007, debug=True)