# Plan de Pruebas de Carga (JMeter) - AidDiag

## Objetivo
Validar el comportamiento bajo carga de los endpoints críticos de AidDiag en un entorno local limitado (8 GB RAM host, contenedor app ~4 GB, CPU i5), usando un plan escalonado hasta 100 hilos.

## Alcance
Se cubren los flujos principales de autenticación y de captura/predicción de síntomas:
- Autenticación: `/api/v1/auth/signin`, `/api/v1/auth/me`, `/api/v1/auth/refresh`
- Flujo clínico: `/api/v1/symptoms` (POST y GET), `/api/v1/predict`, `/api/v1/predictions`

## Flujo probado (por iteración)
1. Login (`POST /auth/signin`) con usuario demo (`patient@demo.local`).
2. Perfil (`GET /auth/me`) para extraer `patient_id`.
3. Captura de síntomas (`POST /symptoms`) para ese paciente.
4. Predicción (`POST /predict`) usando el `symptom_entry_id` creado.
5. Listado de síntomas (`GET /symptoms`) con paginación por cursor (parámetro `limit`).
6. Listado de predicciones (`GET /predictions`).
7. Refresh de token (`POST /auth/refresh`).

## Plan JMeter utilizado
- Archivo: `scripts/aiddiag_local_load.jmx`
- Thread Groups parametrizados:
  - Smoke: 1 usuario, 1 loop (sanidad).
  - Load: `${__P(load_threads,10)}` usuarios, ramp-up 30 s, 3 loops (carga moderada).
  - Stress: `${__P(stress_threads,100)}` usuarios, ramp-up 240 s, 2 loops (stress configurable).
- Defaults: host `localhost`, puerto `8000`, protocolo `http`.
- Autenticación: usuario semilla `patient@demo.local` / `Patient123!` (creado por `scripts/seed_demo.py`).
- Variables: `LIMIT` para paginación de síntomas/predicciones (por defecto 20).

## Datos de entrada
- Credenciales demo y datos semilla generados con `scripts/seed_demo.py`.
- Carga sintética de síntomas: payload estático `{ fever: true, cough: true, fatigue: false }`.

## Métricas recogidas (por sampler)
- Latencia (avg, p95, p99, max) y porcentaje de error.
- Códigos de respuesta capturados en el JTL (`results/aiddiag_local.jtl`).

## Hallazgos observados en la última ejecución
- `POST /symptoms`: 500 en todos los intentos (100% error) → bloquea el flujo de `POST /predict` (NoHttpResponse).
- Lecturas (`/auth/me`, `/symptoms` GET, `/predictions`) y `/auth/refresh` sin errores, pero con p95 elevados en signin/refresh bajo carga.

## Cómo ejecutar
```powershell
# Arrancar servicios
docker-compose up -d
# (Opcional) Sembrar datos demo
# docker-compose exec app python scripts/seed_demo.py
# Ejecutar JMeter
.\tools\apache-jmeter-5.6.3\bin\jmeter.bat -n -t scripts\aiddiag_local_load.jmx -l results\aiddiag_local.jtl -Jjmeter.save.saveservice.output_format=csv
```

## Cómo resumir resultados
```powershell
python - <<'PY'
import csv, math
from collections import defaultdict
from pathlib import Path
path = Path('results/aiddiag_local.jtl')
rows = []
with path.open() as f:
    r = csv.reader(f)
    for row in r:
        if not row or row[0].startswith('timeStamp'):
            continue
        try:
            ts, elapsed, label, code, msg, thread, dtype, success = row[:8]
        except ValueError:
            continue
        if not elapsed.isdigit():
            continue
        rows.append((label, int(elapsed), success.lower()=='true', code))
by_label = defaultdict(list)
for label, elapsed, ok, code in rows:
    by_label[label].append((elapsed, ok, code))
def pct(sorted_vals, p):
    k = (len(sorted_vals)-1) * p / 100
    f = math.floor(k); c = math.ceil(k)
    if f == c:
        return sorted_vals[int(k)]
    return sorted_vals[f] + (sorted_vals[c]-sorted_vals[f])*(k-f)
print(f"Parsed {len(rows)} samples across {len(by_label)} labels")
for label, vals in sorted(by_label.items()):
    el = [v[0] for v in vals]
    ok_count = sum(1 for _, ok, _ in vals if ok)
    err = len(vals) - ok_count
    el_sorted = sorted(el)
    avg = sum(el)/len(el)
    print(f"{label}: n={len(vals)} err={err/len(vals)*100:.2f}% avg={avg:.1f}ms p95={pct(el_sorted,95):.1f} p99={pct(el_sorted,99):.1f} max={max(el)}")
PY
```

## Próximos pasos
- Corregir la causa del 500 en `POST /symptoms` (revisar logs de la app). Tras corregir, repetir Smoke y Load.
- Confirmar que `POST /predict` responde una vez se resuelva `POST /symptoms`.
- Si se requiere reporte HTML: añadir `-g results\\aiddiag_report.html` al comando JMeter.
