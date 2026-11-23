#!/usr/bin/env python3
"""
Security primitives for the Auth Service.

Provides TOTP 2FA helpers (secret generation, encrypted-at-rest storage, QR
provisioning, verification), recovery-code generation/verification, opaque token
hashing for refresh and email tokens, and password-strength policy.
"""

import base64
import hashlib
import hmac
import io
import logging
import os
import secrets
from typing import List, Tuple

import pyotp
import qrcode
from cryptography.fernet import Fernet, InvalidToken
from qrcode.image.pil import PilImage

logger = logging.getLogger("auth")

# ==============================================================================
# TOTP SECRET ENCRYPTION (Fernet)
# ==============================================================================
# TOTP secrets are encrypted at rest so a database read does not expose the
# second factor. The key is REQUIRED; the service refuses to start without it.
_TOTP_KEY = os.getenv("TOTP_ENCRYPTION_KEY", "").strip()
if not _TOTP_KEY:
    raise RuntimeError(
        "TOTP_ENCRYPTION_KEY must be set. Generate one with: "
        'python -c "from cryptography.fernet import Fernet; '
        'print(Fernet.generate_key().decode())"'
    )
try:
    _fernet = Fernet(_TOTP_KEY.encode())
except Exception as exc:  # pragma: no cover - configuration error
    raise RuntimeError(f"TOTP_ENCRYPTION_KEY is not a valid Fernet key: {exc}")

TOTP_ISSUER = os.getenv("TOTP_ISSUER", "Congressional Disclosures")
TOTP_DIGITS = 6
TOTP_INTERVAL = 30
# Accept +/- 1 time step to tolerate clock skew between server and authenticator.
TOTP_VALID_WINDOW = 1

RECOVERY_CODE_COUNT = int(os.getenv("RECOVERY_CODE_COUNT", "10"))


def encrypt_secret(plaintext: str) -> str:
    """Encrypt a TOTP secret for storage."""
    return _fernet.encrypt(plaintext.encode()).decode()


def decrypt_secret(ciphertext: str) -> str:
    """Decrypt a stored TOTP secret."""
    try:
        return _fernet.decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise ValueError("Could not decrypt TOTP secret") from exc


def generate_totp_secret() -> str:
    """Generate a new base32 TOTP secret."""
    return pyotp.random_base32()


def build_otpauth_uri(secret: str, account_name: str) -> str:
    """Build the otpauth:// URI consumed by authenticator apps."""
    return pyotp.TOTP(
        secret, digits=TOTP_DIGITS, interval=TOTP_INTERVAL
    ).provisioning_uri(name=account_name, issuer_name=TOTP_ISSUER)


def qr_png_base64(otpauth_uri: str) -> str:
    """Render the otpauth URI as a base64-encoded PNG QR code."""
    qr = qrcode.QRCode(box_size=6, border=2)
    qr.add_data(otpauth_uri)
    qr.make(fit=True)
    image = qr.make_image(image_factory=PilImage)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode()


def verify_totp(secret: str, code: str) -> bool:
    """Verify a 6-digit TOTP code against the secret."""
    if not secret or not code:
        return False
    totp = pyotp.TOTP(secret, digits=TOTP_DIGITS, interval=TOTP_INTERVAL)
    return bool(totp.verify(code.strip(), valid_window=TOTP_VALID_WINDOW))


# ==============================================================================
# RECOVERY CODES
# ==============================================================================

def generate_recovery_codes(count: int = RECOVERY_CODE_COUNT) -> List[str]:
    """Generate single-use recovery codes (returned to the user once)."""
    return [secrets.token_hex(5) for _ in range(count)]


def hash_recovery_codes(codes: List[str]) -> List[str]:
    """Hash recovery codes for storage."""
    return [hashlib.sha256(code.encode()).hexdigest() for code in codes]


def consume_recovery_code(
    code: str, hashed_codes: List[str]
) -> Tuple[bool, List[str]]:
    """Return ``(matched, remaining_hashes)`` and remove a used code."""
    target = hashlib.sha256(code.strip().encode()).hexdigest()
    for index, stored in enumerate(hashed_codes):
        if hmac.compare_digest(stored, target):
            remaining = hashed_codes[:index] + hashed_codes[index + 1:]
            return True, remaining
    return False, hashed_codes


# ==============================================================================
# OPAQUE TOKEN HASHING (refresh + email tokens)
# ==============================================================================

def generate_opaque_token(nbytes: int = 32) -> str:
    """Generate a high-entropy opaque token (URL-safe)."""
    return secrets.token_urlsafe(nbytes)


def hash_token(token: str) -> str:
    """Hash an opaque token for storage/lookup."""
    return hashlib.sha256(token.encode()).hexdigest()


# ==============================================================================
# PASSWORD POLICY
# ==============================================================================
MIN_PASSWORD_LENGTH = int(os.getenv("MIN_PASSWORD_LENGTH", "12"))


def validate_password_strength(password: str) -> None:
    """Raise ``ValueError`` when a password does not meet policy."""
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
        )
    if not any(c.islower() for c in password):
        raise ValueError("Password must contain a lowercase letter.")
    if not any(c.isupper() for c in password):
        raise ValueError("Password must contain an uppercase letter.")
    if not any(c.isdigit() for c in password):
        raise ValueError("Password must contain a digit.")
