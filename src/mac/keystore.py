"""
mac_keystore.py — AES (Fernet) encrypted API Key storage for macOS.

The encryption key is derived from a machine-unique secret stored in
~/Library/Application Support/<APP_NAME>/.keyring  (mode 600).
This keeps the key off the code and config files.
"""
import os
import stat
import base64
from pathlib import Path
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

_SALT = b"DeepSeekBalMonMacSalt2025"  # static salt is fine; secrecy lives in the keyring file

def _get_fernet(data_dir: Path) -> Fernet:
    keyring_path = data_dir / ".keyring"
    if keyring_path.exists():
        raw = keyring_path.read_bytes()
    else:
        # Generate a new 32-byte random master secret
        raw = os.urandom(32)
        keyring_path.write_bytes(raw)
        # Lock to owner-read-only
        os.chmod(keyring_path, stat.S_IRUSR | stat.S_IWUSR)

    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=_SALT, iterations=100_000)
    key = base64.urlsafe_b64encode(kdf.derive(raw))
    return Fernet(key)

def encrypt_api_key(plaintext: str, data_dir: Path) -> str:
    """Encrypt and return base64-encoded ciphertext."""
    f = _get_fernet(data_dir)
    return f.encrypt(plaintext.encode()).decode()

def decrypt_api_key(ciphertext: str, data_dir: Path) -> str:
    """Decrypt and return plaintext. Returns '' on any error."""
    if not ciphertext:
        return ""
    try:
        f = _get_fernet(data_dir)
        return f.decrypt(ciphertext.encode()).decode()
    except Exception:
        return ""
