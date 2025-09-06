#!/usr/bin/env python3
"""
Script principal para ejecutar el experimento completo
"""

import subprocess
import time
import json
import requests
import logging
from datetime import datetime

# Configuración de logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ExperimentRunner:
    def __init__(self):
        self.results = []
        self.start_time = None
        self.end_time = None
    
    def wait_for_services(self, timeout=60):
        """Espera a que todos los servicios estén disponibles"""
        logger.info("Waiting for services to be ready...")
        
        services = [
            'http://localhost:5000/health',  # orders-svc
            'http://localhost:5001/health',  # inventory-svc-1
            'http://localhost:5002/health',  # inventory-svc-2
            'http://localhost:5003/health',  # inventory-svc-3
            'http://localhost:5004/health',  # monitor-svc
            'http://localhost:5005/health'   # voter-svc
        ]
        
        start_time = time.time()
        while time.time() - start_time < timeout:
            all_ready = True
            for service in services:
                try:
                    response = requests.get(service, timeout=2)
                    if response.status_code != 200:
                        all_ready = False
                        break
                except:
                    all_ready = False
                    break
            
            if all_ready:
                logger.info("All services are ready!")
                return True
            
            time.sleep(2)
        
        logger.error("Timeout waiting for services")
        return False
    
    def run_baseline_test(self, duration=60):
        """Ejecuta prueba de línea base sin fallas"""
        logger.info("Running baseline test...")
        
        # Ejecutar prueba de carga
        cmd = [
            'python', 'scripts/load_test.py', 'query_inventory',
            '--rps', '50',
            '--duration', str(duration),
            '--product-id', 'PROD-001'
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            logger.info("Baseline test completed successfully")
            return True
        else:
            logger.error(f"Baseline test failed: {result.stderr}")
            return False
    
    def inject_failure_and_measure(self, failure_type, instance_id, **kwargs):
        """Inyecta una falla y mide el tiempo de detección y recuperación"""
        logger.info(f"Injecting {failure_type} failure in instance {instance_id}")
        
        # Registrar tiempo de inyección
        injection_time = time.time()
        
        # Inyectar falla
        cmd = ['python', 'scripts/inject_failures.py', failure_type, '--instance', instance_id]
        
        if failure_type == 'latency' and 'latency_ms' in kwargs:
            cmd.extend(['--latency', str(kwargs['latency_ms'])])
        elif failure_type == 'intermittent' and 'probability' in kwargs:
            cmd.extend(['--probability', str(kwargs['probability'])])
        elif failure_type == 'incorrect' and 'product_id' in kwargs:
            cmd.extend(['--product', kwargs['product_id']])
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            logger.error(f"Failed to inject failure: {result.stderr}")
            return None
        
        # Medir tiempo de detección
        detection_time = self.measure_detection_time(instance_id)
        
        # Medir tiempo de recuperación (si aplica)
        recovery_time = None
        if failure_type in ['latency', 'intermittent', 'incorrect']:
            recovery_time = self.measure_recovery_time(instance_id)
        
        # Ejecutar prueba de carga durante la falla
        load_test_result = self.run_load_test_during_failure(duration=30)
        
        return {
            'failure_type': failure_type,
            'instance_id': instance_id,
            'injection_time': injection_time,
            'detection_time': detection_time,
            'recovery_time': recovery_time,
            'ttd_ms': (detection_time - injection_time) * 1000 if detection_time else None,
            'ttr_ms': (recovery_time - injection_time) * 1000 if recovery_time else None,
            'load_test_result': load_test_result,
            'parameters': kwargs
        }
    
    def measure_detection_time(self, instance_id):
        """Mide el tiempo hasta que se detecta la falla"""
        logger.info(f"Measuring detection time for instance {instance_id}")
        
        start_time = time.time()
        timeout = 30  # 30 segundos máximo
        
        while time.time() - start_time < timeout:
            try:
                response = requests.get('http://localhost:5004/status', timeout=2)
                if response.status_code == 200:
                    data = response.json()
                    
                    # Buscar la instancia en el estado
                    for instance in data.get('instances', []):
                        if (instance['service_name'] == 'inventory-svc' and 
                            instance['instance_id'] == instance_id and 
                            instance['status'] == 'OFF'):
                            detection_time = time.time()
                            logger.info(f"Failure detected at {detection_time - start_time:.2f}s")
                            return detection_time
                
                time.sleep(0.5)
            except:
                time.sleep(0.5)
        
        logger.warning(f"Detection timeout for instance {instance_id}")
        return None
    
    def measure_recovery_time(self, instance_id):
        """Mide el tiempo hasta que se recupera la instancia"""
        logger.info(f"Measuring recovery time for instance {instance_id}")
        
        # Limpiar falla
        cmd = ['python', 'scripts/inject_failures.py', 'clear', '--instance', instance_id]
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            logger.error(f"Failed to clear failure: {result.stderr}")
            return None
        
        start_time = time.time()
        timeout = 30  # 30 segundos máximo
        
        while time.time() - start_time < timeout:
            try:
                response = requests.get('http://localhost:5004/status', timeout=2)
                if response.status_code == 200:
                    data = response.json()
                    
                    # Buscar la instancia en el estado
                    for instance in data.get('instances', []):
                        if (instance['service_name'] == 'inventory-svc' and 
                            instance['instance_id'] == instance_id and 
                            instance['status'] == 'ON'):
                            recovery_time = time.time()
                            logger.info(f"Instance recovered at {recovery_time - start_time:.2f}s")
                            return recovery_time
                
                time.sleep(0.5)
            except:
                time.sleep(0.5)
        
        logger.warning(f"Recovery timeout for instance {instance_id}")
        return None
    
    def run_load_test_during_failure(self, duration=30):
        """Ejecuta prueba de carga durante una falla"""
        logger.info(f"Running load test during failure for {duration}s")
        
        cmd = [
            'python', 'scripts/load_test.py', 'query_inventory',
            '--rps', '50',
            '--duration', str(duration),
            '--product-id', 'PROD-001'
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            # Parsear métricas del output
            output_lines = result.stdout.split('\n')
            metrics = {}
            
            for line in output_lines:
                if 'P95:' in line:
                    metrics['p95_ms'] = int(line.split('P95:')[1].split('ms')[0].strip())
                elif 'P99:' in line:
                    metrics['p99_ms'] = int(line.split('P99:')[1].split('ms')[0].strip())
                elif 'Success Rate:' in line:
                    metrics['success_rate'] = float(line.split('Success Rate:')[1].split('%')[0].strip())
            
            return metrics
        else:
            logger.error(f"Load test during failure failed: {result.stderr}")
            return None
    
    def run_experiment(self):
        """Ejecuta el experimento completo"""
        logger.info("Starting experiment...")
        self.start_time = time.time()
        
        # Esperar a que los servicios estén listos
        if not self.wait_for_services():
            logger.error("Services not ready, aborting experiment")
            return False
        
        # Ejecutar línea base
        logger.info("Phase 1: Baseline test")
        if not self.run_baseline_test(duration=60):
            logger.error("Baseline test failed")
            return False
        
        time.sleep(10)  # Pausa entre fases
        
        # Fase 2: Crash failure
        logger.info("Phase 2: Crash failure test")
        crash_result = self.inject_failure_and_measure('crash', '1')
        if crash_result:
            self.results.append(crash_result)
        
        time.sleep(10)
        
        # Fase 3: Latency failure
        logger.info("Phase 3: Latency failure test")
        latency_result = self.inject_failure_and_measure('latency', '2', latency_ms=1200)
        if latency_result:
            self.results.append(latency_result)
        
        time.sleep(10)
        
        # Fase 4: Intermittent failure
        logger.info("Phase 4: Intermittent failure test")
        intermittent_result = self.inject_failure_and_measure('intermittent', '3', probability=0.3)
        if intermittent_result:
            self.results.append(intermittent_result)
        
        time.sleep(10)
        
        # Fase 5: Incorrect response failure
        logger.info("Phase 5: Incorrect response failure test")
        incorrect_result = self.inject_failure_and_measure('incorrect', '1', product_id='PROD-001')
        if incorrect_result:
            self.results.append(incorrect_result)
        
        self.end_time = time.time()
        
        # Generar reporte
        self.generate_report()
        
        logger.info("Experiment completed!")
        return True
    
    def generate_report(self):
        """Genera reporte del experimento"""
        logger.info("Generating experiment report...")
        
        report = {
            'experiment_info': {
                'start_time': datetime.fromtimestamp(self.start_time).isoformat(),
                'end_time': datetime.fromtimestamp(self.end_time).isoformat(),
                'total_duration_seconds': self.end_time - self.start_time
            },
            'results': self.results,
            'summary': self.calculate_summary()
        }
        
        # Guardar reporte
        filename = f"experiment_report_{int(self.start_time)}.json"
        with open(filename, 'w') as f:
            json.dump(report, f, indent=2)
        
        logger.info(f"Report saved to {filename}")
        
        # Imprimir resumen
        self.print_summary(report['summary'])
    
    def calculate_summary(self):
        """Calcula resumen de métricas"""
        summary = {
            'total_tests': len(self.results),
            'successful_tests': len([r for r in self.results if r is not None]),
            'avg_ttd_ms': 0,
            'avg_ttr_ms': 0,
            'max_p95_ms': 0,
            'min_success_rate': 100
        }
        
        ttd_values = [r['ttd_ms'] for r in self.results if r and r['ttd_ms']]
        ttr_values = [r['ttr_ms'] for r in self.results if r and r['ttr_ms']]
        
        if ttd_values:
            summary['avg_ttd_ms'] = sum(ttd_values) / len(ttd_values)
        
        if ttr_values:
            summary['avg_ttr_ms'] = sum(ttr_values) / len(ttr_values)
        
        for result in self.results:
            if result and result.get('load_test_result'):
                load_result = result['load_test_result']
                if 'p95_ms' in load_result:
                    summary['max_p95_ms'] = max(summary['max_p95_ms'], load_result['p95_ms'])
                if 'success_rate' in load_result:
                    summary['min_success_rate'] = min(summary['min_success_rate'], load_result['success_rate'])
        
        return summary
    
    def print_summary(self, summary):
        """Imprime resumen del experimento"""
        print("\n" + "="*60)
        print("EXPERIMENT SUMMARY")
        print("="*60)
        print(f"Total Tests: {summary['total_tests']}")
        print(f"Successful Tests: {summary['successful_tests']}")
        print(f"Average TTD: {summary['avg_ttd_ms']:.2f}ms")
        print(f"Average TTR: {summary['avg_ttr_ms']:.2f}ms")
        print(f"Max P95 Latency: {summary['max_p95_ms']}ms")
        print(f"Min Success Rate: {summary['min_success_rate']:.2f}%")
        print("="*60)

def main():
    runner = ExperimentRunner()
    success = runner.run_experiment()
    
    if success:
        logger.info("Experiment completed successfully")
        exit(0)
    else:
        logger.error("Experiment failed")
        exit(1)

if __name__ == '__main__':
    main()