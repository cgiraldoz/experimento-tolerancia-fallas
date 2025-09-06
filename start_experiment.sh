#!/bin/bash

# Script para iniciar el experimento completo
# Este script automatiza todo el proceso de setup y ejecución

set -e  # Exit on any error

echo "=========================================="
echo "  EXPERIMENTO DE TOLERANCIA A FALLAS"
echo "=========================================="
echo ""

# Función para mostrar ayuda
show_help() {
    echo "Uso: $0 [OPCIÓN]"
    echo ""
    echo "Opciones:"
    echo "  start     Iniciar todos los servicios"
    echo "  stop      Detener todos los servicios"
    echo "  restart   Reiniciar todos los servicios"
    echo "  test      Ejecutar pruebas básicas"
    echo "  experiment Ejecutar experimento completo"
    echo "  clean     Limpiar contenedores y volúmenes"
    echo "  cleanup   Limpiar fallos y reiniciar servicios"
    echo "  logs      Mostrar logs de todos los servicios"
    echo "  status    Mostrar estado de los servicios"
    echo "  help      Mostrar esta ayuda"
    echo ""
}

# Función para verificar dependencias
check_dependencies() {
    echo "Verificando dependencias..."
    
    if ! command -v docker &> /dev/null; then
        echo "❌ Docker no está instalado"
        exit 1
    fi
    
    if ! command -v docker-compose &> /dev/null; then
        echo "❌ Docker Compose no está instalado"
        exit 1
    fi
    
    echo "✅ Dependencias verificadas"
}

# Función para iniciar servicios
start_services() {
    echo "🚀 Iniciando servicios..."
    
    # Construir y levantar servicios
    docker-compose up --build -d
    
    echo "⏳ Esperando a que los servicios estén listos..."
    sleep 30
    
    # Verificar que todos los servicios estén funcionando
    check_services_health
}

# Función para verificar health de servicios
check_services_health() {
    echo "🔍 Verificando health de servicios..."
    
    services=(
        "http://localhost:5006/health:orders-svc"
        "http://localhost:5001/health:inventory-svc-1"
        "http://localhost:5002/health:inventory-svc-2"
        "http://localhost:5003/health:inventory-svc-3"
        "http://localhost:5004/health:monitor-svc"
        "http://localhost:5005/health:voter-svc"
        "http://localhost:5007/health:dashboard"
    )
    
    all_healthy=true
    
    for service in "${services[@]}"; do
        url=$(echo $service | cut -d: -f1-3)
        name=$(echo $service | cut -d: -f4)
        
        if curl -s -f "$url" > /dev/null 2>&1; then
            echo "✅ $name está funcionando"
        else
            echo "❌ $name no está respondiendo"
            all_healthy=false
        fi
    done
    
    if [ "$all_healthy" = true ]; then
        echo "🎉 Todos los servicios están funcionando correctamente"
        return 0
    else
        echo "⚠️  Algunos servicios no están funcionando"
        return 1
    fi
}

# Función para detener servicios
stop_services() {
    echo "🛑 Deteniendo servicios..."
    docker-compose down
    echo "✅ Servicios detenidos"
}

# Función para reiniciar servicios
restart_services() {
    echo "🔄 Reiniciando servicios..."
    stop_services
    sleep 5
    start_services
}

# Función para ejecutar pruebas básicas
run_basic_tests() {
    echo "🧪 Ejecutando pruebas básicas..."
    
    # Verificar que los servicios estén funcionando
    if ! check_services_health; then
        echo "❌ Los servicios no están funcionando correctamente"
        exit 1
    fi
    
    # Crear una orden
    echo "📝 Creando orden de prueba..."
    order_response=$(curl -s -X POST http://localhost:5006/orders \
        -H "Content-Type: application/json" \
        -d '{"product_id": "PROD-001", "quantity": 1}')
    
    if echo "$order_response" | grep -q "order_id"; then
        echo "✅ Orden creada exitosamente"
        order_id=$(echo "$order_response" | grep -o '"order_id":"[^"]*"' | cut -d'"' -f4)
        echo "   Order ID: $order_id"
    else
        echo "❌ Error creando orden"
        echo "   Response: $order_response"
    fi
    
    # Consultar inventario
    echo "📊 Consultando inventario..."
    inventory_response=$(curl -s http://localhost:5005/inventory/PROD-001)
    
    if echo "$inventory_response" | grep -q "available_quantity"; then
        echo "✅ Consulta de inventario exitosa"
        available=$(echo "$inventory_response" | grep -o '"available_quantity":[0-9]*' | cut -d: -f2)
        echo "   Cantidad disponible: $available"
    else
        echo "❌ Error consultando inventario"
        echo "   Response: $inventory_response"
    fi
    
    # Verificar estado del monitor
    echo "📈 Verificando estado del monitor..."
    monitor_response=$(curl -s http://localhost:5004/status)
    
    if echo "$monitor_response" | grep -q "instances"; then
        echo "✅ Monitor funcionando correctamente"
        on_instances=$(echo "$monitor_response" | grep -o '"status":"ON"' | wc -l)
        echo "   Instancias activas: $on_instances"
    else
        echo "❌ Error en monitor"
        echo "   Response: $monitor_response"
    fi
    
    echo "🎉 Pruebas básicas completadas"
}

# Función para ejecutar experimento completo
run_experiment() {
    echo "🔬 Ejecutando experimento completo..."
    
    # Verificar que los servicios estén funcionando
    if ! check_services_health; then
        echo "❌ Los servicios no están funcionando correctamente"
        exit 1
    fi
    
    # Ejecutar experimento
    python scripts/experiment_runner.py
    
    echo "🎉 Experimento completado"
    echo "📊 Revisa el archivo experiment_report_*.json para los resultados"
}

# Función para limpiar
clean_up() {
    echo "🧹 Limpiando contenedores y volúmenes..."
    docker-compose down -v --remove-orphans
    docker system prune -f
    echo "✅ Limpieza completada"
}

# Función para mostrar logs
show_logs() {
    echo "📋 Mostrando logs de todos los servicios..."
    docker-compose logs -f
}

# Función para mostrar estado
show_status() {
    echo "📊 Estado de los servicios:"
    echo ""
    
    # Estado de contenedores
    docker-compose ps
    
    echo ""
    echo "🔍 Health checks:"
    check_services_health
    
    echo ""
    echo "📈 Estado del sistema:"
    curl -s http://localhost:5004/status | python -m json.tool 2>/dev/null || echo "Monitor no disponible"
}

# Función principal
main() {
    case "${1:-help}" in
        start)
            check_dependencies
            start_services
            ;;
        stop)
            stop_services
            ;;
        restart)
            check_dependencies
            restart_services
            ;;
        test)
            run_basic_tests
            ;;
        experiment)
            run_experiment
            ;;
        clean)
            clean_up
            ;;
        cleanup)
            echo "🧹 Limpiando fallos y reiniciando servicios..."
            python scripts/cleanup_experiment.py
            ;;
        logs)
            show_logs
            ;;
        status)
            show_status
            ;;
        help|--help|-h)
            show_help
            ;;
        *)
            echo "❌ Opción no válida: $1"
            echo ""
            show_help
            exit 1
            ;;
    esac
}

# Ejecutar función principal
main "$@"