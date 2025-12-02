from __future__ import annotations

import os
from typing import Any, Dict

import pytest
import requests
from pytest_bdd import given, scenario, then, when


API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")


@scenario("features/auth.feature", "Login con credenciales válidas")
def test_login_valido() -> None:
    """Escenario BDD: Login con credenciales válidas."""


@scenario("features/auth.feature", "Refresh de token válido")
def test_refresh_valido() -> None:
    """Escenario BDD: Refresh de token válido."""


@pytest.fixture
def context() -> Dict[str, Any]:
    """Contenedor simple para compartir datos entre pasos."""

    return {}


@given("un usuario demo existente")
def usuario_demo() -> None:
    """Supone que el usuario de demo ya fue sembrado (seed_demo.py)."""

    # No-op: se asume ambiente semillado; si no, este paso debe crear el usuario.
    return None


@when(
    'hago POST a "/api/v1/auth/signin" con email "patient@demo.local" y password "Patient123!"',
)
def post_signin(context: Dict[str, Any]) -> None:
    response = requests.post(
        f"{API_BASE_URL}/api/v1/auth/signin",
        json={"email": "patient@demo.local", "password": "Patient123!"},
        timeout=10,
    )
    context["response"] = response


@when(
    'hago POST a "/api/v1/auth/refresh" con el token obtenido',
)
def post_refresh(context: Dict[str, Any]) -> None:
    token = context.get("token")
    assert token, "Se esperaba un token previo en el contexto"
    response = requests.post(
        f"{API_BASE_URL}/api/v1/auth/refresh",
        json={"refresh_token": token},
        timeout=10,
    )
    context["response"] = response


@given(
    'obtengo un token con email "patient@demo.local" y password "Patient123!"',
)
def obtener_token(context: Dict[str, Any]) -> None:
    response = requests.post(
        f"{API_BASE_URL}/api/v1/auth/signin",
        json={"email": "patient@demo.local", "password": "Patient123!"},
        timeout=10,
    )
    assert response.status_code == 200, f"Signin falló: {response.text}"
    token = response.json().get("token")
    assert token, "El response no contiene token"
    context["token"] = token


@then("la respuesta tiene código 200")
def respuesta_200(context: Dict[str, Any]) -> None:
    response = context.get("response")
    assert response is not None, "No hay response en contexto"
    assert response.status_code == 200, f"Código inesperado: {response.status_code}, body: {response.text}"


@then('la respuesta contiene un campo "token"')
def respuesta_contiene_token(context: Dict[str, Any]) -> None:
    response = context.get("response")
    assert response is not None, "No hay response en contexto"
    body = response.json()
    assert "token" in body and body["token"], f"No se encontró token en body: {body}"
    context["token"] = body["token"]
