#!/usr/bin/env python3
"""
Script para inyectar fallas en los servicios del experimento
"""

import requests
import time
import json
import argparse
import logging
from datetime import datetime

# Configuración de logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# URLs de los servicios
INVENTORY_SERVICES = {
    '1': 'http://localhost:5001',
    '2': 'http://localhost:5002', 
    '3': 'http://localhost:5003'
}

MONITOR_URL = 'http://localhost:5004'

def inject_crash(instance_id):
    """Inyecta un crash en una instancia específica"""
    if instance_id not in INVENTORY_SERVICES:
        logger.error(f"Invalid instance ID: {instance_id}")
        return False
    
    url = INVENTORY_SERVICES[instance_id]
    
    try:
        response = requests.post(f"{url}/inject-failure", json={
            'type': 'crash'
        }, timeout=5)
        
        if response.status_code == 200:
            logger.info(f"Crash injected in inventory-svc-{instance_id}")
            return True
        else:
            logger.error(f"Failed to inject crash: {response.status_code}")
            return False
            
    except Exception as e:
        logger.error(f"Error injecting crash: {e}")
        return False

def inject_latency(instance_id, latency_ms):
    """Inyecta latencia alta en una instancia específica"""
    if instance_id not in INVENTORY_SERVICES:
        logger.error(f"Invalid instance ID: {instance_id}")
        return False
    
    url = INVENTORY_SERVICES[instance_id]
    
    try:
        response = requests.post(f"{url}/inject-failure", json={
            'type': 'latency',
            'latency_ms': latency_ms
        }, timeout=5)
        
        if response.status_code == 200:
            logger.info(f"Latency {latency_ms}ms injected in inventory-svc-{instance_id}")
            return True
        else:
            logger.error(f"Failed to inject latency: {response.status_code}")
            return False
            
    except Exception as e:
        logger.error(f"Error injecting latency: {e}")
        return False

def inject_intermittent(instance_id, probability):
    """Inyecta errores intermitentes en una instancia específica"""
    if instance_id not in INVENTORY_SERVICES:
        logger.error(f"Invalid instance ID: {instance_id}")
        return False
    
    url = INVENTORY_SERVICES[instance_id]
    
    try:
        response = requests.post(f"{url}/inject-failure", json={
            'type': 'intermittent',
            'probability': probability
        }, timeout=5)
        
        if response.status_code == 200:
            logger.info(f"Intermittent errors (p={probability}) injected in inventory-svc-{instance_id}")
            return True
        else:
            logger.error(f"Failed to inject intermittent errors: {response.status_code}")
            return False
            
    except Exception as e:
        logger.error(f"Error injecting intermittent errors: {e}")
        return False

def inject_incorrect_response(instance_id, product_id):
    """Inyecta respuesta incorrecta para un producto específico"""
    if instance_id not in INVENTORY_SERVICES:
        logger.error(f"Invalid instance ID: {instance_id}")
        return False
    
    url = INVENTORY_SERVICES[instance_id]
    
    try:
        response = requests.post(f"{url}/inject-failure", json={
            'type': 'incorrect_response',
            'product_id': product_id
        }, timeout=5)
        
        if response.status_code == 200:
            logger.info(f"Incorrect response injected for product {product_id} in inventory-svc-{instance_id}")
            return True
        else:
            logger.error(f"Failed to inject incorrect response: {response.status_code}")
            return False
            
    except Exception as e:
        logger.error(f"Error injecting incorrect response: {e}")
        return False

def clear_failures(instance_id):
    """Limpia todas las fallas inyectadas en una instancia"""
    if instance_id not in INVENTORY_SERVICES:
        logger.error(f"Invalid instance ID: {instance_id}")
        return False
    
    url = INVENTORY_SERVICES[instance_id]
    
    try:
        response = requests.post(f"{url}/inject-failure", json={
            'type': 'clear'
        }, timeout=5)
        
        if response.status_code == 200:
            logger.info(f"Failures cleared in inventory-svc-{instance_id}")
            return True
        else:
            logger.error(f"Failed to clear failures: {response.status_code}")
            return False
            
    except Exception as e:
        logger.error(f"Error clearing failures: {e}")
        return False

def get_service_status():
    """Obtiene el estado actual de todos los servicios"""
    try:
        response = requests.get(f"{MONITOR_URL}/status", timeout=5)
        if response.status_code == 200:
            return response.json()
        else:
            logger.error(f"Failed to get service status: {response.status_code}")
            return None
    except Exception as e:
        logger.error(f"Error getting service status: {e}")
        return None

def get_failures():
    """Obtiene el historial de fallas"""
    try:
        response = requests.get(f"{MONITOR_URL}/failures", timeout=5)
        if response.status_code == 200:
            return response.json()
        else:
            logger.error(f"Failed to get failures: {response.status_code}")
            return None
    except Exception as e:
        logger.error(f"Error getting failures: {e}")
        return None

def main():
    parser = argparse.ArgumentParser(description='Inject failures in experiment services')
    parser.add_argument('action', choices=['crash', 'latency', 'intermittent', 'incorrect', 'clear', 'status', 'failures'],
                       help='Action to perform')
    parser.add_argument('--instance', '-i', choices=['1', '2', '3'], required=True,
                       help='Instance ID to target')
    parser.add_argument('--latency', '-l', type=int, default=1000,
                       help='Latency in milliseconds (for latency injection)')
    parser.add_argument('--probability', '-p', type=float, default=0.5,
                       help='Error probability (for intermittent injection)')
    parser.add_argument('--product', type=str, default='PROD-001',
                       help='Product ID (for incorrect response injection)')
    
    args = parser.parse_args()
    
    logger.info(f"Starting failure injection: {args.action} on instance {args.instance}")
    
    if args.action == 'crash':
        success = inject_crash(args.instance)
    elif args.action == 'latency':
        success = inject_latency(args.instance, args.latency)
    elif args.action == 'intermittent':
        success = inject_intermittent(args.instance, args.probability)
    elif args.action == 'incorrect':
        success = inject_incorrect_response(args.instance, args.product)
    elif args.action == 'clear':
        success = clear_failures(args.instance)
    elif args.action == 'status':
        status = get_service_status()
        if status:
            print(json.dumps(status, indent=2))
        return
    elif args.action == 'failures':
        failures = get_failures()
        if failures:
            print(json.dumps(failures, indent=2))
        return
    
    if success:
        logger.info("Failure injection completed successfully")
    else:
        logger.error("Failure injection failed")
        exit(1)

if __name__ == '__main__':
    main()