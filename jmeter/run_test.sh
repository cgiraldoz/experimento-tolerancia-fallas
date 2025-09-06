#!/bin/bash

# Script para ejecutar pruebas JMeter
# Requiere que JMeter esté instalado y en el PATH

echo "Iniciando pruebas JMeter para el experimento de tolerancia a fallas..."

# Verificar que JMeter esté instalado
if ! command -v jmeter &> /dev/null; then
    echo "Error: JMeter no está instalado o no está en el PATH"
    echo "Por favor instala JMeter desde: https://jmeter.apache.org/download_jmeter.cgi"
    exit 1
fi

# Crear directorio de resultados si no existe
mkdir -p results

# Ejecutar plan de pruebas
echo "Ejecutando plan de pruebas..."
jmeter -n -t experiment_test_plan.jmx -l results/test_results.jtl -e -o results/html_report

echo "Pruebas completadas!"
echo "Resultados guardados en:"
echo "  - results/test_results.jtl (datos CSV)"
echo "  - results/html_report/ (reporte HTML)"

# Mostrar resumen básico
echo ""
echo "Resumen de resultados:"
if [ -f "results/test_results.jtl" ]; then
    echo "Total de requests: $(wc -l < results/test_results.jtl)"
    echo "Requests exitosos: $(grep -c "true" results/test_results.jtl)"
    echo "Requests fallidos: $(grep -c "false" results/test_results.jtl)"
fi

echo ""
echo "Para ver el reporte HTML completo, abre: results/html_report/index.html"