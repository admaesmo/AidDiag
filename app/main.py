"""FastAPI application entry point."""

from __future__ import annotations

import json
import random
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from . import models, schemas
from .auth import Auth, require_roles
from .db import get_db
from .routers.auth import router as auth_router


app = FastAPI(title="AidDiag API (Local MVP)", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api/v1")


@app.get("/health")
def health() -> Dict[str, str]:
    """Simple health check endpoint."""

    return {"status": "ok"}


@app.get("/jwks.json")
def jwks() -> Dict[str, Any]:
    """Serve the JWKS used to verify locally issued tokens."""

    with open("app/static/jwks.json", "r", encoding="utf-8") as handler:
        return json.load(handler)


@app.post(
    "/api/v1/symptoms",
    response_model=schemas.SymptomEntryCreated,
    status_code=status.HTTP_201_CREATED,
)
def create_symptoms(
    body: schemas.SymptomEntryRequest,
    db: Session = Depends(get_db),
    claims: Dict[str, Any] = Depends(Auth()),
) -> schemas.SymptomEntryCreated:
    """Persist a symptom entry for the authenticated tenant."""

    tenant_id = UUID(claims["tenant_id"])
    if body.tenant_id and body.tenant_id != tenant_id:
        raise HTTPException(status_code=400, detail="Tenant mismatch")

    symptom_entry = models.SymptomEntry(
        tenant_id=tenant_id,
        patient_id=body.patient_id,
        payload=body.payload,
    )
    db.add(symptom_entry)
    db.commit()
    db.refresh(symptom_entry)
    return schemas.SymptomEntryCreated.model_validate(symptom_entry)


@app.get(
    "/api/v1/symptoms",
    response_model=schemas.SymptomEntryList,
    status_code=status.HTTP_200_OK,
)
def list_symptom_entries(
    patient_id: UUID,
    limit: int = Query(20, ge=1, le=100),
    cursor: Optional[datetime] = Query(
        None, description="Timestamp para paginacion por cursor (keyset)"
    ),
    db: Session = Depends(get_db),
    claims: Dict[str, Any] = Depends(Auth()),
) -> schemas.SymptomEntryList:
    """Return paginated symptom entries for a patient using cursor pagination."""

    tenant_id = UUID(claims["tenant_id"])

    query = (
        db.query(models.SymptomEntry)
        .filter(
            models.SymptomEntry.tenant_id == tenant_id,
            models.SymptomEntry.patient_id == patient_id,
        )
    )

    if cursor:
        query = query.filter(models.SymptomEntry.created_at < cursor)

    query = query.order_by(models.SymptomEntry.created_at.desc())

    total = query.count()
    items = query.limit(limit + 1).all()

    next_cursor = None
    if len(items) > limit:
        next_cursor = items[limit - 1].created_at
        items = items[:limit]

    result = [
        schemas.SymptomEntry(
            id=item.id,
            tenant_id=item.tenant_id,
            patient_id=item.patient_id,
            symptoms=item.payload,
            created_at=item.created_at,
        )
        for item in items
    ]

    return schemas.SymptomEntryList(total=total, items=result, next_cursor=next_cursor)


@app.post(
    "/api/v1/predict",
    response_model=schemas.Prediction,
    status_code=status.HTTP_200_OK,
)
def predict(
    body: schemas.PredictRequest,
    db: Session = Depends(get_db),
    claims: Dict[str, Any] = Depends(Auth()),
) -> schemas.Prediction:
    """Generate a dummy prediction, persist it and audit the call."""

    tenant_id = UUID(claims["tenant_id"])
    if body.tenant_id and body.tenant_id != tenant_id:
        raise HTTPException(status_code=400, detail="Tenant mismatch")

    # Ensure the symptom entry belongs to the same tenant
    symptom_entry = db.get(models.SymptomEntry, body.symptom_entry_id)
    if not symptom_entry or symptom_entry.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Symptom entry not found")
    if symptom_entry.patient_id != body.patient_id:
        raise HTTPException(status_code=400, detail="Patient mismatch")

    score = round(random.random(), 5)
    label = "POS" if score > 0.5 else "NEG"

    prediction = models.Prediction(
        tenant_id=tenant_id,
        patient_id=body.patient_id,
        symptom_entry_id=body.symptom_entry_id,
        model_version=body.model_version,
        score=Decimal(str(score)),
        label=label,
    )
    db.add(prediction)
    db.flush()

    audit_event = models.AuditEvent(
        tenant_id=tenant_id,
        actor_sub=UUID(claims["sub"]),
        action="predict",
        entity="prediction",
        entity_id=str(prediction.id),
        meta={
            "model_version": body.model_version,
            "score": score,
            "label": label,
        },
    )
    db.add(audit_event)
    db.commit()
    db.refresh(prediction)

    return schemas.Prediction(
        id=prediction.id,
        tenant_id=prediction.tenant_id,
        patient_id=prediction.patient_id,
        symptom_entry_id=prediction.symptom_entry_id,
        model_version=prediction.model_version,
        score=float(prediction.score),
        label=prediction.label,
        created_at=prediction.created_at,
    )


@app.get(
    "/api/v1/predictions",
    response_model=schemas.PredictionList,
    status_code=status.HTTP_200_OK,
)
def list_predictions(
    patient_id: UUID,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    claims: Dict[str, Any] = Depends(Auth()),
) -> schemas.PredictionList:
    """Return the prediction history for a patient within the tenant."""

    tenant_id = UUID(claims["tenant_id"])
    query = (
        db.query(models.Prediction)
        .filter(
            models.Prediction.tenant_id == tenant_id,
            models.Prediction.patient_id == patient_id,
        )
        .order_by(models.Prediction.created_at.desc())
    )
    total = query.count()
    items = query.limit(limit).offset(offset).all()
    result = [
        schemas.Prediction(
            id=item.id,
            tenant_id=item.tenant_id,
            patient_id=item.patient_id,
            symptom_entry_id=item.symptom_entry_id,
            model_version=item.model_version,
            score=float(item.score),
            label=item.label,
            created_at=item.created_at,
        )
        for item in items
    ]
    return schemas.PredictionList(total=total, items=result)


@app.get(
    "/api/v1/cases",
    response_model=schemas.CaseList,
)
def list_cases(
    assigned_to: UUID,
    status_filter: str = Query("open"),
    db: Session = Depends(get_db),
    claims: Dict[str, Any] = Depends(require_roles("Profesional", "Admin")),
) -> schemas.CaseList:
    """List cases assigned to a professional within the tenant."""

    tenant_id = UUID(claims["tenant_id"])
    query = (
        db.query(models.Case)
        .filter(
            models.Case.tenant_id == tenant_id,
            models.Case.assigned_to == assigned_to,
            models.Case.status == status_filter,
        )
        .order_by(models.Case.updated_at.desc())
    )
    items = query.all()
    return schemas.CaseList(total=len(items), items=[schemas.Case.model_validate(item) for item in items])


@app.patch(
    "/api/v1/cases/{case_id}",
    response_model=schemas.Case,
)
def patch_case(
    case_id: UUID,
    body: schemas.CasePatch,
    db: Session = Depends(get_db),
    claims: Dict[str, Any] = Depends(require_roles("Profesional", "Admin")),
) -> schemas.Case:
    """Update the status of a case belonging to the tenant."""

    tenant_id = UUID(claims["tenant_id"])
    case = db.get(models.Case, case_id)
    if not case or case.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Case not found")

    case.status = body.status
    db.add(case)
    db.commit()
    db.refresh(case)
    return schemas.Case.model_validate(case)


@app.post(
    "/api/v1/audit/events",
    response_model=schemas.AuditEventCreated,
    status_code=status.HTTP_201_CREATED,
)
def audit_event(
    body: schemas.AuditEventCreate,
    db: Session = Depends(get_db),
    claims: Dict[str, Any] = Depends(Auth()),
) -> schemas.AuditEventCreated:
    """Persist an audit event for the tenant."""

    tenant_id = UUID(claims["tenant_id"])
    if body.tenant_id and body.tenant_id != tenant_id:
        raise HTTPException(status_code=400, detail="Tenant mismatch")

    event = models.AuditEvent(
        tenant_id=tenant_id,
        actor_sub=UUID(claims["sub"]),
        action=body.action,
        entity=body.entity,
        entity_id=body.entity_id,
        meta=body.meta,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return schemas.AuditEventCreated(id=event.id, ts=event.ts)

