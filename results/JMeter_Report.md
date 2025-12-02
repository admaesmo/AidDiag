# AidDiag - Reporte de Pruebas JMeter (local)

## Entorno
- Host: Windows (i5, 8 GB RAM).
- Contenedores activos: `app`, `db` via `docker-compose`.
- Límite de memoria app en Docker: ~4 GB (según configuración local).
- JMeter: `tools/apache-jmeter-5.6.3`.
- Plan usado: `scripts/aiddiag_local_load.jmx` (Smoke 1 hilo, Load 20 hilos, Stress 100 hilos).

## Comando ejecutado
```powershell
.\tools\apache-jmeter-5.6.3\bin\jmeter.bat `
  -n `
  -t scripts\aiddiag_local_load.jmx `
  -l results\aiddiag_local.jtl `
  -Jjmeter.save.saveservice.output_format=csv
```

## Resumen de resultados (archivo: `results/aiddiag_local.jtl`)
Métricas calculadas desde el JTL (aprox., ms):

| Sampler            | Muestras | Error % | Avg | P95  | P99  | Max  | Notas                  |
|--------------------|---------:|--------:|----:|-----:|-----:|-----:|------------------------|
| POST /auth/signin  | 261      | 0.00%   | 796 | 1650 | 1874 | 2093 | Latencia alta login    |
| GET /auth/me       | 261      | 0.00%   | 121 | 489  | 758  | 844  | OK                     |
| POST /symptoms     | 261      | 100.00% | 163 | 729  | 942  | 1072 | 500 en todos los casos |
| POST /predict      | 261      | 100.00% | 3   | 4    | 80   | 141  | NoHttpResponse (falla) |
| GET /symptoms      | 261      | 0.00%   | 169 | 734  | 1160 | 1354 | OK                     |
| GET /predictions   | 261      | 0.00%   | 102 | 374  | 722  | 1093 | OK                     |
| POST /auth/refresh | 261      | 0.00%   | 352 | 1038 | 1231 | 1314 | Latencia alta          |

### Ejecución ampliada (Stress 300 hilos)
Archivo JTL: `results/aiddiag_local_300.jtl`

| Sampler            | Muestras | Error % | Avg  | P95   | P99   | Max  | Notas                  |
|--------------------|---------:|--------:|-----:|------:|------:|-----:|------------------------|
| POST /auth/signin  | 661      | 0.00%   | 1630 | 3400  | 4222  | 4829 | Latencia muy alta      |
| GET /auth/me       | 661      | 0.00%   | 921  | 2854  | 3678  | 4906 | OK                     |
| POST /symptoms     | 661      | 100.00% | 1010 | 2968  | 3813  | 4402 | 500 en todos los casos |
| POST /predict      | 661      | 100.00% | 12   | 46    | 242   | 356  | NoHttpResponse         |
| GET /symptoms      | 661      | 0.00%   | 981  | 2914  | 3611  | 4771 | OK                     |
| GET /predictions   | 661      | 0.00%   | 946  | 2918  | 3805  | 4869 | OK                     |
| POST /auth/refresh | 661      | 0.00%   | 1117 | 2958  | 3590  | 4030 | Latencia alta          |

Reporte HTML 300 hilos: `results/aiddiag_report_300/index.html`

### Ejecución 1 / 10 / 100 hilos (Thread Groups parametrizados)
Archivo JTL: `results/aiddiag_1_10_100.jtl` (Smoke 1, Load 10, Stress 100)

| Sampler            | Muestras | Error % | Avg | P95  | P99  | Max | Notas                  |
|--------------------|---------:|--------:|----:|-----:|-----:|----:|------------------------|
| POST /auth/signin  | 231      | 0.00%   | 381 | 508  | 919  | 920 | OK                     |
| GET /auth/me       | 231      | 0.00%   | 17  | 48   | 69   | 104 | OK                     |
| POST /symptoms     | 231      | 100.00% | 25  | 35   | 75   | 89  | 500 en todos los casos |
| POST /predict      | 231      | 100.00% | 1   | 1    | 3    | 5   | NoHttpResponse         |
| GET /symptoms      | 231      | 0.00%   | 19  | 28   | 55   | 73  | OK                     |
| GET /predictions   | 231      | 0.00%   | 15  | 24   | 29   | 47  | OK                     |
| POST /auth/refresh | 231      | 0.00%   | 75  | 124  | 179  | 204 | OK                     |

Reporte HTML: `results/aiddiag_report_1_10_100/index.html`

### Ejecución alto nivel (≈50 + 400 hilos)
Archivo JTL (limpiado): `results/aiddiag_high_clean.jtl` generado con `-Jload_threads=50 -Jstress_threads=400`

| Sampler            | Muestras | Error % | Avg    | P95    | P99    | Max   | Notas                              |
|--------------------|---------:|--------:|-------:|-------:|-------:|------:|------------------------------------|
| POST /auth/signin  | 655      | 54.35%  | 112949 | 266119 | 392962 | 394140| Saturación, latencias extremas     |
| GET /auth/me       | 733      | 73.67%  | 75736  | 242041 | 389294 | 450063| Alta tasa de error                  |
| POST /symptoms     | 590      | 100.00% | 71574  | 209501 | 212045 | 242457| 500 en todos los casos              |
| POST /predict      | 591      | 100.00% | 60916  | 179592 | 214378 | 240359| NoHttpResponse                      |
| GET /symptoms      | 473      | 64.48%  | 80037  | 209577 | 242917 | 302533| Errores y latencias elevadas        |
| GET /predictions   | 410      | 63.66%  | 56503  | 179601 | 239811 | 271252| Errores y latencias elevadas        |
| POST /auth/refresh | 250      | 44.80%  | 70614  | 201347 | 214934 | 215140| Errores y latencias elevadas        |

Reporte HTML: `results/aiddiag_report_high/index.html` (basado en `aiddiag_high_clean.jtl`)

Errores observados:
- `POST /symptoms` devuelve 500 en todos los intentos.
- `POST /predict` falla con `NoHttpResponse` (derivado de la falla previa).

## Cómo revisar o repetir las pruebas
1) Arrancar servicios (si no están activos):
   ```powershell
   docker-compose up -d
   ```
   (Opcional) sembrar datos demo si es la primera vez:
   ```powershell
   docker-compose exec app python scripts/seed_demo.py
   ```

2) Ejecutar el plan JMeter (mismo comando usado):
   ```powershell
   .\tools\apache-jmeter-5.6.3\bin\jmeter.bat `
     -n `
     -t scripts\aiddiag_local_load.jmx `
     -l results\aiddiag_local.jtl `
     -Jjmeter.save.saveservice.output_format=csv
   ```
   - El plan incluye los 3 grupos: Smoke (1 hilo), Load (20 hilos), Stress (100 hilos).
   - Ajusta hilos o desactiva grupos desde la GUI si necesitas menos carga.

3) Resumir el JTL en consola (opcional):
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
    print(f"{label}: n={len(vals)} err={err/len(vals)*100:.2f}% avg={avg:.1f}ms "
          f"p95={pct(el_sorted,95):.1f} p99={pct(el_sorted,99):.1f} max={max(el)}")
PY
   ```

## Próximos pasos sugeridos
- Revisar logs de la app para `POST /symptoms` (500) y corregir; volver a ejecutar Smoke y Load.
- Si `POST /symptoms` se corrige, revalidar `POST /predict` (debe dejar de fallar).
- Si necesitas reporte HTML, generar con `-g results\aiddiag_report.html` en el comando JMeter.
