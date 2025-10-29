# AidDiag (Local MVP) — Punto 1

Este scaffold corre localmente el **punto 1**: auth/RBAC básico y endpoints:
- POST /api/v1/symptoms
- POST /api/v1/predict
- GET  /api/v1/predictions
- GET  /api/v1/cases
- PATCH /api/v1/cases/{id}
- POST /api/v1/audit/events
- GET  /jwks.json

### Pasos rápidos
1) `docker compose up -d`  
2) `python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`  
3) `cp .env.example .env`  
4) `python scripts/make_jwt.py > token.txt`  
5) `uvicorn app.main:app --reload --port 8000`  
6) Usa el JWT de `token.txt` en Postman (Bearer).

> **Nota**: En producción el JWT lo emite **Cognito**; esto es un mock local para desarrollo.
