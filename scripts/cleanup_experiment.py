#!/usr/bin/env python3
"""
Script para limpiar el estado después de un experimento
"""

import subprocess
import time
import requests
import logging

# Configuración de logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def cleanup_experiment():
    """Limpia todos los fallos y reinicia servicios detenidos"""
    logger.info("🧹 Starting experiment cleanup...")
    
    # Lista de instancias que pueden haber tenido fallos
    instances = ['1', '2', '3']
    
    # 1. Intentar limpiar fallos en servicios que estén corriendo
    logger.info("1️⃣ Clearing injected failures...")
    for instance_id in instances:
        try:
            cmd = ['python', 'scripts/inject_failures.py', 'clear', '--instance', instance_id]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            
            if result.returncode == 0:
                logger.info(f"   ✅ Cleared failures in inventory-svc-{instance_id}")
            else:
                logger.warning(f"   ⚠️ Could not clear failures in inventory-svc-{instance_id}: {result.stderr}")
                
        except subprocess.TimeoutExpired:
            logger.warning(f"   ⚠️ Timeout clearing failures in inventory-svc-{instance_id}")
        except Exception as e:
            logger.warning(f"   ⚠️ Error clearing failures in inventory-svc-{instance_id}: {e}")
    
    # 2. Reiniciar todos los servicios
    logger.info("2️⃣ Restarting all services...")
    try:
        result = subprocess.run(['docker-compose', 'restart'], 
                              capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            logger.info("   ✅ All services restarted successfully")
        else:
            logger.warning(f"   ⚠️ Error restarting services: {result.stderr}")
    except Exception as e:
        logger.warning(f"   ⚠️ Error restarting services: {e}")
    
    # 3. Esperar a que los servicios estén listos
    logger.info("3️⃣ Waiting for services to be ready...")
    time.sleep(15)
    
    # 4. Verificar estado final
    logger.info("4️⃣ Verifying final state...")
    try:
        response = requests.get('http://localhost:5007/api/health', timeout=10)
        if response.status_code == 200:
            data = response.json()
            healthy_count = sum(1 for s in data.values() if s['status'] == 'UP')
            total_count = len(data)
            logger.info(f"   📊 Services status: {healthy_count}/{total_count} UP")
            
            # Mostrar estado de cada servicio
            for service, status in data.items():
                status_icon = "✅" if status['status'] == 'UP' else "❌"
                logger.info(f"   {status_icon} {service}: {status['status']} - {status['response_time']}ms")
        else:
            logger.error(f"   ❌ Could not check service status: HTTP {response.status_code}")
    except Exception as e:
        logger.error(f"   ❌ Error checking service status: {e}")
    
    logger.info("🎉 Experiment cleanup completed!")

if __name__ == "__main__":
    cleanup_experiment()