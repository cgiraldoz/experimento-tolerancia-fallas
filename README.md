# Experimento de Tolerancia a Fallas

Este proyecto implementa un sistema distribuido con Flask para experimentar con tolerancia a fallas, incluyendo detección automática, votación por mayoría y recuperación de servicios.

## Arquitectura

El sistema está compuesto por los siguientes servicios:

### Servicios Core

- **orders-svc**: API síncrona para crear/cancelar órdenes. Publica eventos a Kafka y registra errores.
- **inventory-svc** (3 réplicas): Consume de Kafka, procesa reservas/liberaciones, expone health checks.
- **monitor-svc**: Realiza health checks periódicos e inspecciona cola de errores. Marca instancias como OFF cuando detecta fallas.
- **voter-svc**: Para consultas de inventario, agrega respuestas de las 3 réplicas y decide por mayoría.
- **dashboard**: Dashboard web para visualizar métricas, fallas y estado del sistema en tiempo real.

### Infraestructura

- **Kafka**: Comunicación asíncrona entre servicios (órdenes → inventario, cola de errores)
- **Postgres**: Estado de instancias, auditoría de fallas, métricas

## Requisitos

- Docker y Docker Compose
- Python 3.11+
- JMeter (opcional, para pruebas de carga)

## Instalación y Ejecución

### 1. Iniciar el sistema completo

```bash
# Construir y levantar todos los servicios
docker-compose up --build

# O en modo detached
docker-compose up --build -d
```

### 2. Verificar que todos los servicios estén funcionando

```bash
# Verificar health checks
curl http://localhost:5006/health  # orders-svc
curl http://localhost:5001/health  # inventory-svc-1
curl http://localhost:5002/health  # inventory-svc-2
curl http://localhost:5003/health  # inventory-svc-3
curl http://localhost:5004/health  # monitor-svc
curl http://localhost:5005/health  # voter-svc
curl http://localhost:5007/health  # dashboard
```

### 3. Verificar estado del sistema

```bash
# Ver estado de todas las instancias
curl http://localhost:5004/status

# Ver métricas del sistema
curl http://localhost:5004/metrics
```

## Uso del Sistema

### Crear una Orden

```bash
curl -X POST http://localhost:5006/orders \
  -H "Content-Type: application/json" \
  -d '{"product_id": "PROD-001", "quantity": 5}'
```

### Consultar Inventario (con votación)

```bash
# Consulta individual
curl http://localhost:5005/inventory/PROD-001

# Consulta de todo el inventario
curl http://localhost:5005/inventory
```

### Cancelar una Orden

```bash
curl -X POST http://localhost:5006/orders/{order_id}/cancel
```

## Experimentos y Pruebas

### Scripts de Inyección de Fallas

```bash
# Inyectar crash en instancia 1
python scripts/inject_failures.py crash --instance 1

# Inyectar latencia de 1200ms en instancia 2
python scripts/inject_failures.py latency --instance 2 --latency 1200

# Inyectar errores intermitentes (50% probabilidad) en instancia 3
python scripts/inject_failures.py intermittent --instance 3 --probability 0.5

# Inyectar respuesta incorrecta para producto específico
python scripts/inject_failures.py incorrect --instance 1 --product PROD-001

# Limpiar todas las fallas
python scripts/inject_failures.py clear --instance 1

# Ver estado actual
python scripts/inject_failures.py status --instance 1

# Ver historial de fallas
python scripts/inject_failures.py failures --instance 1
```

### Pruebas de Carga

```bash
# Prueba de carga básica (50 RPS por 5 minutos)
python scripts/load_test.py query_inventory --rps 50 --duration 300

# Prueba de creación de órdenes
python scripts/load_test.py create_order --rps 30 --duration 180

# Con métricas del sistema
python scripts/load_test.py query_inventory --rps 50 --duration 300 --metrics
```

### Experimento Completo

```bash
# Ejecutar experimento completo automatizado
python scripts/experiment_runner.py
```

Este script ejecuta:
1. Prueba de línea base
2. Inyección de crash failure
3. Inyección de latency failure
4. Inyección de intermittent failure
5. Inyección de incorrect response failure
6. Medición de TTD (Time to Detect) y TTR (Time to Recovery)
7. Generación de reporte

### Pruebas con JMeter

```bash
# Ejecutar plan de pruebas JMeter
cd jmeter
./run_test.sh
```

## Monitoreo y Métricas

### Dashboard Web

**Acceso al Dashboard**: http://localhost:5007

