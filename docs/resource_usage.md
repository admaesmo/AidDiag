# Uso de recursos (CPU/RAM) en pruebas JMeter – AidDiag

## Entorno
- Host estimado: 8 GB RAM, CPU i5.
- Contenedor app: límite ~4 GB.
- JMeter local, Java Temurin 21.

## Observaciones por corrida
- **1/10/100 hilos** (`results/aiddiag_1_10_100.jtl`, `aiddiag_report_1_10_100`):
  - Sin síntomas de agotamiento de recursos. Latencias bajas salvo signin.
  - `/symptoms` POST falla (500) y arrastra `/predict`.
- **Stress 300 hilos** (`results/aiddiag_local_300.jtl`, `aiddiag_report_300`):
  - Latencias >1 s en auth/lecturas. `/symptoms` y `/predict` siguen fallando.
  - No se detectó OOM, pero el contenedor estuvo en estrés alto.
- **Stress alto ~50+400 hilos** (`results/aiddiag_high_clean.jtl`, `aiddiag_report_high`):
  - Errores 54–100% y latencias extremas (p95 >180 s en varios samplers).
  - Indicio de saturación de CPU/RAM; comportamiento degradado.
- **Intento 1000 hilos** (`aiddiag_1000.jtl` fallido):
  - Java no pudo reservar memoria: “El archivo de paginación es demasiado pequeño” / “insufficient memory… G1 virtual space”.
  - No se completó la prueba; requiere más RAM/paginación.

## Cómo medir en futuras corridas
- En otra terminal durante el test:
  - Docker: `docker stats` (memoria/CPU por contenedor).
  - Windows: Monitor de recursos/Administrador de tareas para ver uso total.
- Reducir heap de JMeter si es necesario: `-Xms256m -Xmx1g` en el comando Java, equilibrando para no agotar memoria nativa.
- Ajustar hilos/ramp-up gradualmente hasta ver ~90% de RAM/CPU y registrar métricas.

## Riesgos actuales
- Endpoint `/api/v1/symptoms` POST devuelve 500 en todas las corridas → `/predict` falla en cascada.
- Bajo carga alta, tiempos de respuesta se disparan y la tasa de error sube; la infraestructura local no soporta 1000 hilos con la configuración actual.

## Recomendaciones
- Corregir `/symptoms` POST antes de nuevas mediciones.
- Ejecutar pruebas escalonadas y registrar `docker stats` para correlacionar picos de uso con latencias.
- Para escenarios de >400 hilos, aumentar memoria asignada al host/VM o paginación, o distribuir carga en varias instancias. 
