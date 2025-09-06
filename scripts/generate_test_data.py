#!/usr/bin/env python3
"""
Script para generar datos de prueba para el dashboard
"""

import requests
import time
import random
import logging
from datetime import datetime, timedelta

# Configuración de logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# URLs de los servicios
ORDERS_URL = 'http://localhost:5006'
VOTER_URL = 'http://localhost:5005'

def create_test_orders(count=50):
    """Crea órdenes de prueba"""
    logger.info(f"Creando {count} órdenes de prueba...")
    
    products = ['PROD-001', 'PROD-002', 'PROD-003']
    successful = 0
    
    for i in range(count):
        try:
            product = random.choice(products)
            quantity = random.randint(1, 10)
            
            response = requests.post(f"{ORDERS_URL}/orders", json={
                'product_id': product,
                'quantity': quantity
            }, timeout=5)
            
            if response.status_code == 201:
                successful += 1
            
            # Pequeña pausa entre requests
            time.sleep(0.1)
            
        except Exception as e:
            logger.error(f"Error creating order {i}: {e}")
    
    logger.info(f"Órdenes creadas: {successful}/{count}")
    return successful

def query_inventory_test(count=100):
    """Realiza consultas de inventario de prueba"""
    logger.info(f"Realizando {count} consultas de inventario...")
    
    products = ['PROD-001', 'PROD-002', 'PROD-003']
    successful = 0
    
    for i in range(count):
        try:
            product = random.choice(products)
            
            response = requests.get(f"{VOTER_URL}/inventory/{product}", timeout=5)
            
            if response.status_code == 200:
                successful += 1
            
            # Pequeña pausa entre requests
            time.sleep(0.05)
            
        except Exception as e:
            logger.error(f"Error querying inventory {i}: {e}")
    
    logger.info(f"Consultas exitosas: {successful}/{count}")
    return successful

def generate_load_pattern(duration_minutes=5, base_rps=10):
    """Genera un patrón de carga variable"""
    logger.info(f"Generando patrón de carga por {duration_minutes} minutos...")
    
    start_time = time.time()
    end_time = start_time + (duration_minutes * 60)
    
    orders_created = 0
    queries_made = 0
    
    while time.time() < end_time:
        # Variar la carga con un patrón sinusoidal
        elapsed = time.time() - start_time
        pattern = 0.5 + 0.5 * (1 + (elapsed / 60) * 2 * 3.14159)  # Patrón variable
        
        current_rps = base_rps * pattern
        
        # Crear órdenes (30% de la carga)
        if random.random() < 0.3:
            try:
                product = random.choice(['PROD-001', 'PROD-002', 'PROD-003'])
                quantity = random.randint(1, 5)
                
                response = requests.post(f"{ORDERS_URL}/orders", json={
                    'product_id': product,
                    'quantity': quantity
                }, timeout=5)
                
                if response.status_code == 201:
                    orders_created += 1
                    
            except Exception as e:
                logger.error(f"Error creating order: {e}")
        
        # Consultar inventario (70% de la carga)
        else:
            try:
                product = random.choice(['PROD-001', 'PROD-002', 'PROD-003'])
                
                response = requests.get(f"{VOTER_URL}/inventory/{product}", timeout=5)
                
                if response.status_code == 200:
                    queries_made += 1
                    
            except Exception as e:
                logger.error(f"Error querying inventory: {e}")
        
        # Pausa basada en RPS objetivo
        sleep_time = 1.0 / current_rps if current_rps > 0 else 0.1
        time.sleep(sleep_time)
    
    logger.info(f"Patrón de carga completado: {orders_created} órdenes, {queries_made} consultas")
    return orders_created, queries_made

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Generar datos de prueba para el dashboard')
    parser.add_argument('--orders', type=int, default=50, help='Número de órdenes a crear')
    parser.add_argument('--queries', type=int, default=100, help='Número de consultas a realizar')
    parser.add_argument('--load-pattern', action='store_true', help='Generar patrón de carga variable')
    parser.add_argument('--duration', type=int, default=5, help='Duración del patrón de carga en minutos')
    parser.add_argument('--rps', type=int, default=10, help='RPS base para el patrón de carga')
    
    args = parser.parse_args()
    
    logger.info("Iniciando generación de datos de prueba...")
    
    if args.load_pattern:
        # Generar patrón de carga variable
        generate_load_pattern(args.duration, args.rps)
    else:
        # Generar datos básicos
        create_test_orders(args.orders)
        query_inventory_test(args.queries)
    
    logger.info("Generación de datos completada!")

if __name__ == '__main__':
    main()