#!/usr/bin/env python3
"""
Script para realizar pruebas de carga y medir métricas
"""

import requests
import time
import json
import threading
import statistics
import argparse
import logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# Configuración de logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# URLs de los servicios
ORDERS_URL = 'http://localhost:5006'
VOTER_URL = 'http://localhost:5005'
MONITOR_URL = 'http://localhost:5004'

class LoadTester:
    def __init__(self):
        self.results = []
        self.errors = []
        self.start_time = None
        self.end_time = None
    
    def create_order(self, product_id, quantity):
        """Crea una orden"""
        start_time = time.time()
        try:
            response = requests.post(f"{ORDERS_URL}/orders", json={
                'product_id': product_id,
                'quantity': quantity
            }, timeout=10)
            
            latency_ms = int((time.time() - start_time) * 1000)
            
            return {
                'success': response.status_code == 201,
                'status_code': response.status_code,
                'latency_ms': latency_ms,
                'response': response.json() if response.status_code in [200, 201] else None,
                'timestamp': datetime.utcnow().isoformat()
            }
        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            return {
                'success': False,
                'status_code': 0,
                'latency_ms': latency_ms,
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat()
            }
    
    def query_inventory(self, product_id):
        """Consulta inventario a través del voter"""
        start_time = time.time()
        try:
            response = requests.get(f"{VOTER_URL}/inventory/{product_id}", timeout=5)
            
            latency_ms = int((time.time() - start_time) * 1000)
            
            return {
                'success': response.status_code == 200,
                'status_code': response.status_code,
                'latency_ms': latency_ms,
                'response': response.json() if response.status_code == 200 else None,
                'timestamp': datetime.utcnow().isoformat()
            }
        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            return {
                'success': False,
                'status_code': 0,
                'latency_ms': latency_ms,
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat()
            }
    
    def worker_thread(self, operation, args, duration_seconds):
        """Thread worker para operaciones concurrentes"""
        end_time = time.time() + duration_seconds
        
        while time.time() < end_time:
            if operation == 'create_order':
                result = self.create_order(args['product_id'], args['quantity'])
            elif operation == 'query_inventory':
                result = self.query_inventory(args['product_id'])
            else:
                break
            
            self.results.append(result)
            
            if not result['success']:
                self.errors.append(result)
    
    def run_load_test(self, operation, args, rps, duration_seconds):
        """Ejecuta prueba de carga"""
        logger.info(f"Starting load test: {operation} at {rps} RPS for {duration_seconds} seconds")
        
        self.results = []
        self.errors = []
        self.start_time = time.time()
        
        # Calcular número de threads necesarios
        num_threads = max(1, rps // 10)  # 10 requests por thread
        sleep_time = 1.0 / rps if rps > 0 else 0
        
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = []
            
            for _ in range(num_threads):
                future = executor.submit(self.worker_thread, operation, args, duration_seconds)
                futures.append(future)
            
            # Esperar a que terminen todos los threads
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    logger.error(f"Thread error: {e}")
        
        self.end_time = time.time()
        
        # Calcular métricas
        self.calculate_metrics()
    
    def calculate_metrics(self):
        """Calcula métricas de la prueba"""
        if not self.results:
            logger.warning("No results to analyze")
            return
        
        successful_requests = [r for r in self.results if r['success']]
        failed_requests = [r for r in self.results if not r['success']]
        
        latencies = [r['latency_ms'] for r in successful_requests]
        
        total_time = self.end_time - self.start_time
        total_requests = len(self.results)
        actual_rps = total_requests / total_time if total_time > 0 else 0
        
        metrics = {
            'total_requests': total_requests,
            'successful_requests': len(successful_requests),
            'failed_requests': len(failed_requests),
            'success_rate': len(successful_requests) / total_requests * 100 if total_requests > 0 else 0,
            'actual_rps': actual_rps,
            'total_time_seconds': total_time,
            'latency_stats': {
                'min_ms': min(latencies) if latencies else 0,
                'max_ms': max(latencies) if latencies else 0,
                'avg_ms': statistics.mean(latencies) if latencies else 0,
                'p50_ms': statistics.median(latencies) if latencies else 0,
                'p95_ms': self.percentile(latencies, 95) if latencies else 0,
                'p99_ms': self.percentile(latencies, 99) if latencies else 0
            }
        }
        
        self.metrics = metrics
        return metrics
    
    def percentile(self, data, percentile):
        """Calcula percentil"""
        if not data:
            return 0
        sorted_data = sorted(data)
        index = int(len(sorted_data) * percentile / 100)
        return sorted_data[min(index, len(sorted_data) - 1)]
    
    def print_metrics(self):
        """Imprime métricas de forma legible"""
        if not hasattr(self, 'metrics'):
            logger.warning("No metrics available")
            return
        
        m = self.metrics
        print("\n" + "="*50)
        print("LOAD TEST RESULTS")
        print("="*50)
        print(f"Total Requests: {m['total_requests']}")
        print(f"Successful: {m['successful_requests']}")
        print(f"Failed: {m['failed_requests']}")
        print(f"Success Rate: {m['success_rate']:.2f}%")
        print(f"Actual RPS: {m['actual_rps']:.2f}")
        print(f"Total Time: {m['total_time_seconds']:.2f}s")
        print("\nLatency Statistics:")
        print(f"  Min: {m['latency_stats']['min_ms']}ms")
        print(f"  Max: {m['latency_stats']['max_ms']}ms")
        print(f"  Avg: {m['latency_stats']['avg_ms']:.2f}ms")
        print(f"  P50: {m['latency_stats']['p50_ms']}ms")
        print(f"  P95: {m['latency_stats']['p95_ms']}ms")
        print(f"  P99: {m['latency_stats']['p99_ms']}ms")
        print("="*50)

def get_system_metrics():
    """Obtiene métricas del sistema desde el monitor"""
    try:
        response = requests.get(f"{MONITOR_URL}/metrics", timeout=5)
        if response.status_code == 200:
            return response.json()
        else:
            logger.error(f"Failed to get system metrics: {response.status_code}")
            return None
    except Exception as e:
        logger.error(f"Error getting system metrics: {e}")
        return None

def main():
    parser = argparse.ArgumentParser(description='Load test the experiment services')
    parser.add_argument('operation', choices=['create_order', 'query_inventory', 'both'],
                       help='Operation to test')
    parser.add_argument('--rps', type=int, default=50,
                       help='Requests per second')
    parser.add_argument('--duration', type=int, default=300,
                       help='Duration in seconds')
    parser.add_argument('--product-id', default='PROD-001',
                       help='Product ID for testing')
    parser.add_argument('--quantity', type=int, default=1,
                       help='Quantity for orders')
    parser.add_argument('--metrics', action='store_true',
                       help='Show system metrics after test')
    
    args = parser.parse_args()
    
    tester = LoadTester()
    
    if args.operation == 'create_order':
        tester.run_load_test('create_order', {
            'product_id': args.product_id,
            'quantity': args.quantity
        }, args.rps, args.duration)
    elif args.operation == 'query_inventory':
        tester.run_load_test('query_inventory', {
            'product_id': args.product_id
        }, args.rps, args.duration)
    elif args.operation == 'both':
        # Ejecutar ambas operaciones alternadamente
        logger.info("Running both operations alternately")
        # Implementar lógica para alternar entre operaciones
        pass
    
    tester.print_metrics()
    
    if args.metrics:
        print("\nSystem Metrics:")
        system_metrics = get_system_metrics()
        if system_metrics:
            print(json.dumps(system_metrics, indent=2))

if __name__ == '__main__':
    main()