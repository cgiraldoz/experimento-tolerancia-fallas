#!/usr/bin/env python3
"""
Script simple para probar los servicios
"""

import requests
import time

def test_service(name, url):
    try:
        print(f"Probando {name} en {url}...")
        response = requests.get(url, timeout=5)
        print(f"  Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"  Response: {data}")
            return True
        else:
            print(f"  Error: {response.text}")
            return False
    except Exception as e:
        print(f"  Error: {e}")
        return False

def main():
    services = [
        ("orders-svc", "http://localhost:5006/health"),
        ("inventory-svc-1", "http://localhost:5001/health"),
        ("inventory-svc-2", "http://localhost:5002/health"),
        ("inventory-svc-3", "http://localhost:5003/health"),
        ("monitor-svc", "http://localhost:5004/health"),
        ("voter-svc", "http://localhost:5005/health"),
    ]
    
    print("=== Probando servicios ===")
    successful = 0
    
    for name, url in services:
        if test_service(name, url):
            successful += 1
        print()
    
    print(f"Servicios funcionando: {successful}/{len(services)}")
    
    if successful == len(services):
        print("🎉 Todos los servicios están funcionando!")
        
        # Probar funcionalidad básica
        print("\n=== Probando funcionalidad ===")
        
        # Crear una orden
        try:
            print("Creando orden...")
            order_response = requests.post(
                "http://localhost:5006/orders",
                json={"product_id": "PROD-001", "quantity": 1},
                timeout=5
            )
            if order_response.status_code == 201:
                order_data = order_response.json()
                print(f"✅ Orden creada: {order_data['order_id']}")
            else:
                print(f"❌ Error creando orden: {order_response.status_code}")
        except Exception as e:
            print(f"❌ Error creando orden: {e}")
        
        # Consultar inventario
        try:
            print("Consultando inventario...")
            inventory_response = requests.get(
                "http://localhost:5005/inventory/PROD-001",
                timeout=5
            )
            if inventory_response.status_code == 200:
                inventory_data = inventory_response.json()
                print(f"✅ Inventario consultado: {inventory_data}")
            else:
                print(f"❌ Error consultando inventario: {inventory_response.status_code}")
        except Exception as e:
            print(f"❌ Error consultando inventario: {e}")
        
        # Ver estado del monitor
        try:
            print("Verificando estado del monitor...")
            status_response = requests.get(
                "http://localhost:5004/status",
                timeout=5
            )
            if status_response.status_code == 200:
                status_data = status_response.json()
                instances = status_data.get('instances', [])
                on_instances = [i for i in instances if i.get('status') == 'ON']
                print(f"✅ Monitor funcionando: {len(on_instances)}/{len(instances)} instancias activas")
            else:
                print(f"❌ Error verificando monitor: {status_response.status_code}")
        except Exception as e:
            print(f"❌ Error verificando monitor: {e}")
    
    else:
        print("⚠️  Algunos servicios no están funcionando correctamente")

if __name__ == "__main__":
    main()