"""Pydantic schemas for the AidDiag API."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class BaseModelConfig(BaseModel):
    """Base configuration to enable ORM mode for SQLAlchemy models."""

    model_config = {"from_attributes": True, "protected_namespaces": ()}


class RoleOut(BaseModelConfig):
    id: int
    name: str
    description: Optional[str] = None


class UserOut(BaseModelConfig):
    id: UUID
    tenant_id: UUID
    email: str
    roles: List[RoleOut] = Field(default_factory=list)
    mfa_enabled: bool
    status: str
    created_at: datetime


class SignUpRequest(BaseModel):
    email: str = Field(
        ..., description="Email del usuario a registrar", pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
    )
    password: str = Field(..., min_length=8, description="Contraseña para el login local")
    role: str = Field(
        default="Paciente",
        description="Rol inicial asignado al usuario (Paciente por defecto)",
    )


class SignInPasswordRequest(BaseModel):
    email: str = Field(..., pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str


class SignInOIDCRequest(BaseModel):
    id_token: str
    access_token: str


class AssignRoleRequest(BaseModel):
    user_id: UUID
    role: str = Field(..., description="Nombre del rol a asignar")


class EnableMFARequest(BaseModel):
    user_id: Optional[UUID] = Field(
        default=None, description="Usuario al que se habilita MFA (por defecto, el propio)"
    )


class PasswordResetRequest(BaseModel):
    email: str = Field(..., pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    new_password: str = Field(..., min_length=8)


class AuthToken(BaseModel):
    token: str
    token_type: str = "Bearer"
    expires_at: datetime


class MeOut(BaseModelConfig):
    user: UserOut
    scopes: List[str]


class SymptomEntryRequest(BaseModel):
    tenant_id: Optional[UUID] = Field(
        default=None,
        description="Tenant asociado a la entrada (se valida contra el token)",
    )
    patient_id: UUID
    payload: dict


class SymptomEntryCreated(BaseModel):
    id: UUID
    created_at: datetime


class PredictRequest(BaseModel):
    tenant_id: Optional[UUID] = Field(
        default=None,
        description="Tenant asociado a la predicción (se valida contra el token)",
    )
    patient_id: UUID
    symptom_entry_id: UUID
    model_version: str = "v1"

    model_config = {"protected_namespaces": ()}


class Prediction(BaseModel):
    id: UUID
    tenant_id: UUID
    patient_id: UUID
    symptom_entry_id: UUID
    model_version: str
    score: float
    label: str
    created_at: datetime

    model_config = {"protected_namespaces": ()}


class PredictionList(BaseModel):
    total: int
    items: List[Prediction]


class CasePatch(BaseModel):
    status: str = Field(pattern="^(open|in_progress|closed)$")


class Case(BaseModel):
    id: UUID
    tenant_id: UUID
    patient_id: UUID
    assigned_to: Optional[UUID] = None
    status: str
    updated_at: datetime
    created_at: datetime


class CaseList(BaseModel):
    total: int
    items: List[Case]


class AuditEventCreate(BaseModel):
    tenant_id: Optional[UUID] = Field(
        default=None,
        description="Tenant de la acción (se sobrescribe con el del token)",
    )
    action: str
    entity: str
    entity_id: Optional[str] = None
    meta: Optional[dict] = None


class AuditEventCreated(BaseModel):
    id: int
    ts: datetime

