# 📚 Guía de Estudio - Experimento de Tolerancia a Fallas en Sistemas Distribuidos

## 📋 Tabla de Contenidos

1. [Introducción y Objetivos](#introducción-y-objetivos)
2. [Arquitectura del Sistema](#arquitectura-del-sistema)
3. [Nomenclatura y Glosario](#nomenclatura-y-glosario)
4. [Funcionamiento del Código](#funcionamiento-del-código)
5. [Flujo del Experimento](#flujo-del-experimento)
6. [Interpretación de Reportes](#interpretación-de-reportes)
7. [Preguntas de Estudio](#preguntas-de-estudio)
8. [Preguntas y Respuestas Frecuentes](#preguntas-y-respuestas-frecuentes)
9. [Casos de Uso y Escenarios](#casos-de-uso-y-escenarios)
10. [Troubleshooting](#troubleshooting)

---

## 🎯 Introducción y Objetivos

### **¿Qué es este experimento?**

Este experimento implementa un **sistema distribuido tolerante a fallas** que simula un e-commerce con múltiples servicios que deben funcionar de manera coordinada y resiliente.

### **Objetivos Principales**

1. **Demostrar tolerancia a fallas** en sistemas distribuidos
2. **Medir TTD (Time to Detect)** y **TTR (Time to Recovery)**
3. **Evaluar mecanismos de votación** por mayoría
4. **Probar diferentes tipos de fallos** (crash, latency, intermittent, incorrect)
5. **Validar la detección de outliers** en respuestas

### **Tecnologías Utilizadas**

- **Flask**: Microservicios web
- **Kafka**: Mensajería asíncrona
- **PostgreSQL**: Persistencia de datos
- **Docker**: Containerización
- **Plotly**: Visualización de métricas

---

## 🏗️ Arquitectura del Sistema

### **Diagrama de Arquitectura**

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   orders-svc    │    │ inventory-svc-1 │    │ inventory-svc-2 │
│   (Puerto 5006) │    │   (Puerto 5001) │    │   (Puerto 5002) │
└─────────┬───────┘    └─────────┬───────┘    └─────────┬───────┘
          │                      │                      │
          │                      │                      │
          ▼                      ▼                      ▼
    ┌─────────────────────────────────────────────────────────┐
    │                    Kafka Cluster                       │
    │              (order-events, error-queue)               │
    └─────────────────────────────────────────────────────────┘
          │                      │                      │
          │                      │                      │
          ▼                      ▼                      ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   monitor-svc   │    │ inventory-svc-3 │    │   voter-svc     │
│   (Puerto 5004) │    │   (Puerto 5003) │    │   (Puerto 5005) │
└─────────┬───────┘    └─────────────────┘    └─────────────────┘
          │
          ▼
┌─────────────────┐
│    dashboard    │
│   (Puerto 5007) │
└─────────────────┘
          │
          ▼
┌─────────────────┐
│   PostgreSQL    │
│   (Puerto 5432) │
└─────────────────┘
```

### **Servicios y Responsabilidades**

#### **1. orders-svc (Puerto 5006)**
- **Función**: API síncrona para crear/cancelar órdenes
- **Endpoints**: 
  - `POST /orders` - Crear orden
  - `DELETE /orders/<id>` - Cancelar orden
  - `GET /health` - Health check
- **Comunicación**: Publica eventos a Kafka

#### **2. inventory-svc (3 réplicas)**
- **Función**: Gestión de inventario con tolerancia a fallas
- **Puertos**: 5001, 5002, 5003
- **Endpoints**:
  - `GET /inventory` - Consultar inventario
  - `GET /health` - Health check
  - `POST /inject-failure` - Inyectar fallos
- **Características**: 3 réplicas para votación por mayoría

#### **3. monitor-svc (Puerto 5004)**
- **Función**: Monitoreo y detección de fallos
- **Responsabilidades**:
  - Health checks cada 200ms
  - Detección de fallos (3 fallos consecutivos)
  - Actualización de estado en BD
  - Consumo de cola de errores

#### **4. voter-svc (Puerto 5005)**
- **Función**: Agregación por mayoría y detección de outliers
- **Endpoints**:
  - `GET /inventory/voted` - Inventario por votación
  - `GET /voting/stats` - Estadísticas de votación
- **Algoritmo**: Mayoría (2 de 3) + detección de outliers

#### **5. dashboard (Puerto 5007)**
- **Función**: Visualización de métricas y reportes
- **Características**:
  - Métricas en tiempo real
  - Gráficos interactivos
  - Reportes de experimentos
  - Auto-refresh cada 30 segundos

---

## 📖 Nomenclatura y Glosario

### **Términos Técnicos**

| Término | Definición | Ejemplo |
|---------|------------|---------|
| **TTD** | Time to Detect - Tiempo de detección de fallos | 600ms |
| **TTR** | Time to Recovery - Tiempo de recuperación | 200ms |
| **Health Check** | Verificación periódica del estado de un servicio | Cada 200ms |
| **Quorum** | Número mínimo de respuestas para tomar decisión | 2 de 3 |
| **Outlier** | Respuesta que se desvía significativamente del patrón | Latencia > 2σ |
| **Fan-out** | Número de instancias consultadas | 3 instancias |
| **Crash** | Fallo que termina completamente el proceso | `os._exit(1)` |
| **Latency** | Delay artificial en las respuestas | 1200ms |
| **Intermittent** | Fallo que ocurre con cierta probabilidad | 30% probabilidad |
| **Incorrect Response** | Respuesta con datos incorrectos | Producto inexistente |

### **Métricas del Sistema**

| Métrica | Descripción | Unidad |
|---------|-------------|--------|
| **Response Time** | Tiempo de respuesta de un endpoint | ms |
| **P95 Latency** | Percentil 95 de latencia | ms |
| **P99 Latency** | Percentil 99 de latencia | ms |
| **Request Count** | Número de requests procesados | count |
| **Success Rate** | Porcentaje de requests exitosos | % |
| **Availability** | Porcentaje de tiempo disponible | % |
| **Fan-out** | Número de instancias consultadas | count |
| **Quorum** | Número de respuestas válidas | count |
| **Excluded Replicas** | Instancias excluidas por outlier | count |

### **Estados de Instancias**

| Estado | Descripción | Condición |
|--------|-------------|-----------|
| **ON** | Instancia funcionando correctamente | Health check OK |
| **OFF** | Instancia no disponible | 3 fallos consecutivos |
| **UNKNOWN** | Estado no determinado | Sin health checks recientes |

---

## 💻 Funcionamiento del Código

### **Estructura de Archivos**

```
experimento-test/
├── docker-compose.yml          # Orquestación de servicios
├── init.sql                    # Esquema de base de datos
├── start_experiment.sh         # Script principal de control
├── orders-svc/
│   ├── app.py                  # API de órdenes
│   ├── requirements.txt        # Dependencias
│   └── Dockerfile             # Imagen Docker
├── inventory-svc/
│   ├── app.py                  # API de inventario
│   ├── requirements.txt        # Dependencias
│   └── Dockerfile             # Imagen Docker
├── monitor-svc/
│   ├── app.py                  # Servicio de monitoreo
│   ├── requirements.txt        # Dependencias
│   └── Dockerfile             # Imagen Docker
├── voter-svc/
│   ├── app.py                  # Servicio de votación
│   ├── requirements.txt        # Dependencias
│   └── Dockerfile             # Imagen Docker
├── dashboard/
│   ├── app.py                  # Dashboard web
│   ├── templates/              # Plantillas HTML
│   ├── requirements.txt        # Dependencias
│   └── Dockerfile             # Imagen Docker
├── scripts/
│   ├── experiment_runner.py    # Ejecutor de experimentos
│   ├── inject_failures.py      # Inyección de fallos
│   ├── load_test.py           # Pruebas de carga
│   ├── generate_test_data.py   # Generación de datos
│   └── cleanup_experiment.py   # Limpieza post-experimento
└── jmeter/
    ├── experiment_test_plan.jmx # Plan de pruebas JMeter
    └── run_test.sh             # Ejecutor JMeter
```

### **Flujo de Datos**

#### **1. Creación de Orden**
```python
# orders-svc/app.py
@app.route('/orders', methods=['POST'])
def create_order():
    # 1. Validar datos
    # 2. Publicar evento a Kafka
    # 3. Registrar métricas
    # 4. Retornar respuesta
```

#### **2. Procesamiento de Inventario**
```python
# inventory-svc/app.py
def process_order_event():
    # 1. Consumir evento de Kafka
    # 2. Verificar fallos inyectados
    # 3. Procesar inventario
    # 4. Registrar métricas
```

#### **3. Monitoreo de Salud**
```python
# monitor-svc/app.py
def health_check_worker():
    # 1. Hacer health check cada 200ms
    # 2. Contar fallos consecutivos
    # 3. Actualizar estado en BD
    # 4. Detectar recuperación
```

#### **4. Votación por Mayoría**
```python
# voter-svc/app.py
def aggregate_responses():
    # 1. Consultar todas las instancias
    # 2. Detectar outliers
    # 3. Aplicar votación por mayoría
    # 4. Retornar resultado consensuado
```

### **Inyección de Fallos**

#### **Tipos de Fallos Implementados**

```python
# inventory-svc/app.py
def check_failure_injection():
    if FAILURE_TYPE == 'crash':
        os._exit(1)  # Termina el proceso
        
    elif FAILURE_TYPE == 'latency':
        time.sleep(LATENCY_MS / 1000.0)  # Delay artificial
        
    elif FAILURE_TYPE == 'intermittent':
        if random.random() < FAILURE_PROBABILITY:
            raise Exception("Intermittent error")
            
    elif FAILURE_TYPE == 'incorrect_response':
        # Retorna datos incorrectos
        return incorrect_data
```

#### **Comando de Inyección**
```bash
# Inyectar fallo crash en instancia 1
python scripts/inject_failures.py crash --instance 1

# Inyectar fallo de latencia en instancia 2
python scripts/inject_failures.py latency --instance 2 --latency_ms 1200

# Inyectar fallo intermitente en instancia 3
python scripts/inject_failures.py intermittent --instance 3 --probability 0.3

# Limpiar todos los fallos
python scripts/inject_failures.py clear --instance 1
```

---

## 🔄 Flujo del Experimento

### **Fases del Experimento**

#### **Fase 1: Baseline (Línea Base)**
```python
# Medir rendimiento sin fallos
baseline_result = self.run_baseline_test()
```

**Objetivo**: Establecer métricas de referencia
**Duración**: ~2 minutos
**Métricas**: Latencia, throughput, success rate

#### **Fase 2: Crash Failure**
```python
crash_result = self.inject_failure_and_measure('crash', '1')
```

**Objetivo**: Medir TTD/TTR de fallos catastróficos
**Fallo**: `os._exit(1)` - Contenedor se detiene
**TTD Esperado**: ~600ms
**TTR**: Requiere reinicio manual

#### **Fase 3: Latency Failure**
```python
latency_result = self.inject_failure_and_measure('latency', '2', latency_ms=1200)
```

**Objetivo**: Medir impacto de latencia alta
**Fallo**: Delay artificial de 1200ms
**TTD Esperado**: ~600ms
**TTR Esperado**: ~200ms

#### **Fase 4: Intermittent Failure**
```python
intermittent_result = self.inject_failure_and_measure('intermittent', '3', probability=0.3)
```

**Objetivo**: Medir resiliencia a fallos impredecibles
**Fallo**: 30% probabilidad de error
**TTD**: Variable (depende de la frecuencia)
**TTR Esperado**: ~200ms

#### **Fase 5: Incorrect Response**
```python
incorrect_result = self.inject_failure_and_measure('incorrect', '1', product_id='PROD-001')
```

**Objetivo**: Medir detección de respuestas incorrectas
**Fallo**: Retorna datos incorrectos
**TTD Esperado**: ~600ms
**TTR Esperado**: ~200ms

### **Medición de TTD/TTR**

#### **Time to Detect (TTD)**
```python
def measure_detection_time(self, instance_id):
    start_time = time.time()
    while time.time() - start_time < timeout:
        # Consultar estado en monitor-svc
        response = requests.get('http://localhost:5004/status')
        # Buscar instancia con status 'OFF'
        if instance['status'] == 'OFF':
            return time.time() - start_time
```

#### **Time to Recovery (TTR)**
```python
def measure_recovery_time(self, instance_id):
    # 1. Limpiar fallo
    subprocess.run(['python', 'scripts/inject_failures.py', 'clear', '--instance', instance_id])
    
    # 2. Medir tiempo hasta recuperación
    while time.time() - start_time < timeout:
        # Buscar instancia con status 'ON'
        if instance['status'] == 'ON':
            return time.time() - start_time
```

---

## 📊 Interpretación de Reportes

### **Estructura del Reporte JSON**

```json
{
  "experiment_info": {
    "start_time": "2025-09-06T14:20:24.722000",
    "end_time": "2025-09-06T14:35:42.156000",
    "total_duration_seconds": 917.434
  },
  "results": [
    {
      "phase": "baseline",
      "ttd_ms": null,
      "ttr_ms": null,
      "load_test_result": {
        "rps": 45.2,
        "avg_latency_ms": 89.3,
        "p95_latency_ms": 156.7,
        "p99_latency_ms": 234.1,
        "success_rate": 99.8
      }
    },
    {
      "phase": "crash",
      "ttd_ms": 623.4,
      "ttr_ms": null,
      "load_test_result": {
        "rps": 38.1,
        "avg_latency_ms": 145.2,
        "p95_latency_ms": 289.3,
        "p99_latency_ms": 456.7,
        "success_rate": 95.2
      }
    }
  ],
  "summary": {
    "total_tests": 5,
    "successful_tests": 5,
    "avg_ttd_ms": 587.2,
    "avg_ttr_ms": 198.4,
    "max_p95_ms": 289.3,
    "min_success_rate": 95.2
  }
}
```

### **Interpretación de Métricas**

#### **TTD (Time to Detect)**
- **Valor Óptimo**: < 1000ms
- **Valor Aceptable**: < 2000ms
- **Valor Crítico**: > 5000ms

#### **TTR (Time to Recovery)**
- **Valor Óptimo**: < 500ms
- **Valor Aceptable**: < 1000ms
- **Valor Crítico**: > 2000ms

#### **Success Rate**
- **Valor Óptimo**: > 99%
- **Valor Aceptable**: > 95%
- **Valor Crítico**: < 90%

#### **P95 Latency**
- **Valor Óptimo**: < 200ms
- **Valor Aceptable**: < 500ms
- **Valor Crítico**: > 1000ms

### **Dashboard - Interpretación de Gráficos**

#### **1. Gráfico de Latencia**
- **Eje X**: Tiempo
- **Eje Y**: Latencia en ms
- **Líneas**: Diferentes servicios
- **Interpretación**: Picos indican fallos o sobrecarga

#### **2. Gráfico de Requests**
- **Eje X**: Tiempo
- **Eje Y**: Requests por segundo
- **Interpretación**: Caídas indican fallos de servicios

#### **3. Gráfico de Fallos**
- **Eje X**: Tiempo
- **Eje Y**: Número de fallos
- **Interpretación**: Picos indican detección de fallos

#### **4. Métricas Detalladas**
- **Tabla**: Métricas por servicio y endpoint
- **Columnas**: Servicio, Endpoint, Método, Status, Requests, Latencia
- **Interpretación**: Identificar servicios problemáticos

---

## 📚 Preguntas de Estudio

### **Nivel Básico**

1. **¿Qué es TTD y TTR?**
   - TTD: Tiempo de detección de fallos
   - TTR: Tiempo de recuperación de fallos

2. **¿Cuántas réplicas de inventory-svc hay?**
   - 3 réplicas (inventory-svc-1, inventory-svc-2, inventory-svc-3)

3. **¿Qué puerto usa orders-svc?**
   - Puerto 5006

4. **¿Cuál es el umbral de fallos consecutivos para marcar una instancia como OFF?**
   - 3 fallos consecutivos

5. **¿Con qué frecuencia hace health checks el monitor-svc?**
   - Cada 200ms

### **Nivel Intermedio**

6. **¿Cómo funciona la votación por mayoría?**
   - Se consultan las 3 instancias
   - Se detectan outliers
   - Se toma la decisión por mayoría (2 de 3)

7. **¿Qué tipos de fallos se pueden inyectar?**
   - Crash: Termina el proceso
   - Latency: Delay artificial
   - Intermittent: Probabilidad de fallo
   - Incorrect: Respuesta incorrecta

8. **¿Cómo se detecta un outlier?**
   - Usando desviación estándar (2σ)
   - Comparando con la media de respuestas

9. **¿Qué hace el voter-svc?**
   - Agrega respuestas por mayoría
   - Detecta outliers
   - Proporciona inventario consensuado

10. **¿Cómo se mide el TTD?**
    - Desde inyección del fallo hasta detección por monitor-svc

### **Nivel Avanzado**

11. **¿Por qué se usa Kafka en este experimento?**
    - Desacoplamiento de servicios
    - Mensajería asíncrona
    - Cola de errores
    - Escalabilidad

12. **¿Cómo se calculan los percentiles P95 y P99?**
    - P95: 95% de las respuestas están por debajo de este valor
    - P99: 99% de las respuestas están por debajo de este valor

13. **¿Qué pasa si 2 de 3 instancias fallan?**
    - El sistema no puede tomar decisión por mayoría
    - Se marca como fallo del sistema
    - Se requiere intervención manual

14. **¿Cómo se maneja la consistencia de datos?**
    - Eventual consistency
    - Votación por mayoría
    - Detección de outliers

15. **¿Qué métricas se almacenan en PostgreSQL?**
    - Estado de instancias
    - Métricas de requests
    - Eventos de fallos
    - Eventos de votación

---

## ❓ Preguntas y Respuestas Frecuentes

### **P: ¿Por qué inventory-svc-1 siempre queda en failed al final?**
**R:** Porque el experimento inyecta fallos `crash` y `incorrect` en la instancia 1, y el fallo `crash` termina completamente el contenedor. El experimento ahora incluye limpieza automática al final.

### **P: ¿Cómo interpreto un TTD de 600ms?**
**R:** Significa que el sistema tardó 600ms en detectar el fallo. Esto es bueno porque está por debajo del umbral de 1000ms.

### **P: ¿Qué significa un success rate del 95%?**
**R:** Significa que 95 de cada 100 requests fueron exitosos. Esto puede indicar fallos intermitentes o problemas de red.

### **P: ¿Por qué el dashboard muestra 0/6 servicios saludables?**
**R:** Probablemente hay un problema de conectividad entre contenedores. Verificar que todos los servicios estén corriendo con `docker ps`.

### **P: ¿Cómo sé si el experimento fue exitoso?**
**R:** Revisar el reporte JSON generado. Un experimento exitoso debe tener:
- TTD < 1000ms
- TTR < 500ms (excepto crash)
- Success rate > 95%
- Todos los tests completados

### **P: ¿Qué hacer si un servicio no responde?**
**R:** 
1. Verificar con `docker ps`
2. Revisar logs con `docker logs <service-name>`
3. Reiniciar con `docker restart <service-name>`
4. Usar script de limpieza: `./start_experiment.sh cleanup`

### **P: ¿Cómo generar más datos para el dashboard?**
**R:** Ejecutar `python scripts/generate_test_data.py` para generar tráfico artificial.

### **P: ¿Qué significa "quorum not reached" en el voter-svc?**
**R:** Significa que no se pudo obtener mayoría (2 de 3) de respuestas válidas. Esto puede indicar que múltiples instancias están fallando.

---

## 🎯 Casos de Uso y Escenarios

### **Escenario 1: Fallo de una Instancia**
```
Situación: inventory-svc-1 falla
Resultado Esperado:
- TTD: ~600ms
- Sistema continúa funcionando con 2 instancias
- Votación por mayoría funciona
- TTR: ~200ms después de limpiar fallo
```

### **Escenario 2: Fallo de Dos Instancias**
```
Situación: inventory-svc-1 y inventory-svc-2 fallan
Resultado Esperado:
- TTD: ~600ms para ambas
- Sistema no puede tomar decisión por mayoría
- Voter-svc reporta "quorum not reached"
- Requiere intervención manual
```

### **Escenario 3: Fallo Intermitente**
```
Situación: inventory-svc-3 con 30% probabilidad de fallo
Resultado Esperado:
- Success rate: ~70%
- TTD: Variable
- Sistema detecta outliers
- TTR: ~200ms
```

### **Escenario 4: Latencia Alta**
```
Situación: inventory-svc-2 con 1200ms de latencia
Resultado Esperado:
- P95 latency: ~1200ms
- TTD: ~600ms
- Sistema detecta instancia lenta
- TTR: ~200ms
```

---

## 🔧 Troubleshooting

### **Problemas Comunes**

#### **1. Servicios no inician**
```bash
# Verificar estado
docker ps

# Ver logs
docker logs <service-name>

# Reiniciar todo
./start_experiment.sh restart
```

#### **2. Dashboard no muestra datos**
```bash
# Verificar conectividad
curl http://localhost:5007/health

# Verificar base de datos
docker exec -it postgres psql -U postgres -d experimento -c "SELECT COUNT(*) FROM request_metrics;"
```

#### **3. Experimentos fallan**
```bash
# Limpiar estado
./start_experiment.sh cleanup

# Verificar servicios
./start_experiment.sh status

# Reintentar experimento
./start_experiment.sh experiment
```

#### **4. Puerto en uso**
```bash
# Verificar puertos
lsof -i :5006

# Cambiar puerto en docker-compose.yml
# Reiniciar servicios
```

### **Comandos de Diagnóstico**

```bash
# Estado de servicios
./start_experiment.sh status

# Logs de todos los servicios
./start_experiment.sh logs

# Limpiar y reiniciar
./start_experiment.sh cleanup

# Verificar conectividad
curl http://localhost:5006/health  # orders-svc
curl http://localhost:5001/health  # inventory-svc-1
curl http://localhost:5002/health  # inventory-svc-2
curl http://localhost:5003/health  # inventory-svc-3
curl http://localhost:5004/health  # monitor-svc
curl http://localhost:5005/health  # voter-svc
curl http://localhost:5007/health  # dashboard
```

### **Verificación de Base de Datos**

```sql
-- Ver estado de instancias
SELECT * FROM instance_status ORDER BY service_name, instance_id;

-- Ver métricas de requests
SELECT service_name, endpoint, COUNT(*) as requests, AVG(latency_ms) as avg_latency
FROM request_metrics 
WHERE timestamp >= NOW() - INTERVAL '1 hour'
GROUP BY service_name, endpoint;

-- Ver fallos detectados
SELECT * FROM failure_audit 
WHERE detected_at >= NOW() - INTERVAL '1 hour'
ORDER BY detected_at DESC;

-- Ver eventos de votación
SELECT * FROM voting_events 
WHERE timestamp >= NOW() - INTERVAL '1 hour'
ORDER BY timestamp DESC;
```

---

## 📈 Métricas y KPIs

### **Métricas de Rendimiento**

| Métrica | Descripción | Valor Óptimo | Valor Crítico |
|---------|-------------|--------------|---------------|
| **TTD** | Tiempo de detección | < 1000ms | > 5000ms |
| **TTR** | Tiempo de recuperación | < 500ms | > 2000ms |
| **Availability** | Disponibilidad | > 99.9% | < 95% |
| **Success Rate** | Tasa de éxito | > 99% | < 90% |
| **P95 Latency** | Latencia percentil 95 | < 200ms | > 1000ms |
| **Throughput** | Requests por segundo | > 100 RPS | < 10 RPS |

### **Métricas de Tolerancia a Fallas**

| Métrica | Descripción | Valor Óptimo |
|---------|-------------|--------------|
| **Quorum Success** | Éxito en votación | > 95% |
| **Outlier Detection** | Detección de outliers | > 90% |
| **Failure Coverage** | Cobertura de tipos de fallo | 100% |
| **Recovery Success** | Éxito en recuperación | > 95% |

---

## 🎓 Guía de Presentación

### **Estructura Recomendada para Sustentar**

#### **1. Introducción (5 minutos)**
- Objetivo del experimento
- Arquitectura del sistema
- Tecnologías utilizadas

#### **2. Demostración en Vivo (10 minutos)**
- Mostrar dashboard funcionando
- Ejecutar un experimento pequeño
- Explicar métricas en tiempo real

#### **3. Análisis de Resultados (10 minutos)**
- Interpretar reportes generados
- Explicar TTD/TTR
- Mostrar gráficos y métricas

#### **4. Preguntas y Respuestas (5 minutos)**
- Responder preguntas técnicas
- Explicar decisiones de diseño
- Discutir mejoras posibles

### **Puntos Clave a Destacar**

1. **Tolerancia a Fallas**: Sistema continúa funcionando con fallos
2. **Detección Rápida**: TTD < 1000ms
3. **Recuperación Rápida**: TTR < 500ms
4. **Votación por Mayoría**: Consenso entre réplicas
5. **Detección de Outliers**: Identificación de respuestas anómalas
6. **Monitoreo en Tiempo Real**: Dashboard con métricas actualizadas

### **Preparación para Preguntas**

- **Conocer los números**: TTD, TTR, percentiles, success rates
- **Entender la arquitectura**: Flujo de datos, comunicación entre servicios
- **Saber interpretar métricas**: Qué significa cada valor
- **Conocer limitaciones**: Qué pasa con 2 de 3 fallos
- **Tener ejemplos**: Casos de uso reales

---

## 📚 Recursos Adicionales

### **Documentación Técnica**
- [Flask Documentation](https://flask.palletsprojects.com/)
- [Kafka Documentation](https://kafka.apache.org/documentation/)
- [PostgreSQL Documentation](https://www.postgresql.org/docs/)
- [Docker Documentation](https://docs.docker.com/)

### **Conceptos de Sistemas Distribuidos**
- Tolerancia a Fallas
- Consenso y Votación
- Monitoreo y Observabilidad
- Patrones de Microservicios

### **Herramientas de Monitoreo**
- Prometheus + Grafana
- ELK Stack (Elasticsearch, Logstash, Kibana)
- Jaeger (Tracing distribuido)
- Zipkin (Tracing distribuido)

---

## ✅ Checklist de Preparación

### **Antes de la Presentación**

- [ ] Todos los servicios funcionando
- [ ] Dashboard accesible
- [ ] Datos de ejemplo generados
- [ ] Reportes de experimentos disponibles
- [ ] Comandos de demostración preparados
- [ ] Preguntas frecuentes revisadas
- [ ] Backup de datos importante

### **Durante la Presentación**

- [ ] Mostrar dashboard en tiempo real
- [ ] Ejecutar experimento en vivo
- [ ] Explicar métricas paso a paso
- [ ] Responder preguntas con ejemplos
- [ ] Demostrar troubleshooting si es necesario

### **Después de la Presentación**

- [ ] Limpiar estado del sistema
- [ ] Documentar preguntas no respondidas
- [ ] Recopilar feedback
- [ ] Planificar mejoras

---

**¡Buena suerte con tu presentación! 🚀**

*Esta guía cubre todos los aspectos necesarios para sustentar el experimento de manera exitosa. Recuerda practicar la demostración y estar preparado para preguntas técnicas detalladas.*