from pydantic import BaseModel, Field
from typing import Optional
from uuid import UUID
from datetime import datetime

class SymptomEntryRequest(BaseModel):
    tenant_id: UUID
    patient_id: UUID
    payload: dict

class PredictRequest(BaseModel):
    tenant_id: UUID
    patient_id: UUID
    symptom_entry_id: UUID
    model_version: str = "v1"

class CasePatch(BaseModel):
    status: str = Field(pattern="^(open|in_progress|closed)$")

class AuditEventCreate(BaseModel):
    tenant_id: UUID
    action: str
    entity: str
    entity_id: Optional[str] = None
    meta: Optional[dict] = None

class SymptomEntryCreated(BaseModel):
    id: UUID
    created_at: datetime

class Prediction(BaseModel):
    id: UUID
    tenant_id: UUID
    patient_id: UUID
    symptom_entry_id: UUID
    model_version: str
    score: float
    label: str
    created_at: datetime

class Case(BaseModel):
    id: UUID
    tenant_id: UUID
    patient_id: UUID
    assigned_to: Optional[UUID] = None
    status: str
    updated_at: datetime
    created_at: datetime
