# Guía de Implementación de Endpoints de Alta Transaccionalidad para AidDiag

Esta guía proporciona los pasos detallados para implementar los dos *endpoints* identificados como faltantes en el repositorio de AidDiag, basándose en el documento "AidDiag — Endpoints de Alta Transaccionalidad":

1.  **`GET /api/v1/symptoms`**: Para la lectura paginada de entradas de síntomas (Endpoint 9).
2.  **`POST /api/v1/auth/refresh`**: Para la renovación de tokens de autenticación (Endpoint 10).

## 1. Implementación de `GET /api/v1/symptoms` (Lectura Paginada)

Este *endpoint* se implementará en `AidDiag/app/main.py` para listar las entradas de síntomas de un paciente, utilizando la **paginación por cursor (keyset pagination)** recomendada en el documento para alta transaccionalidad.

### Paso 1.1: Actualizar `AidDiag/app/schemas.py`

Necesitas definir el esquema de salida para la lista de entradas de síntomas.

**Acción:** Edita el archivo `AidDiag/app/schemas.py` y añade el siguiente código al final del archivo:

```python
# ... (código existente)

class SymptomEntry(BaseModel):
    id: UUID
    tenant_id: UUID
    patient_id: UUID
    symptoms: Dict[str, Any]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class SymptomEntryList(BaseModel):
    total: int
    items: List[SymptomEntry]
    next_cursor: Optional[datetime] = None
```

### Paso 1.2: Implementar el *Endpoint* en `AidDiag/app/main.py`

**Acción:** Edita el archivo `AidDiag/app/main.py` y añade la siguiente función justo después de la función `create_symptom_entry` (que maneja el `POST /api/v1/symptoms`):

```python
# ... (código existente)

@app.get(
    "/api/v1/symptoms",
    response_model=schemas.SymptomEntryList,
    status_code=status.HTTP_200_OK,
)
def list_symptom_entries(
    patient_id: UUID,
    limit: int = Query(20, ge=1, le=100),
    cursor: Optional[datetime] = Query(None, description="Timestamp para paginación por cursor (keyset)"),
    db: Session = Depends(get_db),
    claims: Dict[str, Any] = Depends(Auth()),
) -> schemas.SymptomEntryList:
    """
    Retorna el historial de entradas de síntomas para un paciente, utilizando paginación por cursor.
    """
    tenant_id = UUID(claims["tenant_id"])
    
    # 1. Consulta base: filtrar por tenant_id y patient_id
    query = (
        db.query(models.SymptomEntry)
        .filter(
            models.SymptomEntry.tenant_id == tenant_id,
            models.SymptomEntry.patient_id == patient_id,
        )
    )
    
    # 2. Aplicar filtro de cursor para keyset pagination
    if cursor:
        query = query.filter(models.SymptomEntry.created_at < cursor)
        
    # 3. Ordenar por fecha de creación descendente
    query = query.order_by(models.SymptomEntry.created_at.desc())
    
    # 4. Obtener el total (se puede optimizar para no contar en cada request de alta transaccionalidad)
    # Para esta implementación, mantenemos el total para consistencia con otros endpoints.
    total = query.count()
    
    # 5. Aplicar límite + 1 para determinar si hay más páginas
    items = query.limit(limit + 1).all()
    
    # 6. Determinar el siguiente cursor
    next_cursor = None
    if len(items) > limit:
        next_cursor = items[limit - 1].created_at
        items = items[:limit] # Truncar la lista al límite
        
    result = [schemas.SymptomEntry.model_validate(item) for item in items]
    
    return schemas.SymptomEntryList(total=total, items=result, next_cursor=next_cursor)
```

## 2. Implementación de `POST /api/v1/auth/refresh` (Renovación de Token)

Este *endpoint* se implementará en `AidDiag/app/routers/auth.py` para emitir un nuevo token de acceso.

### Paso 2.1: Actualizar `AidDiag/app/schemas.py`

Necesitas definir el esquema de entrada para la solicitud de renovación de token.

**Acción:** Edita el archivo `AidDiag/app/schemas.py` y añade la siguiente clase junto a los otros esquemas de autenticación (ej. `SignInPasswordRequest`):

