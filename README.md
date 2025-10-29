# AidDiag (Local MVP) — Punto 1

Backend FastAPI con autenticación JWT RS256, RBAC y endpoints de demo para clase.

## Endpoints clave

- `POST /api/v1/auth/signup`, `POST /api/v1/auth/signin`, `GET /api/v1/auth/me`
- `POST /api/v1/symptoms`, `POST /api/v1/predict`, `GET /api/v1/predictions`
- `GET /api/v1/cases`, `PATCH /api/v1/cases/{id}`
- `POST /api/v1/audit/events`
- `GET /jwks.json`

## Requisitos previos

- Python 3.11
- PostgreSQL 15 local con la extensión `citext` habilitada

## Puesta en marcha local

```bash
# 1) Crear entorno virtual e instalar dependencias
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2) Exportar variables de conexión si difieren de .env.example
cp .env.example .env  # ajusta credenciales si hace falta

# 3) Aplicar migraciones de base de datos
alembic upgrade head

# 4) Sembrar datos de demo (tenant, roles, usuarios y un caso)
python scripts/seed_demo.py

# 5) Generar claves/jwks y un JWT local de ejemplo
python scripts/make_jwt.py > token.txt

# 6) Levantar la API
python -m uvicorn app.main:app --reload --port 8000

# Swagger UI disponible en
# http://127.0.0.1:8000/docs
```

## Colección Postman

Importa en Postman los archivos generados en la raíz del repo:

- `AidDiag_Postman_Parte1_Collection.json`
- `AidDiag_Postman_Parte1_Environment.json`

Configura el environment con `base_url` y pega el token de `token.txt` en `bearer_token`. Los scripts de la colección guardan automáticamente el `symptom_entry_id` tras crear síntomas.

## OpenAPI

`AidDiag_OpenAPI.yaml` contiene el contrato actualizado listo para compartir o importar en SwaggerHub.

> En producción los tokens serán emitidos por Amazon Cognito. El flujo local firma con la clave `app/static/private.pem` y valida contra `app/static/jwks.json`.
