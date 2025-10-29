from sqlalchemy import Column, String, Text, Boolean, Integer, ForeignKey, JSON, TIMESTAMP, func, Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid

from .db import Base

class Tenant(Base):
    __tablename__ = "tenants"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(Text, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

class Role(Base):
    __tablename__ = "roles"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), unique=True, nullable=False)
    description = Column(Text)

class User(Base):
    __tablename__ = "users"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    email = Column(String, nullable=False)
    hashed_password = Column(Text, nullable=False)
    mfa_enabled = Column(Boolean, default=False)
    mfa_secret = Column(Text, nullable=True)
    status = Column(String(20), default="active")
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

class UserRole(Base):
    __tablename__ = "user_roles"
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role_id = Column(Integer, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True)

class SymptomEntry(Base):
    __tablename__ = "symptom_entries"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    patient_id = Column(UUID(as_uuid=True), nullable=False)
    payload = Column(JSON, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

class Prediction(Base):
    __tablename__ = "predictions"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    patient_id = Column(UUID(as_uuid=True), nullable=False)
    symptom_entry_id = Column(UUID(as_uuid=True), ForeignKey("symptom_entries.id"), nullable=False)
    model_version = Column(String, nullable=False)
    score = Column(Numeric(6,5), nullable=False)
    label = Column(String, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

class Case(Base):
    __tablename__ = "cases"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    patient_id = Column(UUID(as_uuid=True), nullable=False)
    assigned_to = Column(UUID(as_uuid=True), nullable=True)
    status = Column(String(20), nullable=False, default="open")
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

class AuditEvent(Base):
    __tablename__ = "audit_events"
    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(UUID(as_uuid=True), nullable=False)
    actor_sub = Column(UUID(as_uuid=True), nullable=False)
    action = Column(Text, nullable=False)
    entity = Column(Text, nullable=False)
    entity_id = Column(Text, nullable=True)
    ts = Column(TIMESTAMP(timezone=True), server_default=func.now())
    meta = Column(JSON, nullable=True)