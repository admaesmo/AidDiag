# scripts/make_jwt.py
import json, os, uuid
from datetime import datetime, timedelta, timezone
from jose import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend
from jose.utils import base64url_encode

ISSUER = os.getenv("JWT_ISSUER", "http://localhost:8000")
AUDIENCE = os.getenv("JWT_AUDIENCE", "aiddiag-api")
PRIV_PATH = os.getenv("JWT_PRIVATE_KEY_PATH", "app/static/private.pem")
JWKS_PATH = os.getenv("JWT_PUBLIC_JWKS_PATH", "app/static/jwks.json")

# 1) Generar/leer par de claves
os.makedirs(os.path.dirname(PRIV_PATH), exist_ok=True)
if not os.path.exists(PRIV_PATH):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())
    with open(PRIV_PATH, "wb") as f:
        f.write(
            key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,  # o PKCS8
                encryption_algorithm=serialization.NoEncryption(),
            )
        )
else:
    with open(PRIV_PATH, "rb") as f:
        key = serialization.load_pem_private_key(f.read(), password=None, backend=default_backend())

pub = key.public_key()

# 2) Construir JWKS (n, e) y guardarlo
numbers = pub.public_numbers()
n_b64 = base64url_encode(numbers.n.to_bytes((numbers.n.bit_length() + 7)//8, "big")).decode()
e_b64 = base64url_encode(numbers.e.to_bytes((numbers.e.bit_length() + 7)//8, "big")).decode()

KID = os.getenv("JWT_KID", "local-rs256")
jwks = {"keys": [{"kty": "RSA", "use": "sig", "alg": "RS256", "kid": KID, "n": n_b64, "e": e_b64}]}
os.makedirs(os.path.dirname(JWKS_PATH), exist_ok=True)
with open(JWKS_PATH, "w") as f:
    json.dump(jwks, f)

# 3) Claims del token
now = datetime.now(timezone.utc)
claims = {
    "iss": ISSUER,
    "aud": AUDIENCE,
    "iat": int(now.timestamp()),
    "exp": int((now + timedelta(hours=1)).timestamp()),
    "sub": str(uuid.uuid4()),
    "tenant_id": "00000000-0000-0000-0000-000000000000",
    "role": os.getenv("JWT_ROLE", "Profesional"),
    "scope": "api.read api.write",
}

# 4) **IMPORTANTE**: serializar la clave privada a PEM (bytes) para python-jose
private_pem = key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.TraditionalOpenSSL,  # o PKCS8
    encryption_algorithm=serialization.NoEncryption(),
)

# 5) Firmar el JWT con RS256
token = jwt.encode(claims, private_pem, algorithm="RS256", headers={"kid": KID})
print(token)