El dashboard proporciona visualización en tiempo real de:
- **Resumen del Sistema**: Estado general, servicios saludables, instancias activas
- **Estado de Servicios**: Health checks en tiempo real de todos los servicios
- **Estado de Instancias**: Monitoreo de las 3 réplicas de inventory-svc
- **Gráficos de Latencia**: Serie temporal de latencias por servicio (P95, P99)
- **Gráficos de Requests**: Requests por minuto por servicio
- **Fallas Detectadas**: Historial y gráficos de fallas por hora
- **Métricas Detalladas**: Tabla con métricas completas por endpoint

### Endpoints de Monitoreo

- `GET /monitor/status` - Estado de todas las instancias
- `GET /monitor/failures` - Historial de fallas detectadas
- `GET /monitor/metrics` - Métricas de rendimiento
- `GET /voter/voting-stats` - Estadísticas de votación

### Métricas Clave

- **TTD (Time to Detect)**: Tiempo desde inyección hasta detección
- **TTR (Time to Recovery)**: Tiempo desde inyección hasta recuperación
- **P95/P99 Latency**: Percentiles de latencia
- **Success Rate**: Tasa de éxito de requests
- **Quorum Achievement**: Frecuencia de logro de quórum en votaciones

## Casos de Fallas Implementados

### 1. Crash Duro
- Mata el proceso de una réplica
- Detectado por health check timeout
- TTD esperado: ~600ms (3 checks × 200ms)

### 2. Latencia Alta
- Sleep aleatorio de 500-1500ms
- Detectado por health check timeout
- TTD esperado: ~600ms

### 3. Respuesta Incorrecta
- Stock manipulado para producto específico
- Detectado por voter-svc (outlier detection)
- TTD esperado: ~300ms (tiempo de votación)

### 4. Errores Intermitentes
- 5xx con probabilidad configurable
- Detectado por health check failures
- TTD esperado: ~600ms

## Configuración

### Variables de Entorno

- `KAFKA_BOOTSTRAP_SERVERS`: Servidores Kafka
- `POSTGRES_URL`: URL de conexión a Postgres
- `SERVICE_NAME`: Nombre del servicio
- `INSTANCE_ID`: ID de la instancia (para inventory-svc)

### Parámetros de Monitoreo

- Health check interval: 200ms
- Health check timeout: 1s
- Consecutive failures threshold: 3
- Recovery threshold: 5

### Parámetros de Votación

- Voting timeout: 300ms
- Quorum size: 2 de 3
- Outlier detection: 2 desviaciones estándar

## Estructura del Proyecto

```
├── docker-compose.yml          # Orquestación de servicios
├── init.sql                    # Esquema de base de datos
├── orders-svc/                 # Servicio de órdenes
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app.py
├── inventory-svc/              # Servicio de inventario
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app.py
├── monitor-svc/                # Servicio de monitoreo
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app.py
├── voter-svc/                  # Servicio de votación
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app.py
├── scripts/                    # Scripts de experimentación
│   ├── inject_failures.py
│   ├── load_test.py
│   └── experiment_runner.py
└── jmeter/                     # Planes de pruebas JMeter
    ├── experiment_test_plan.jmx
    └── run_test.sh
```

## Troubleshooting

### Servicios no inician

```bash
# Ver logs de todos los servicios
docker-compose logs

# Ver logs de un servicio específico
docker-compose logs orders-svc
```

### Kafka no conecta

```bash
# Verificar que Kafka esté funcionando
docker-compose logs kafka

# Verificar conectividad
docker exec -it kafka kafka-topics --bootstrap-server localhost:9092 --list
```

### Base de datos no conecta

```bash
# Verificar Postgres
docker-compose logs postgres

# Conectar a la base de datos
docker exec -it postgres psql -U postgres -d experimento
```

## Resultados Esperados

### Métricas Objetivo

- **TTD**: < 1 segundo para todos los tipos de falla
- **P95 Latency**: < 1 segundo durante fallas
- **Availability**: > 99% durante experimentos
- **Quorum Success**: > 95% durante fallas

### Comportamiento Esperado

1. **Falla Normal**: Sistema continúa funcionando sin degradación
2. **Falla en Réplica**: Monitor detecta y marca OFF, voter continúa con mayoría
3. **Falla Lógica**: Voter detecta outlier y reporta al monitor
4. **Recuperación**: Instancias vuelven a ON después de health checks exitosos

## Contribución

Para contribuir al proyecto:

1. Fork el repositorio
2. Crea una rama para tu feature
3. Implementa los cambios
4. Ejecuta las pruebas
5. Envía un pull request

## Licencia

Este proyecto es para fines educativos y de investigación.