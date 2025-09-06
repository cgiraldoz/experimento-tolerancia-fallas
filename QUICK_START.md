# Guía de Inicio Rápido

## 🚀 Inicio en 3 Pasos

### 1. Iniciar el Sistema

```bash
# Opción A: Script automatizado (recomendado)
./start_experiment.sh start

# Opción B: Manual
docker-compose up --build -d
```

### 2. Verificar que Todo Funciona

```bash
# Verificar servicios
./start_experiment.sh status

# O ejecutar pruebas básicas
./start_experiment.sh test
```

### 3. Ejecutar Experimento

```bash
# Experimento completo automatizado
./start_experiment.sh experiment

# O pruebas manuales
python scripts/inject_failures.py crash --instance 1
python scripts/load_test.py query_inventory --rps 50 --duration 60
```

## 📋 Comandos Útiles

```bash
# Ver estado de servicios
./start_experiment.sh status

# Ver logs en tiempo real
./start_experiment.sh logs

# Detener todo
./start_experiment.sh stop

# Limpiar completamente
./start_experiment.sh clean
```

## 🧪 Pruebas Rápidas

### Crear una Orden
```bash
curl -X POST http://localhost:5006/orders \
  -H "Content-Type: application/json" \
  -d '{"product_id": "PROD-001", "quantity": 5}'
```

### Consultar Inventario
```bash
curl http://localhost:5005/inventory/PROD-001
```

### Ver Estado del Sistema
```bash
curl http://localhost:5004/status
```

## 🔧 Inyección de Fallas

```bash
# Crash en instancia 1
python scripts/inject_failures.py crash --instance 1

# Latencia alta en instancia 2
python scripts/inject_failures.py latency --instance 2 --latency 1200

# Errores intermitentes en instancia 3
python scripts/inject_failures.py intermittent --instance 3 --probability 0.5

# Limpiar fallas
python scripts/inject_failures.py clear --instance 1
```

## 📊 Monitoreo

- **Estado de servicios**: http://localhost:5004/status
- **Métricas**: http://localhost:5004/metrics
- **Fallas**: http://localhost:5004/failures
- **Estadísticas de votación**: http://localhost:5005/voting-stats

## 🆘 Troubleshooting

### Servicios no inician
```bash
# Ver logs
./start_experiment.sh logs

# Reiniciar
./start_experiment.sh restart
```

### Puerto ocupado
```bash
# Ver qué está usando el puerto
lsof -i :5000

# Cambiar puertos en docker-compose.yml si es necesario
```

### Base de datos no conecta
```bash
# Verificar Postgres
docker-compose logs postgres

# Reiniciar solo la base de datos
docker-compose restart postgres
```

## 📈 Resultados Esperados

- **TTD (Time to Detect)**: < 1 segundo
- **P95 Latency**: < 1 segundo durante fallas
- **Success Rate**: > 95% durante experimentos
- **Quorum Achievement**: > 95% durante fallas

## 🎯 Próximos Pasos

1. Ejecutar experimento completo: `./start_experiment.sh experiment`
2. Revisar reporte generado: `experiment_report_*.json`
3. Analizar métricas en: http://localhost:5004/metrics
4. Ejecutar pruebas JMeter: `cd jmeter && ./run_test.sh`