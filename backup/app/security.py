from werkzeug.security import check_password_hash
from passlib.context import CryptContext
from functools import wraps
from flask import abort
from flask_login import current_user
import os

# Fernet for encrypting sensitive fields at rest
try:
    from cryptography.fernet import Fernet, InvalidToken
except Exception:
    Fernet = None
    InvalidToken = Exception

# Use Passlib CryptContext so we can migrate to Argon2 while still verifying
# older werkzeug hashes. New hashes will use Argon2 by default.
pwd_context = CryptContext(schemes=['argon2', 'pbkdf2_sha256'], deprecated='auto')


def hash_password(password: str) -> str:
    """Hash a password using Passlib (argon2 primary)."""
    return pwd_context.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    """Verify a password against its hash.

    Tries Passlib first (argon2/pbkdf2). If that fails (older werkzeug-format hash),
    falls back to werkzeug.check_password_hash to preserve backward compatibility.
    """
    try:
        # Passlib expects (password, hash)
        if pwd_context.identify(password_hash):
            return pwd_context.verify(password, password_hash)
    except Exception:
        pass
    # Fallback to werkzeug-style hashes
    try:
        return check_password_hash(password_hash, password)
    except Exception:
        return False


def _get_fernet():
    """Return a Fernet instance using FERNET_KEY from env or None."""
    key = os.getenv('FERNET_KEY')
    if not key or Fernet is None:
        return None
    try:
        return Fernet(key.encode() if isinstance(key, str) else key)
    except Exception:
        return None


def encrypt_secret(plaintext: str) -> bytes:
    """Encrypt a plaintext string and return bytes token.

    Returns None if encryption is not available or fails.
    """
    if plaintext is None:
        return None
    f = _get_fernet()
    if not f:
        return None
    try:
        return f.encrypt(plaintext.encode('utf-8'))
    except Exception:
        return None


def decrypt_secret(token: bytes) -> str:
    """Decrypt a bytes token produced by `encrypt_secret`.

    Returns the plaintext string or None on failure.
    """
    if token is None:
        return None
    f = _get_fernet()
    if not f:
        return None
    try:
        pt = f.decrypt(token)
        return pt.decode('utf-8')
    except InvalidToken:
        return None
    except Exception:
        return None


def get_client_ip(request) -> str:
    """Return best-effort client IP, honoring ProxyFix/X-Forwarded-For."""
    try:
        # With ProxyFix, request.remote_addr should be the real client IP
        ip = request.remote_addr
        # Fallback: first address in access_route if available
        if not ip and hasattr(request, 'access_route') and request.access_route:
            ip = request.access_route[0]
        return ip or 'unknown'
    except Exception:
        return 'unknown'


def admin_required(f):
    """Decorator to require admin role"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            abort(401)
        if not current_user.is_admin():
            abort(403)
        return f(*args, **kwargs)
    return decorated_function


def teacher_required(f):
    """Decorator to require teacher or admin role"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            abort(401)
        if current_user.role not in ['teacher', 'admin']:
            abort(403)
        return f(*args, **kwargs)
    return decorated_function
