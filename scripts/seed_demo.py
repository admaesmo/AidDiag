"""Seed the local database with demo data for the AidDiag MVP."""

from __future__ import annotations

import os
import sys
from typing import Dict

import hashlib

try:  # pragma: no cover
    import bcrypt  # type: ignore
except ImportError:  # pragma: no cover
    bcrypt = None

ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
if ROOT_DIR not in sys.path:
    sys.path.append(ROOT_DIR)

from app import models  # noqa: E402
from app.db import SessionLocal  # noqa: E402

DEFAULT_TENANT_NAME = os.getenv("DEFAULT_TENANT_NAME", "demo")

USERS_TO_CREATE = [
    {"email": os.getenv("ADMIN_EMAIL", "admin@demo.local"), "password": os.getenv("ADMIN_PASSWORD", "Admin123!"), "role": "Admin"},
    {"email": os.getenv("PROF_EMAIL", "pro@demo.local"), "password": os.getenv("PROF_PASSWORD", "Pro123!"), "role": "Profesional"},
    {"email": os.getenv("PATIENT_EMAIL", "patient@demo.local"), "password": os.getenv("PATIENT_PASSWORD", "Patient123!"), "role": "Paciente"},
]


_FALLBACK_PREFIX = "sha256$"


def _hash_password(password: str) -> str:
    if bcrypt is None:
        digest = hashlib.sha256(password.encode("utf-8")).hexdigest()
        return f"{_FALLBACK_PREFIX}{digest}"
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def main() -> None:
    session = SessionLocal()
    try:
        tenant = session.query(models.Tenant).filter(models.Tenant.name == DEFAULT_TENANT_NAME).first()
        if not tenant:
            tenant = models.Tenant(name=DEFAULT_TENANT_NAME)
            session.add(tenant)
            session.commit()
            session.refresh(tenant)
            print(f"Created tenant '{tenant.name}' ({tenant.id})")
        else:
            print(f"Using existing tenant '{tenant.name}' ({tenant.id})")

        role_names = ["Paciente", "Profesional", "Admin"]
        roles: Dict[str, models.Role] = {}
        for role_name in role_names:
            role = session.query(models.Role).filter(models.Role.name == role_name).first()
            if not role:
                role = models.Role(name=role_name, description=f"Rol {role_name}")
                session.add(role)
                session.commit()
                session.refresh(role)
                print(f"Created role {role.name}")
            roles[role_name] = role

        created_users: Dict[str, models.User] = {}
        for user_data in USERS_TO_CREATE:
            existing = (
                session.query(models.User)
                .filter(models.User.tenant_id == tenant.id, models.User.email == user_data["email"])
                .first()
            )
            if existing:
                print(f"User {existing.email} already exists (id={existing.id})")
                created_users[user_data["role"]] = existing
                continue
            user = models.User(
                tenant_id=tenant.id,
                email=user_data["email"],
                hashed_password=_hash_password(user_data["password"]),
            )
            user.roles.append(roles[user_data["role"]])
            session.add(user)
            session.commit()
            session.refresh(user)
            created_users[user_data["role"]] = user
            print(f"Created user {user.email} ({user.roles[0].name}) id={user.id}")

        prof_user = created_users.get("Profesional")
        patient_user = created_users.get("Paciente")
        if prof_user and patient_user:
            existing_case = (
                session.query(models.Case)
                .filter(
                    models.Case.tenant_id == tenant.id,
                    models.Case.assigned_to == prof_user.id,
                    models.Case.patient_id == patient_user.id,
                )
                .first()
            )
            if not existing_case:
                case = models.Case(
                    tenant_id=tenant.id,
                    patient_id=patient_user.id,
                    assigned_to=prof_user.id,
                    status="open",
                )
                session.add(case)
                session.commit()
                print(f"Created demo case {case.id}")
            else:
                print(f"Demo case already exists ({existing_case.id})")

        session.commit()
        print("Seed completed.")
    finally:
        session.close()
if __name__ == "__main__":
    main()
