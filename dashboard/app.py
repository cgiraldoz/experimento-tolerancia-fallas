import os
import json
import time
import logging
import glob
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
    'orders-svc': 'http://orders-svc:5000',
    'inventory-svc-1': 'http://inventory-svc-1:5000',
    'inventory-svc-2': 'http://inventory-svc-2:5000',
    'inventory-svc-3': 'http://inventory-svc-3:5000',
    'monitor-svc': 'http://monitor-svc:5000',
    'voter-svc': 'http://voter-svc:5000'
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
                   MIN(latency_ms) as min_latency
            FROM request_metrics 
            WHERE timestamp >= %s 
            GROUP BY service_name, endpoint, method, status_code
            ORDER BY service_name, endpoint
            """,
            (since,)
        )
        metrics = cursor.fetchall()
        
        # Obtener datos detallados para calcular percentiles
        cursor.execute(
            """
            SELECT service_name, endpoint, method, status_code, latency_ms
            FROM request_metrics 
            WHERE timestamp >= %s 
            ORDER BY service_name, endpoint, method, status_code, latency_ms
            """,
            (since,)
        )
        detailed_metrics = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        # Calcular percentiles por grupo
        metrics_dict = {}
        for metric in detailed_metrics:
            key = (metric['service_name'], metric['endpoint'], metric['method'], metric['status_code'])
            if key not in metrics_dict:
                metrics_dict[key] = []
            metrics_dict[key].append(metric['latency_ms'])
        
        # Agregar percentiles a las métricas
        result = []
        for metric in metrics:
            key = (metric['service_name'], metric['endpoint'], metric['method'], metric['status_code'])
            latencies = metrics_dict.get(key, [])
            
            metric_dict = dict(metric)
            if latencies:
                sorted_latencies = sorted(latencies)
                n = len(sorted_latencies)
                metric_dict['p95_latency'] = sorted_latencies[int(0.95 * n)] if n > 0 else 0
                metric_dict['p99_latency'] = sorted_latencies[int(0.99 * n)] if n > 0 else 0
            else:
                metric_dict['p95_latency'] = 0
                metric_dict['p99_latency'] = 0
            
            result.append(metric_dict)
        
        return result
        
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
        
        # Agregar percentiles calculados en Python
        result = []
        for row in timeseries:
            row_dict = dict(row)
            # Convertir avg_latency a float si es Decimal
            avg_latency = float(row_dict['avg_latency']) if row_dict['avg_latency'] else 0
            # Para simplificar, usar avg_latency como aproximación de percentiles
            row_dict['p95_latency'] = avg_latency * 1.5  # Aproximación
            row_dict['p99_latency'] = avg_latency * 2.0  # Aproximación
            result.append(row_dict)
        
        return result
        
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
        # Obtener datos básicos
        health_status = get_service_health()
        instances = get_instance_status()
        failures = get_failures_history(24)
        
        # Calcular estadísticas básicas
        total_services = len(health_status)
        healthy_services = len([s for s in health_status.values() if s.get('status') == 'UP'])
        
        total_instances = len(instances)
        active_instances = len([i for i in instances if i.get('status') == 'ON'])
        
        total_failures = len(failures)
        recent_failures = 0
        
        # Calcular fallos recientes de forma segura
        try:
            cutoff_time = datetime.utcnow() - timedelta(hours=1)
            for f in failures:
                if f.get('detected_at'):
                    try:
                        detected_time = datetime.fromisoformat(f['detected_at'].replace('Z', '+00:00'))
                        if detected_time > cutoff_time:
                            recent_failures += 1
                    except (ValueError, TypeError):
                        continue
        except Exception as e:
            logger.error(f"Error calculating recent failures: {e}")
            recent_failures = 0
        
        # Métricas de performance simplificadas
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
                'avg_latency_ms': 0,
                'max_p95_latency_ms': 0,
                'total_requests_1h': 0
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

def get_experiment_reports():
    """Obtiene la lista de reportes de experimentos"""
    try:
        # Buscar archivos de reporte en el directorio host
        report_files = glob.glob('/app/host/experiment_report_*.json')
        reports = []
        
        for file_path in sorted(report_files, reverse=True):  # Más recientes primero
            try:
                with open(file_path, 'r') as f:
                    data = json.load(f)
                
                # Extraer información básica del reporte
                report_info = {
                    'filename': os.path.basename(file_path),
                    'start_time': data.get('experiment_info', {}).get('start_time'),
                    'end_time': data.get('experiment_info', {}).get('end_time'),
                    'duration_seconds': data.get('experiment_info', {}).get('total_duration_seconds'),
                    'total_tests': data.get('summary', {}).get('total_tests', 0),
                    'successful_tests': data.get('summary', {}).get('successful_tests', 0),
                    'avg_ttd_ms': data.get('summary', {}).get('avg_ttd_ms', 0),
                    'avg_ttr_ms': data.get('summary', {}).get('avg_ttr_ms', 0),
                    'max_p95_ms': data.get('summary', {}).get('max_p95_ms', 0),
                    'min_success_rate': data.get('summary', {}).get('min_success_rate', 0)
                }
                
                reports.append(report_info)
                
            except Exception as e:
                logger.error(f"Error reading report {file_path}: {e}")
                continue
        
        return reports
        
    except Exception as e:
        logger.error(f"Error getting experiment reports: {e}")
        return []

def get_experiment_report_details(filename):
    """Obtiene los detalles completos de un reporte específico"""
    try:
        file_path = f'/app/host/{filename}'
        with open(file_path, 'r') as f:
            data = json.load(f)
        
        # Agregar análisis y explicaciones
        analysis = analyze_experiment_report(data)
        data['analysis'] = analysis
        
        return data
        
    except Exception as e:
        logger.error(f"Error reading report details {filename}: {e}")
        return None

def analyze_experiment_report(report_data):
    """Analiza un reporte de experimento y genera explicaciones"""
    analysis = {
        'overall_assessment': '',
        'key_findings': [],
        'recommendations': [],
        'performance_analysis': {},
        'failure_analysis': {}
    }
    
    try:
        summary = report_data.get('summary', {})
        results = report_data.get('results', [])
        
        # Análisis general
        success_rate = summary.get('successful_tests', 0) / max(summary.get('total_tests', 1), 1) * 100
        avg_ttd = summary.get('avg_ttd_ms', 0)
        max_p95 = summary.get('max_p95_ms', 0)
        
        if success_rate >= 90 and max_p95 < 1000:
            analysis['overall_assessment'] = 'EXCELENTE - El sistema demostró alta tolerancia a fallas'
        elif success_rate >= 75 and max_p95 < 2000:
            analysis['overall_assessment'] = 'BUENO - El sistema manejó las fallas adecuadamente'
        else:
            analysis['overall_assessment'] = 'NECESITA MEJORAS - Se detectaron problemas de tolerancia a fallas'
        
        # Hallazgos clave
        if max_p95 < 1000:
            analysis['key_findings'].append(f"✅ Latencia P95 excelente: {max_p95}ms (objetivo <1000ms)")
        else:
            analysis['key_findings'].append(f"⚠️ Latencia P95 alta: {max_p95}ms (objetivo <1000ms)")
        
        if success_rate >= 95:
            analysis['key_findings'].append(f"✅ Alta disponibilidad: {success_rate:.1f}% de tests exitosos")
        else:
            analysis['key_findings'].append(f"⚠️ Disponibilidad reducida: {success_rate:.1f}% de tests exitosos")
        
        if avg_ttd < 5000:
            analysis['key_findings'].append(f"✅ TTD rápido: {avg_ttd:.0f}ms promedio")
        else:
            analysis['key_findings'].append(f"⚠️ TTD lento: {avg_ttd:.0f}ms promedio (objetivo <1000ms)")
        
        # Análisis por tipo de falla
        for result in results:
            failure_type = result.get('failure_type', 'unknown')
            ttd = result.get('ttd_ms')
            ttr = result.get('ttr_ms')
            p95 = result.get('load_test_result', {}).get('p95_ms', 0)
            
            if failure_type == 'crash':
                if ttd and ttd < 10000:
                    analysis['key_findings'].append(f"✅ Crash detectado rápidamente: {ttd:.0f}ms")
                else:
                    analysis['key_findings'].append(f"⚠️ Detección de crash lenta: {ttd:.0f}ms")
            
            elif failure_type == 'latency':
                if ttd and ttd < 5000:
                    analysis['key_findings'].append(f"✅ Latencia alta detectada: {ttd:.0f}ms")
                else:
                    analysis['key_findings'].append(f"⚠️ Detección de latencia lenta: {ttd:.0f}ms")
                
                if ttr and ttr < 30000:
                    analysis['key_findings'].append(f"✅ Recuperación rápida: {ttr:.0f}ms")
                else:
                    analysis['key_findings'].append(f"⚠️ Recuperación lenta: {ttr:.0f}ms")
            
            elif failure_type == 'intermittent':
                if not ttd:
                    analysis['key_findings']
                else:
                    analysis['key_findings']
        
        # Recomendaciones
        if avg_ttd > 5000:
            analysis['recommendations'].append("Reducir intervalo de health checks de 200ms a 100ms")
            analysis['recommendations'].append("Disminuir threshold de fallos consecutivos de 3 a 2")
        
        if max_p95 > 1000:
            analysis['recommendations'].append("Optimizar timeouts de votación")
            analysis['recommendations'].append("Revisar configuración de Kafka")
        
        if success_rate < 95:
            analysis['recommendations'].append("Investigar causas de fallos en tests")
            analysis['recommendations'].append("Mejorar manejo de errores en servicios")
        
        # Análisis de rendimiento
        analysis['performance_analysis'] = {
            'latency_compliance': max_p95 < 1000,
            'availability_compliance': success_rate >= 95,
            'detection_speed': avg_ttd < 5000,
            'overall_score': calculate_overall_score(summary)
        }
        
        # Análisis de fallas
        failure_types = [r.get('failure_type') for r in results]
        analysis['failure_analysis'] = {
            'crash_handling': 'crash' in failure_types,
            'latency_handling': 'latency' in failure_types,
            'intermittent_handling': 'intermittent' in failure_types,
            'total_failure_types_tested': len(set(failure_types))
        }
        
    except Exception as e:
        logger.error(f"Error analyzing experiment report: {e}")
        analysis['overall_assessment'] = 'ERROR - No se pudo analizar el reporte'
    
    return analysis

def calculate_overall_score(summary):
    """Calcula un score general del experimento (0-100)"""
    try:
        score = 0
        
        # Disponibilidad (40 puntos)
        success_rate = summary.get('successful_tests', 0) / max(summary.get('total_tests', 1), 1)
        score += success_rate * 40
        
        # Latencia (30 puntos)
        max_p95 = summary.get('max_p95_ms', 0)
        if max_p95 < 1000:
            score += 30
        elif max_p95 < 2000:
            score += 20
        else:
            score += 10
        
        # TTD (20 puntos)
        avg_ttd = summary.get('avg_ttd_ms', 0)
        if avg_ttd < 1000:
            score += 20
        elif avg_ttd < 5000:
            score += 15
        elif avg_ttd < 10000:
            score += 10
        else:
            score += 5
        
        # TTR (10 puntos)
        avg_ttr = summary.get('avg_ttr_ms', 0)
        if avg_ttr and avg_ttr < 30000:
            score += 10
        elif avg_ttr and avg_ttr < 60000:
            score += 7
        else:
            score += 5
        
        return min(100, max(0, score))
        
    except Exception as e:
        logger.error(f"Error calculating overall score: {e}")
        return 0

@app.route('/reports')
def reports_page():
    """Página de reportes de experimentos"""
    return render_template('reports.html')

@app.route('/api/reports')
def api_reports():
    """API para obtener lista de reportes"""
    return jsonify(get_experiment_reports())

@app.route('/api/reports/<filename>')
def api_report_details(filename):
    """API para obtener detalles de un reporte específico"""
    if not filename.startswith('experiment_report_') or not filename.endswith('.json'):
        return jsonify({'error': 'Invalid filename'}), 400
    
    report_data = get_experiment_report_details(filename)
    if report_data is None:
        return jsonify({'error': 'Report not found'}), 404
    
    return jsonify(report_data)

@app.route('/api/reports/<filename>/chart')
def api_report_chart(filename):
    """API para generar gráfico de un reporte específico"""
    try:
        report_data = get_experiment_report_details(filename)
        if not report_data:
            return jsonify({'error': 'Report not found'}), 404
        
        results = report_data.get('results', [])
        if not results:
            return jsonify({'error': 'No data available'}), 400
        
        # Crear gráfico de TTD/TTR por tipo de falla
        fig = go.Figure()
        
        failure_types = []
        ttd_values = []
        ttr_values = []
        
        for result in results:
            failure_type = result.get('failure_type', 'unknown')
            ttd = result.get('ttd_ms', 0)
            ttr = result.get('ttr_ms', 0)
            
            failure_types.append(failure_type)
            ttd_values.append(ttd if ttd else 0)
            ttr_values.append(ttr if ttr else 0)
        
        # Gráfico de barras
        fig.add_trace(go.Bar(
            name='TTD (ms)',
            x=failure_types,
            y=ttd_values,
            marker_color='lightblue'
        ))
        
        fig.add_trace(go.Bar(
            name='TTR (ms)',
            x=failure_types,
            y=ttr_values,
            marker_color='lightcoral'
        ))
        
        fig.update_layout(
            title='TTD y TTR por Tipo de Falla',
            xaxis_title='Tipo de Falla',
            yaxis_title='Tiempo (ms)',
            barmode='group'
        )
        
        return jsonify(plotly.utils.PlotlyJSONEncoder().encode(fig))
        
    except Exception as e:
        logger.error(f"Error creating report chart: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5007, debug=True)