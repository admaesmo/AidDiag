import random
from decimal import Decimal
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from uuid import UUID

from .db import Base, engine, get_db
from . import models, schemas
from .auth import Auth

app = FastAPI(title="AidDiag API (Local MVP)", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

Base.metadata.create_all(bind=engine)

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/jwks.json")
def jwks():
    import json
    with open("app/static/jwks.json", "r") as f:
        return json.load(f)

@app.post("/api/v1/symptoms", response_model=schemas.SymptomEntryCreated, status_code=201, dependencies=[Depends(Auth())])
def create_symptoms(body: schemas.SymptomEntryRequest, db: Session = Depends(get_db)):
    se = models.SymptomEntry(
        tenant_id=body.tenant_id,
        patient_id=body.patient_id,
        payload=body.payload,
    )
    db.add(se)
    db.commit()
    db.refresh(se)
    return {"id": se.id, "created_at": se.created_at}

@app.post("/api/v1/predict", response_model=schemas.Prediction, dependencies=[Depends(Auth())])
def predict(body: schemas.PredictRequest, db: Session = Depends(get_db)):
    score = round(random.random(), 5)
    label = "POS" if score > 0.5 else "NEG"
    pred = models.Prediction(
        tenant_id=body.tenant_id,
        patient_id=body.patient_id,
        symptom_entry_id=body.symptom_entry_id,
        model_version=body.model_version,
        score=Decimal(str(score)),
        label=label,
    )
    db.add(pred)
    db.commit()
    db.refresh(pred)
    return {
        "id": pred.id,
        "tenant_id": pred.tenant_id,
        "patient_id": pred.patient_id,
        "symptom_entry_id": pred.symptom_entry_id,
        "model_version": pred.model_version,
        "score": float(pred.score),
        "label": pred.label,
        "created_at": pred.created_at,
    }

@app.get("/api/v1/predictions")
def list_predictions(patient_id: UUID, limit: int = 20, offset: int = 0, db: Session = Depends(get_db), claims=Depends(Auth())):
    q = db.query(models.Prediction).filter(
        models.Prediction.tenant_id == UUID(claims["tenant_id"]),
        models.Prediction.patient_id == patient_id
    )
    total = q.count()
    items = q.order_by(models.Prediction.created_at.desc()).limit(limit).offset(offset).all()
    def to_dict(p):
        return {
            "id": str(p.id), "tenant_id": str(p.tenant_id), "patient_id": str(p.patient_id),
            "symptom_entry_id": str(p.symptom_entry_id), "model_version": p.model_version,
            "score": float(p.score), "label": p.label, "created_at": p.created_at.isoformat()
        }
    return {"items": [to_dict(p) for p in items], "total": total}

@app.get("/api/v1/cases", dependencies=[Depends(Auth(required_roles=["Profesional","Admin"]))])
def list_cases(assigned_to: UUID, status: str = "open", db: Session = Depends(get_db), claims=Depends(Auth())):
    q = db.query(models.Case).filter(
        models.Case.tenant_id == UUID(claims["tenant_id"]),
        models.Case.assigned_to == assigned_to,
        models.Case.status == status
    ).order_by(models.Case.updated_at.desc())
    items = q.all()
    def to_dict(c):
        return {
            "id": str(c.id), "tenant_id": str(c.tenant_id), "patient_id": str(c.patient_id),
            "assigned_to": str(c.assigned_to) if c.assigned_to else None,
            "status": c.status, "updated_at": c.updated_at.isoformat(), "created_at": c.created_at.isoformat()
        }
    return {"items": [to_dict(c) for c in items], "total": len(items)}

@app.patch("/api/v1/cases/{case_id}", response_model=schemas.Case, dependencies=[Depends(Auth(required_roles=["Profesional","Admin"]))])
def patch_case(case_id: UUID, body: schemas.CasePatch, db: Session = Depends(get_db), claims=Depends(Auth())):
    case = db.get(models.Case, case_id)
    if not case or str(case.tenant_id) != claims["tenant_id"]:
        raise HTTPException(status_code=404, detail="Case not found")
    case.status = body.status
    db.add(case)
    db.commit()
    db.refresh(case)
    return {
        "id": case.id, "tenant_id": case.tenant_id, "patient_id": case.patient_id,
        "assigned_to": case.assigned_to, "status": case.status,
        "updated_at": case.updated_at, "created_at": case.created_at
    }

@app.post("/api/v1/audit/events", status_code=201, dependencies=[Depends(Auth())])
def audit_event(body: schemas.AuditEventCreate, db: Session = Depends(get_db), claims=Depends(Auth())):
    evt = models.AuditEvent(
        tenant_id=body.tenant_id,
        actor_sub=claims["sub"],
        action=body.action,
        entity=body.entity,
        entity_id=body.entity_id,
        meta=body.meta
    )
    db.add(evt)
    db.commit()
    return {"id": evt.id, "ts": evt.ts}