```python
# ... (código existente)

class RefreshTokenRequest(BaseModel):
    refresh_token: str
```

### Paso 2.2: Implementar el *Endpoint* en `AidDiag/app/routers/auth.py`

**Acción:** Edita el archivo `AidDiag/app/routers/auth.py`.

1.  **Importar `timedelta`**: Asegúrate de que `timedelta` esté importado. Si no lo está, añade:
    ```python
    from datetime import datetime, timezone, timedelta # Asegúrate de que timedelta esté aquí
    ```

2.  **Añadir la función `refresh_token`**: Añade la siguiente función después de `signin` y antes de `assign_role`:

```python
# ... (código existente)

@router.post("/auth/refresh", response_model=schemas.AuthToken)
def refresh_token(
    payload: schemas.RefreshTokenRequest,
    db: Session = Depends(get_db),
) -> schemas.AuthToken:
    """
    Emite un nuevo token de acceso a partir de un token de refresco válido.
    
    NOTA: En un sistema real, el token de refresco debe ser validado contra una 
    base de datos o un servicio de autenticación (ej. Cognito) para asegurar 
    que no ha sido revocado. Aquí se simula la lógica de emisión de un nuevo token.
    """
    try:
        # Simulación de validación: Decodificar el token de refresco.
        # En un sistema real, el token de refresco tendría un 'scope' o 'type' diferente
        # y se validaría su existencia en la DB.
        claims = decode_jwt(payload.refresh_token)
        user_id = UUID(claims["sub"])
        tenant_id = UUID(claims["tenant_id"])
        role_name = claims["role"]
        
        # 1. Buscar el usuario
        user = db.get(models.User, user_id)
        if not user or user.tenant_id != tenant_id:
            raise HTTPException(status_code=401, detail="Invalid refresh token or user not found")
            
        # 2. Emitir un nuevo token de acceso (con un tiempo de expiración corto)
        # Reutilizamos la función interna _issue_local_token
        return _issue_local_token(user, role_name)
        
    except Exception as e:
        # Capturar errores de decodificación de JWT (token expirado, inválido, etc.)
        raise HTTPException(status_code=401, detail=f"Invalid or expired refresh token: {e}")
```

## 3. Configuración de Docker para Despliegue Local

El repositorio ya incluye una configuración de Docker robusta (`Dockerfile` y `docker-compose.yml`). No se requieren cambios en estos archivos para el despliegue local de los nuevos *endpoints*.

### Paso 3.1: Construir y Ejecutar el Contenedor

**Acción:** Abre una terminal en el directorio raíz de tu proyecto (`AidDiag/`) y ejecuta los siguientes comandos:

1.  **Construir las imágenes de Docker:**
    ```bash
    docker-compose build
    ```

2.  **Iniciar los servicios (Base de Datos y Aplicación):**
    ```bash
    docker-compose up
    ```

El servicio de la aplicación (`app`) realizará automáticamente las migraciones de la base de datos (`alembic upgrade head`) y sembrará datos de demostración (`python scripts/seed_demo.py`) antes de iniciar el servidor Uvicorn.

### Paso 3.2: Acceder a la API

Una vez que los contenedores estén en funcionamiento, la API estará disponible en:

*   **URL Base:** `http://localhost:8000`

Puedes probar los nuevos *endpoints* con herramientas como Postman o cURL:

| Endpoint | Método | Descripción |
| :--- | :--- | :--- |
| `/api/v1/auth/refresh` | `POST` | Renueva un token de acceso. Requiere un `refresh_token` en el cuerpo. |
| `/api/v1/symptoms` | `GET` | Lista entradas de síntomas. Requiere `patient_id` como parámetro de consulta y un token de acceso válido. |

**Ejemplo de `GET /api/v1/symptoms` (asumiendo que tienes un token de acceso válido):**

```bash
curl -X 'GET' \
  'http://localhost:8000/api/v1/symptoms?patient_id=UUID_DEL_PACIENTE&limit=10' \
  -H 'accept: application/json' \
  -H 'Authorization: Bearer TU_ACCESS_TOKEN'
```

---

**¡Listo!** Con estos pasos, habrás implementado los *endpoints* faltantes y tendrás tu aplicación lista para ser desplegada y probada localmente con Docker.
