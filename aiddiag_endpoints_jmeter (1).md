# Guía Completa: Endpoints de Alta Transaccionalidad en AidDiag
## Implementación, Testing con JMeter y Despliegue Local

---

## Tabla de Contenidos

1. [Introducción](#introducción)
2. [Contexto: Endpoints de Alta Transaccionalidad](#contexto-endpoints-de-alta-transaccionalidad)
3. [Implementación de Endpoints](#implementación-de-endpoints)
4. [Configuración del Entorno Local](#configuración-del-entorno-local)
5. [Testing con JMeter](#testing-con-jmeter)
6. [Estrategias de Escalabilidad](#estrategias-de-escalabilidad)
7. [Monitoreo y Troubleshooting](#monitoreo-y-troubleshooting)

---

## Introducción

AidDiag está diseñado para soportar **≥10,000 usuarios concurrentes** desde el primer día. Este documento proporciona una guía completa para:

- Implementar los **dos endpoints faltantes** identificados en el análisis de alta transaccionalidad
- Configurar un entorno de pruebas local con **Docker**
- Ejecutar pruebas de carga con **Apache JMeter**
- Aplicar patrones de escalabilidad en AWS

### Endpoints Objetivo

1. **`GET /api/v1/symptoms`** (Endpoint 9) — Lectura paginada de síntomas
2. **`POST /api/v1/auth/refresh`** (Endpoint 10) — Renovación de tokens

---

## Contexto: Endpoints de Alta Transaccionalidad

### Matriz de Endpoints Críticos

| # | Endpoint | Verbo | Tipo de Carga | Razón |
|---|----------|-------|---------------|-------|
| 1 | `/api/v1/auth/signin` | POST | Ráfagas de login | Oleadas de inicio de jornada |
| 2 | `/api/v1/auth/me` | GET | Lectura frecuente | Consulta UI cada load/refresh |
| 3 | `/api/v1/symptoms` | POST | Escritura intensiva | Alto volumen de reportes |
| 4 | `/api/v1/predict` | POST | CPU/IO + escritura | Invocación post-captura |
| 5 | `/api/v1/predictions` | GET | Lectura intensiva | Historial con paginación |
| 6 | `/api/v1/cases` | GET | Lectura intensiva | Bandeja de profesionales |
| 7 | `/api/v1/cases/{id}` | PATCH | Escritura concurrente | Cambios de estado operativos |
| 8 | `/api/v1/audit/events` | POST | Escritura masiva | Auditoría por acción |
| 9 | `/api/v1/symptoms` | GET | Lectura paginada | **Timelines y reportes** |
| 10 | `/api/v1/auth/refresh` | POST | Ráfagas periódicas | **Renovación de token** |

### Recomendaciones Técnicas Clave

#### Modelo de Datos e Índices

```sql
-- Tabla: symptom_entries
CREATE INDEX idx_symptom_entries_tenant_patient_created 
ON symptom_entries(tenant_id, patient_id, created_at DESC);

-- Tabla: predictions
CREATE INDEX idx_predictions_tenant_patient_created 
ON predictions(tenant_id, patient_id, created_at DESC);

-- Tabla: cases
CREATE INDEX idx_cases_tenant_assigned_status 
ON cases(tenant_id, assigned_to, status, updated_at DESC);

-- Tabla: audit_events
CREATE INDEX idx_audit_events_tenant_ts 
ON audit_events(tenant_id, ts DESC);
```

#### Paginación

**Problema:** `OFFSET` en queries grandes degrada rendimiento exponencialmente.

**Solución:** Usar **keyset pagination (cursor-based)**

```sql
-- En lugar de:
SELECT * FROM symptom_entries WHERE tenant_id = ? OFFSET 1000 LIMIT 20;

-- Usar:
SELECT * FROM symptom_entries 
WHERE tenant_id = ? AND created_at < ? 
ORDER BY created_at DESC 
LIMIT 20;
```

#### Caché y Mitigación

- **`/auth/me`**: TTL 30–120 segundos por `sub/tenant_id`
- **Listados** (predictions, cases): Caché por usuario/tenant + invalidación al crear/actualizar
- **Rate limiting**: Proteger `signin` y `refresh` contra ataques de fuerza bruta
- **Bloqueo por IP**: Después de N intentos fallidos

#### Escrituras de Alto Volumen

- Usar `Idempotency-Key` en POST (`symptoms`, `predict`) para evitar duplicados bajo reintentos
- Auditoría asíncrona: mantener **traza mínima en caliente**, exportar lote masivo a S3 (Kinesis/SQS → Lambda)

#### Concurrencia y Consistencia

- **Optimistic Locking**: Campo `version` o `updated_at` en cláusula `WHERE` para evitar race conditions
- **Transacciones cortas**: Preferir `READ COMMITTED`

---

## Implementación de Endpoints

### Implementación de `GET /api/v1/symptoms` (Lectura Paginada)

Este endpoint retorna el historial de entradas de síntomas de un paciente usando **keyset pagination**.

#### Paso 1: Actualizar `AidDiag/app/schemas.py`

Añade los siguientes esquemas de Pydantic al archivo `schemas.py`:

```python
from pydantic import BaseModel, ConfigDict
from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime

class SymptomEntry(BaseModel):
    """Esquema de una entrada de síntoma individual."""
    id: UUID
    tenant_id: UUID
    patient_id: UUID
    symptoms: Dict[str, Any]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SymptomEntryList(BaseModel):
    """Respuesta paginada de entradas de síntomas."""
    total: int
    items: List[SymptomEntry]
    next_cursor: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
```

#### Paso 2: Implementar el Endpoint en `AidDiag/app/main.py`

Añade la siguiente función después de `create_symptom_entry`:

```python
from fastapi import Query, Depends, HTTPException, status
from sqlalchemy.orm import Session
from uuid import UUID
from datetime import datetime
from typing import Optional, Any, Dict
import logging

logger = logging.getLogger(__name__)

@app.get(
    "/api/v1/symptoms",
    response_model=schemas.SymptomEntryList,
    status_code=status.HTTP_200_OK,
    tags=["Symptoms"],
    summary="Listar síntomas paginados",
    description="Retorna el historial de entradas de síntomas para un paciente usando keyset pagination."
)
def list_symptom_entries(
    patient_id: UUID = Query(..., description="UUID del paciente"),
    limit: int = Query(20, ge=1, le=100, description="Número de registros por página (máximo 100)"),
    cursor: Optional[datetime] = Query(
        None, 
        description="Timestamp para keyset pagination. Devuelve registros creados antes de este timestamp."
    ),
    db: Session = Depends(get_db),
    claims: Dict[str, Any] = Depends(Auth()),
) -> schemas.SymptomEntryList:
    """
    Retorna el historial de entradas de síntomas para un paciente.
    
    **Características:**
    - Paginación por cursor (keyset pagination)
    - Filtrado por tenant_id para seguridad multi-tenant
    - Índices optimizados para p95 < 200ms en 10K usuarios
    
    **Parámetros:**
    - `patient_id`: UUID del paciente
    - `limit`: Número de registros (1-100, default 20)
    - `cursor`: Timestamp del último registro de la página anterior (opcional)
    
    **Ejemplo:**
    ```
    GET /api/v1/symptoms?patient_id=550e8400-e29b-41d4-a716-446655440000&limit=10
    ```
    
    **Respuesta:**
    ```json
    {
        "total": 150,
        "items": [...],
        "next_cursor": "2024-01-15T14:30:00Z"
    }
    ```
    """
    try:
        tenant_id = UUID(claims["tenant_id"])
        user_id = UUID(claims["sub"])
        
        # Validar que el paciente pertenece al tenant del usuario autenticado
        patient = db.query(models.Patient).filter(
            models.Patient.id == patient_id,
            models.Patient.tenant_id == tenant_id
        ).first()
        
        if not patient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Paciente no encontrado o no tienes permisos de acceso"
            )
        
        # Consulta base: filtrar por tenant_id y patient_id
        query = db.query(models.SymptomEntry).filter(
            models.SymptomEntry.tenant_id == tenant_id,
            models.SymptomEntry.patient_id == patient_id,
        )
        
        # Aplicar filtro de cursor para keyset pagination
        if cursor:
            query = query.filter(models.SymptomEntry.created_at < cursor)
        
        # Contar total (optimizable: considerar cachear para no contar en cada request)
        total = query.count()
        
        # Ordenar por fecha de creación descendente
        query = query.order_by(models.SymptomEntry.created_at.desc())
        
        # Obtener limit + 1 para determinar si hay más páginas
        items = query.limit(limit + 1).all()
        
        # Determinar el siguiente cursor
        next_cursor = None
        if len(items) > limit:
            # Si obtuvimos más de `limit` registros, hay más páginas
            next_cursor = items[limit - 1].created_at
            items = items[:limit]  # Truncar a exactamente `limit` registros
        
        # Transformar a esquemas Pydantic
        result = [schemas.SymptomEntry.model_validate(item) for item in items]
        
        logger.info(
            f"list_symptom_entries: tenant={tenant_id}, patient={patient_id}, "
            f"returned={len(result)}, total={total}"
        )
        
        return schemas.SymptomEntryList(
            total=total,
            items=result,
            next_cursor=next_cursor
        )
        
    except ValueError as e:
        logger.error(f"Error validando UUIDs: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="UUID inválido en parámetros"
        )
    except Exception as e:
        logger.error(f"Error inesperado en list_symptom_entries: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al recuperar síntomas"
        )
```

---

### Implementación de `POST /api/v1/auth/refresh` (Renovación de Token)

Este endpoint emite un nuevo token de acceso a partir de un token de refresco válido.

#### Paso 1: Actualizar `AidDiag/app/schemas.py`

Añade el esquema de solicitud junto a otros esquemas de autenticación:

```python
class RefreshTokenRequest(BaseModel):
    """Solicitud de renovación de token."""
    refresh_token: str = Field(
        ..., 
        description="Token de refresco válido obtenido en el login",
        min_length=10
    )


class TokenRefreshResponse(BaseModel):
    """Respuesta exitosa de renovación de token."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    refresh_token: Optional[str] = None
```

#### Paso 2: Implementar el Endpoint en `AidDiag/app/routers/auth.py`

Añade la siguiente función después de la función `signin`:

```python
from datetime import datetime, timezone, timedelta
from fastapi import router, HTTPException, Depends, status
from sqlalchemy.orm import Session
from uuid import UUID
from typing import Dict, Any
import logging
import jwt

logger = logging.getLogger(__name__)

@router.post(
    "/auth/refresh",
    response_model=schemas.AuthToken,
    status_code=status.HTTP_200_OK,
    tags=["Authentication"],
    summary="Renovar token de acceso",
    description="Emite un nuevo token de acceso a partir de un refresh token válido."
)
def refresh_token(
    payload: schemas.RefreshTokenRequest,
    db: Session = Depends(get_db),
) -> schemas.AuthToken:
    """
    Emite un nuevo token de acceso a partir de un refresh token.
    
    **Flujo de funcionamiento:**
    1. Decodifica y valida el refresh token
    2. Verifica que el usuario y tenant existen y están activos
    3. Emite un nuevo access token con TTL corto
    
    **Consideraciones de Seguridad:**
    - El refresh token tiene un TTL más largo (ej: 7 días)
    - El access token tiene un TTL corto (ej: 15 minutos)
    - Se pueden implementar blacklist de tokens revocados en Redis
    - Rate limit (máx 5 intentos fallidos por IP/usuario)
    
    **Parámetros:**
    - `refresh_token`: Token de refresco del response anterior de signin
    
    **Ejemplo:**
    ```json
    {
        "refresh_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9..."
    }
    ```
    
    **Respuesta Exitosa (200):**
    ```json
    {
        "access_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",
        "token_type": "bearer",
        "expires_in": 900,
        "refresh_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9..."
    }
    ```
    
    **Respuesta de Error (401):**
    ```json
    {
        "detail": "Invalid or expired refresh token"
    }
    ```
    """
    try:
        # Paso 1: Decodificar el refresh token
        try:
            claims = decode_jwt(payload.refresh_token)
        except jwt.ExpiredSignatureError:
            logger.warning(f"Refresh token expirado")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token ha expirado"
            )
        except jwt.InvalidTokenError as e:
            logger.warning(f"Refresh token inválido: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token inválido"
            )
        
        # Paso 2: Extraer claims
        try:
            user_id = UUID(claims["sub"])
            tenant_id = UUID(claims["tenant_id"])
            role_name = claims.get("role", "user")
        except (KeyError, ValueError) as e:
            logger.error(f"Claims incompletos o inválidos: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token malformado"
            )
        
        # Paso 3: Buscar el usuario en la BD
        user = db.query(models.User).filter(
            models.User.id == user_id,
            models.User.tenant_id == tenant_id
        ).first()
        
        if not user:
            logger.warning(f"Usuario {user_id} no encontrado para refresh")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Usuario no encontrado"
            )
        
        # Paso 4: Validar que el usuario está activo
        if not user.is_active:
            logger.warning(f"Usuario {user_id} está inactivo")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Usuario inactivo"
            )
        
        # Paso 5: Emitir nuevo token de acceso
        # (La función _issue_local_token debe existir en tu código)
        access_token = _issue_local_token(user, role_name)
        
        logger.info(f"Token refreshed para usuario {user_id}")
        
        return schemas.AuthToken(
            access_token=access_token,
            token_type="bearer",
            expires_in=900  # 15 minutos
        )
        
    except HTTPException:
        # Re-raise HTTPExceptions como están
        raise
    except Exception as e:
        logger.error(f"Error inesperado en refresh_token: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al renovar token"
        )


# Función auxiliar para emitir tokens (debe existir en tu código)
def _issue_local_token(user: models.User, role_name: str) -> str:
    """
    Emite un nuevo token JWT local.
    
    **Estructura del token:**
    ```json
    {
        "sub": "user-uuid",
        "tenant_id": "tenant-uuid",
        "role": "admin|professional|patient",
        "iss": "aiddiag",
        "aud": "aiddiag-api",
        "iat": 1234567890,
        "exp": 1234568790,
        "type": "access"
    }
    ```
    """
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=15)
    
    payload = {
        "sub": str(user.id),
        "tenant_id": str(user.tenant_id),
        "role": role_name,
        "iss": "aiddiag",
        "aud": "aiddiag-api",
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
        "type": "access"
    }
    
    # Usar la clave privada RS256 para firmar
    token = jwt.encode(
        payload,
        PRIVATE_KEY,  # Debe estar configurada en variables de entorno
        algorithm="RS256"
    )
    
    return token
```

---

## Configuración del Entorno Local

### Prerrequisitos

- **Docker** y **Docker Compose** instalados
- **Git** para clonar el repositorio
- **Python 3.10+** (opcional, para scripts locales)
- **JMeter 5.5+** para pruebas de carga
- **Postman** o **curl** para pruebas manual

### Estructura del Proyecto

```
AidDiag/
├── app/
│   ├── main.py              # Endpoints principales
│   ├── schemas.py           # Esquemas Pydantic
│   ├── models.py            # Modelos SQLAlchemy
│   ├── routers/
│   │   └── auth.py          # Endpoints de autenticación
│   └── dependencies.py      # Dependencias (BD, auth)
├── migrations/              # Alembic migrations
├── scripts/
│   ├── seed_demo.py         # Datos de demostración
│   └── test_endpoints.py    # Script de pruebas (nuevo)
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

### Paso 1: Clonar el Repositorio

```bash
git clone https://github.com/tu-org/AidDiag.git
cd AidDiag
```

### Paso 2: Configurar Variables de Entorno

Crea un archivo `.env` en la raíz del proyecto (basándote en `.env.example`):

```bash
# .env
ENVIRONMENT=local
DEBUG=True

# Database
DATABASE_URL=postgresql://aiddiag:aiddiag_dev@postgres:5432/aiddiag
SQLALCHEMY_ECHO=False

# JWT/Security
SECRET_KEY=tu-clave-secreta-super-segura-para-desarrollo-local
ALGORITHM=RS256
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7

# AWS (si usas servicios AWS)
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=test
AWS_SECRET_ACCESS_KEY=test

# Logs
LOG_LEVEL=INFO

# CORS
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:8000

# Cognito (opcional)
COGNITO_CLIENT_ID=test-client
COGNITO_USER_POOL_ID=test-pool
```

### Paso 3: Construir y Ejecutar con Docker Compose

```bash
# Construir imágenes
docker-compose build

# Iniciar servicios (PostgreSQL + API)
docker-compose up

# En otra terminal, ejecutar migraciones (si es necesario)
docker-compose exec app alembic upgrade head

# Generar datos de demostración
docker-compose exec app python scripts/seed_demo.py
```

### Verificación Inicial

```bash
# Verificar que la API está disponible
curl http://localhost:8000/health

# Acceder a la documentación interactiva Swagger
open http://localhost:8000/docs
```

---

## Testing con JMeter

### Introducción a JMeter para Testing de APIs

**Apache JMeter** es una herramienta de código abierto para realizar pruebas de carga, estrés y funcionales. Es ideal para validar que tus endpoints puedan manejar ≥10,000 usuarios concurrentes.

### Instalación de JMeter

#### En macOS (con Homebrew):

```bash
brew install jmeter
```

#### En Linux (Ubuntu/Debian):

```bash
sudo apt-get update
sudo apt-get install jmeter
```

#### En Windows:

Descarga desde: https://jmeter.apache.org/download_jmeter.cgi

### Creación del Plan de Pruebas

#### Paso 1: Crear un Nuevo Plan de Pruebas

1. Abre JMeter: `jmeter` (o `jmeter.bat` en Windows)
2. File → New
3. Guarda el plan: File → Save → `aiddiag_load_test.jmx`

#### Paso 2: Configurar la Estructura Base

El plan debe incluir:

```
Test Plan
├── HTTP Request Defaults (configuración global)
├── User Defined Variables
├── Thread Group 1: Smoke Test (1 usuario, 1 loop)
├── Thread Group 2: Load Test (10 usuarios, 10 loops)
├── Thread Group 3: Stress Test (100 usuarios, 5 loops)
└── Listeners (para ver resultados)
```

#### Paso 3: Crear HTTP Request Defaults

1. Clic derecho en "Test Plan" → Add → Config Element → HTTP Request Defaults
2. Configura:
   - Protocol: `http`
   - Hostname: `localhost`
   - Port: `8000`
   - Path: `/api/v1` (prefijo común)

#### Paso 4: Variables Globales

1. Clic derecho en "Test Plan" → Add → Config Element → User Defined Variables
2. Añade variables:

| Name | Value |
|------|-------|
| `BASE_URL` | `http://localhost:8000` |
| `PATIENT_UUID` | `550e8400-e29b-41d4-a716-446655440000` |
| `ACCESS_TOKEN` | (vacío, se rellenará dinámicamente) |
| `REFRESH_TOKEN` | (vacío, se rellenará dinámicamente) |

#### Paso 5: Thread Group 1 - Smoke Test (Básico)

1. Clic derecho en "Test Plan" → Add → Threads → Thread Group
2. Configura:
   - Name: `Smoke Test`
   - Number of Threads: `1`
   - Ramp-up period: `1` segundo
   - Loop Count: `1`

3. Añade una solicitud HTTP para obtener token:
   - Clic derecho en "Smoke Test" → Add → Sampler → HTTP Request
   - Name: `POST /auth/signin`
   - Path: `/api/v1/auth/signin`
   - Method: `POST`
   - Body Data:
   ```json
   {
       "email": "test@example.com",
       "password": "password123"
   }
   ```

4. Añade un extractor JSON para capturar el token:
   - Clic derecho en "POST /auth/signin" → Add → Post Processor → JSON Extractor
   - JSON Path Expressions:
     - Reference Name: `access_token`
     - JSON Path: `$.access_token`

5. Añade una solicitud GET para listar síntomas:
   - Clic derecho en "Smoke Test" → Add → Sampler → HTTP Request
   - Name: `GET /symptoms`
   - Path: `/api/v1/symptoms`
   - Method: `GET`
   - Parameters:
     - Name: `patient_id` | Value: `${PATIENT_UUID}`
     - Name: `limit` | Value: `10`
   - Headers:
     - Authorization: `Bearer ${access_token}`

#### Paso 6: Thread Group 2 - Load Test

1. Clic derecho en "Test Plan" → Add → Threads → Thread Group
2. Configura:
   - Name: `Load Test`
   - Number of Threads: `10`
   - Ramp-up period: `60` segundos (1 usuario/6 segundos)
   - Loop Count: `10`

3. Repite los mismos samplers del Smoke Test

#### Paso 7: Thread Group 3 - Stress Test

1. Clic derecho en "Test Plan" → Add → Threads → Thread Group
2. Configura:
   - Name: `Stress Test`
   - Number of Threads: `100`
   - Ramp-up period: `300` segundos (1 usuario/3 segundos)
   - Loop Count: `5`

#### Paso 8: Añadir Listeners para Análisis

Para cada Thread Group, añade:

1. **View Results Tree** (para debug):
   - Clic derecho en Thread Group → Add → Listener → View Results Tree

2. **Summary Report** (para métricas agregadas):
   - Clic derecho en Thread Group → Add → Listener → Summary Report

3. **Response Time Graph**:
   - Clic derecho en Thread Group → Add → Listener → Response Time Graph

4. **Aggregate Report**:
   - Clic derecho en Thread Group → Add → Listener → Aggregate Report

### Ejemplo: Script JMeter en XML

Aquí está el plan completo en formato XML (importa esto en JMeter):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<jmeterTestPlan version="1.2">
  <hashTree>
    <TestPlan guiclass="TestPlanGui" testclass="TestPlan" testname="AidDiag Load Test">
      <elementProp name="TestPlan.user_defined_variables" elementType="Arguments"/>
      <stringProp name="TestPlan.user_defined_variables"/>
      <boolProp name="TestPlan.functional_mode">false</boolProp>
      <boolProp name="TestPlan.serialize_threadgroups">false</boolProp>
      <elementProp name="TestPlan.user_defined_variables" elementType="Arguments" guiclass="ArgumentsPanel" testclass="Arguments" testname="User Defined Variables">
        <collectionProp name="Arguments.arguments">
          <elementProp name="BASE_URL" elementType="Argument">
            <stringProp name="Argument.name">BASE_URL</stringProp>
            <stringProp name="Argument.value">http://localhost:8000</stringProp>
            <stringProp name="Argument.metadata">=</stringProp>
          </elementProp>
          <elementProp name="PATIENT_UUID" elementType="Argument">
            <stringProp name="Argument.name">PATIENT_UUID</stringProp>
            <stringProp name="Argument.value">550e8400-e29b-41d4-a716-446655440000</stringProp>
            <stringProp name="Argument.metadata">=</stringProp>
          </elementProp>
        </collectionProp>
      </elementProp>
      <hashTree>
        <!-- Thread Group: Smoke Test -->
        <ThreadGroup guiclass="ThreadGroupGui" testclass="ThreadGroup" testname="Smoke Test">
          <elementProp name="ThreadGroup.main_controller" elementType="LoopController" guiclass="LoopControlPanel" testclass="LoopController" testname="Loop Controller">
            <boolProp name="LoopController.continue_forever">false</boolProp>
            <stringProp name="LoopController.loops">1</stringProp>
          </elementProp>
          <stringProp name="ThreadGroup.num_threads">1</stringProp>
          <stringProp name="ThreadGroup.ramp_time">1</stringProp>
          <elementProp name="ThreadGroup.duration_assert" elementType="longProp" name="ThreadGroup.duration_assert">
            <boolProp name="ThreadGroup.scheduler">false</boolProp>
            <stringProp name="ThreadGroup.duration">0</stringProp>
            <stringProp name="ThreadGroup.delay">0</stringProp>
          </elementProp>
        </ThreadGroup>
        <hashTree>
          <!-- GET /symptoms sampler -->
          <HTTPSampler guiclass="HttpTestSampleGui" testclass="HTTPSampler" testname="GET /symptoms">
            <elementProp name="HTTPsampler.Arguments" elementType="Arguments" guiclass="HTTPArgumentsPanel" testclass="Arguments" testname="User Defined Variables">
              <collectionProp name="Arguments.arguments">
                <elementProp name="patient_id" elementType="HTTPArgument">
                  <boolProp name="HTTPArgument.always_encode">false</boolProp>
                  <stringProp name="Argument.name">patient_id</stringProp>
                  <stringProp name="Argument.value">${PATIENT_UUID}</stringProp>
                  <stringProp name="Argument.metadata">=</stringProp>
                  <boolProp name="HTTPArgument.use_equals">true</boolProp>
                </elementProp>
                <elementProp name="limit" elementType="HTTPArgument">
                  <boolProp name="HTTPArgument.always_encode">false</boolProp>
                  <stringProp name="Argument.name">limit</stringProp>
                  <stringProp name="Argument.value">20</stringProp>
                  <stringProp name="Argument.metadata">=</stringProp>
                  <boolProp name="HTTPArgument.use_equals">true</boolProp>
                </elementProp>
              </collectionProp>
            </elementProp>
            <stringProp name="HTTPSampler.domain">localhost</stringProp>
            <stringProp name="HTTPSampler.port">8000</stringProp>
            <stringProp name="HTTPSampler.protocol">http</stringProp>
            <stringProp name="HTTPSampler.contentEncoding"></stringProp>
            <stringProp name="HTTPSampler.path">/api/v1/symptoms</stringProp>
            <stringProp name="HTTPSampler.method">GET</stringProp>
            <boolProp name="HTTPSampler.follow_redirects">true</boolProp>
            <boolProp name="HTTPSampler.auto_redirects">false</boolProp>
            <boolProp name="HTTPSampler.use_keepalive">true</boolProp>
            <boolProp name="HTTPSampler.DO_MULTIPART_POST">false</boolProp>
            <stringProp name="HTTPSampler.embedded_url_re"></stringProp>
            <stringProp name="HTTPSampler.connect_timeout"></stringProp>
            <stringProp name="HTTPSampler.response_timeout"></stringProp>
          </HTTPSampler>
          <hashTree/>
          <!-- Summary Report -->
          <ResultCollector guiclass="SummaryReport" testclass="ResultCollector" testname="Summary Report">
            <elementProp name="ResultCollector.sample_listeners" elementType="elementProp"/>
            <stringProp name="filename"></stringProp>
            <boolProp name="ResultCollector.error_logging">false</boolProp>
            <boolProp name="ResultCollector.success_only">false</boolProp>
            <boolProp name="ResultCollector.properties">false</boolProp>
            <boolProp name="ResultCollector.child_samples">true</boolProp>
            <stringProp name="ResultCollector.test_type">all</stringProp>
          </ResultCollector>
          <hashTree/>
        </hashTree>
      </hashTree>
    </TestPlan>
  </hashTree>
</jmeterTestPlan>
```

### Ejecución de Pruebas

#### Modo GUI (para desarrollo):

```bash
jmeter -t aiddiag_load_test.jmx
```

#### Modo Headless (para CI/CD):

```bash
jmeter -n -t aiddiag_load_test.jmx \
        -l results/aiddiag_results.jtl \
        -j results/aiddiag.log \
        -g results/aiddiag_graph.html
```

**Parámetros:**
- `-n`: Non-GUI mode
- `-t`: Test plan file
- `-l`: Results file (JTL format)
- `-j`: Log file
- `-g`: Generate HTML report

#### Interpretar Resultados

Después de ejecutar el test, revisa el "Aggregate Report":

| Métrica | Significado | Objetivo |
|---------|------------|----------|
| **Samples** | Total de requests ejecutadas | ≥ 100 |
| **Average** | Latencia promedio (ms) | < 200 |
| **Min** | Latencia mínima | Referencia |
| **Max** | Latencia máxima | < 1000 |
| **90%** | P90 latencia | < 300 |
| **95%** | P95 latencia | < 400 |
| **99%** | P99 latencia | < 800 |
| **Error %** | Tasa de error | < 1% |
| **Throughput** | Requests/segundo | ≥ 100 RPS |

### Ejemplo: Script Python para Automatizar Tests

Crea `scripts/run_jmeter_tests.py`:

```python
#!/usr/bin/env python3
"""
Script para ejecutar pruebas JMeter y generar reportes automáticamente.
"""

import subprocess
import sys
import os
from datetime import datetime
import json

def run_jmeter_test(test_plan, threads, result_file, log_file):
    """Ejecuta JMeter en modo headless."""
    cmd = [
        "jmeter",
        "-n",
        "-t", test_plan,
        "-l", result_file,
        "-j", log_file,
        "-Jthreads=" + str(threads),
    ]
    
    print(f"Ejecutando: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"Error: {result.stderr}")
        return False
    
    print(f"✓ Test completado. Resultados en {result_file}")
    return True


def main():
    """Ejecuta suite completa de pruebas."""
    
    # Configuración
    test_plan = "aiddiag_load_test.jmx"
    results_dir = "jmeter_results"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Crear directorio de resultados
    os.makedirs(results_dir, exist_ok=True)
    
    # Suite de pruebas
    test_suite = [
        ("Smoke", 1),
        ("Load", 10),
        ("Stress", 100),
    ]
    
    results = {}
    
    for test_name, num_threads in test_suite:
        print(f"\n{'='*60}")
        print(f"Ejecutando {test_name} Test ({num_threads} threads)...")
        print(f"{'='*60}\n")
        
        result_file = f"{results_dir}/{test_name.lower()}_{timestamp}.jtl"
        log_file = f"{results_dir}/{test_name.lower()}_{timestamp}.log"
        
        success = run_jmeter_test(test_plan, num_threads, result_file, log_file)
        results[test_name] = {
            "success": success,
            "result_file": result_file,
            "log_file": log_file
        }
    
    # Resumen
    print(f"\n{'='*60}")
    print("RESUMEN DE PRUEBAS")
    print(f"{'='*60}\n")
    
    for test_name, result in results.items():
        status = "✓ PASSED" if result["success"] else "✗ FAILED"
        print(f"{test_name:15} {status}")
    
    print(f"\nResultados guardados en: {results_dir}/")
    
    return all(r["success"] for r in results.values())


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
```

Ejecuta con:

```bash
python scripts/run_jmeter_tests.py
```

---

## Estrategias de Escalabilidad

### Arquitectura Recomendada (AWS)

```
┌─────────────────────────────────────────────────────────────┐
│                        CloudFront (CDN)                      │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────┴──────────────────────────────────────┐
│                    API Gateway + WAF                          │
│             (Throttle, Auth OIDC, Rate Limit)                │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────┴──────────────────────────────────────┐
│                  Application Load Balancer                    │
└──────────┬───────────────────────────────────────┬───────────┘
           │                                       │
    ┌──────▼──────┐                        ┌──────▼──────┐
    │  ECS Task 1 │                        │  ECS Task N │
    │  (FastAPI)  │◄──────┬────────────►   │  (FastAPI)  │
    └──────┬──────┘       │                └──────┬──────┘
           │         ┌────┴────┐                   │
           │         │ Redis   │                   │
           │         │ Cache   │                   │
           │         └────┬────┘                   │
           │              │                       │
    ┌──────┴──────────────┴───────────────────────┴──────┐
    │                                                      │
    │          RDS PostgreSQL (Multi-AZ)                  │
    │     (Master + Read Replicas)                        │
    │                                                      │
    └──────────────────────────────────────────────────────┘
           │                              │
    ┌──────▼────────┐          ┌──────────▼─────┐
    │ CloudWatch    │          │  X-Ray (Traces)│
    │ (Logs, Metrics)         │                 │
    └───────────────┘          └─────────────────┘
```

### Implementación de Caché con Redis

```python
from redis import Redis
from functools import wraps
import json

redis_client = Redis(host='redis', port=6379, db=0)

def cache_result(ttl_seconds=120):
    """Decorador para cachear resultados en Redis."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Generar clave de caché
            cache_key = f"{func.__name__}:{args}:{kwargs}"
            
            # Intentar recuperar del caché
            cached = redis_client.get(cache_key)
            if cached:
                return json.loads(cached)
            
            # Ejecutar función
            result = func(*args, **kwargs)
            
            # Guardar en caché
            redis_client.setex(
                cache_key,
                ttl_seconds,
                json.dumps(result, default=str)
            )
            
            return result
        return wrapper
    return decorator


# Uso en endpoint
@app.get("/api/v1/auth/me")
@cache_result(ttl_seconds=60)
def get_current_user(claims: Dict = Depends(Auth())):
    """Endpoint con caché de 60 segundos."""
    user_id = claims["sub"]
    # Lógica para obtener usuario
    return {"id": user_id, "email": "user@example.com"}
```

### Rate Limiting

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

# Aplicar al app
app.state.limiter = limiter

@app.post("/api/v1/auth/signin")
@limiter.limit("5/minute")  # Máx 5 intentos por minuto por IP
def signin(request: Request, payload: SignInRequest):
    # Lógica de signin
    pass
```

### Índices de Base de Datos

```sql
-- Índices compuestos para keyset pagination
CREATE INDEX idx_symptom_entries_pagination 
ON symptom_entries(tenant_id, patient_id, created_at DESC);

CREATE INDEX idx_predictions_pagination 
ON predictions(tenant_id, patient_id, created_at DESC);

-- Índice para bandeja de casos
CREATE INDEX idx_cases_bandeja 
ON cases(tenant_id, assigned_to, status, updated_at DESC);

-- Índice para auditoría
CREATE INDEX idx_audit_events 
ON audit_events(tenant_id, ts DESC);

-- Analizar planes de query
ANALYZE symptom_entries;
ANALYZE predictions;
ANALYZE cases;
ANALYZE audit_events;
```

---

## Monitoreo y Troubleshooting

### Logs y Observabilidad

```python
import logging
from logging.config import dictConfig

LOG_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "[%(asctime)s] %(levelname)s - %(name)s - %(message)s"
        },
        "json": {
            "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
            "format": "%(asctime)s %(name)s %(levelname)s %(message)s"
        }
    },
    "handlers": {
        "default": {
            "formatter": "default",
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout"
        },
        "file": {
            "formatter": "json",
            "class": "logging.handlers.RotatingFileHandler",
            "filename": "logs/app.log",
            "maxBytes": 10485760,  # 10MB
            "backupCount": 5
        }
    },
    "loggers": {
        "app": {
            "handlers": ["default", "file"],
            "level": "INFO"
        }
    }
}

dictConfig(LOG_CONFIG)
logger = logging.getLogger("app")
```

### Métricas de PostgreSQL

```sql
-- Conexiones activas
SELECT count(*) FROM pg_stat_activity WHERE state = 'active';

-- Índices no utilizados
SELECT schemaname, tablename, indexname 
FROM pg_stat_user_indexes 
WHERE idx_scan = 0;

-- Tamaño de tablas
SELECT schemaname, tablename, pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) 
FROM pg_tables 
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;

-- Queries lentas
SELECT query, calls, mean_exec_time, max_exec_time 
FROM pg_stat_statements 
WHERE mean_exec_time > 1000 
ORDER BY mean_exec_time DESC;
```

### Health Check Endpoint

```python
@app.get("/health", tags=["Health"])
def health_check(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Endpoint de salud para monitoreo."""
    try:
        # Verificar conexión a BD
        db.execute("SELECT 1")
        db_status = "healthy"
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"
    
    return {
        "status": "healthy" if db_status == "healthy" else "degraded",
        "database": db_status,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
```

### Common Issues & Fixes

| Problema | Causa | Solución |
|----------|-------|----------|
| **High latency p95 > 500ms** | Queries sin índices | Revisar `pg_stat_statements`, añadir índices compuestos |
| **Connection pool exhausted** | Demasiadas conexiones activas | Aumentar `pool_size` en SQLAlchemy, usar `pool_pre_ping=True` |
| **Memory leak en API** | Conexiones no cerradas | Asegurar `finally` blocks, usar context managers |
| **Rate limit errors** | Traffic burst | Implementar backoff exponencial en cliente |
| **JWT decode errors** | Token expirado | Verificar TTL, implementar refresh automático |
| **Duplicate records** | Reintentos sin idempotencia | Usar `Idempotency-Key` header |

---

## Checklist de Implementación

- [ ] Implementar `GET /api/v1/symptoms` con keyset pagination
- [ ] Implementar `POST /api/v1/auth/refresh` con validación de JWT
- [ ] Crear índices en PostgreSQL
- [ ] Configurar Docker Compose localmente
- [ ] Ejecutar migraciones de BD
- [ ] Generar datos de demostración
- [ ] Crear plan de pruebas JMeter
- [ ] Ejecutar Smoke Test (1 usuario)
- [ ] Ejecutar Load Test (10 usuarios)
- [ ] Ejecutar Stress Test (100 usuarios)
- [ ] Analizar métricas (p95, error rate, throughput)
- [ ] Implementar caché con Redis
- [ ] Configurar rate limiting
- [ ] Añadir logging estructurado
- [ ] Documentar endpoints en OpenAPI/Swagger
- [ ] Preparar deployment en AWS

---

## Referencias y Recursos

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [SQLAlchemy ORM](https://docs.sqlalchemy.org/)
- [Apache JMeter](https://jmeter.apache.org/)
- [PostgreSQL Performance](https://www.postgresql.org/docs/current/performance.html)
- [AWS Well-Architected Framework](https://aws.amazon.com/architecture/well-architected/)
- [OWASP API Security](https://owasp.org/www-project-api-security/)

---

**Documento actualizado:** Diciembre 2025  
**Versión:** 1.0  
**Autor:** AidDiag Engineering Team