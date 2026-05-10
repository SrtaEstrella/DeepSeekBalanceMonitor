import os
import stat
import base64
import struct
import hmac
import hashlib
import time
from pathlib import Path
from typing import Optional
from ctypes import CDLL, c_size_t, byref, create_string_buffer

# Load CommonCrypto for AES-128-CBC
_common_crypto = CDLL("/usr/lib/system/libcommonCrypto.dylib")

kCCEncrypt = 0
kCCDecrypt = 1
kCCAlgorithmAES128 = 0
kCCOptionPKCS7Padding = 1
kCCBlockSizeAES128 = 16

_SALT = b"DeepSeekBalMonMacSalt2025"

def _aes_cbc_decrypt(key: bytes, iv: bytes, ciphertext: bytes) -> bytes:
    out_buf = create_string_buffer(len(ciphertext) + kCCBlockSizeAES128)
    out_len = c_size_t()
    status = _common_crypto.CCCrypt(
        kCCDecrypt, kCCAlgorithmAES128, kCCOptionPKCS7Padding,
        key, len(key), iv, ciphertext, len(ciphertext),
        out_buf, len(out_buf), byref(out_len)
    )
    if status != 0:
        raise ValueError(f"CCCrypt failed with status {status}")
    return out_buf.raw[:out_len.value]

def _aes_cbc_encrypt(key: bytes, iv: bytes, plaintext: bytes) -> bytes:
    out_buf = create_string_buffer(len(plaintext) + kCCBlockSizeAES128)
    out_len = c_size_t()
    status = _common_crypto.CCCrypt(
        kCCEncrypt, kCCAlgorithmAES128, kCCOptionPKCS7Padding,
        key, len(key), iv, plaintext, len(plaintext),
        out_buf, len(out_buf), byref(out_len)
    )
    if status != 0:
        raise ValueError(f"CCCrypt failed with status {status}")
    return out_buf.raw[:out_len.value]

def _get_fernet_keys(data_dir: Path) -> tuple[bytes, bytes]:
    keyring_path = data_dir / ".keyring"
    if not keyring_path.exists():
        raw = os.urandom(32)
        keyring_path.write_bytes(raw)
        os.chmod(keyring_path, stat.S_IRUSR | stat.S_IWUSR)
    else:
        raw = keyring_path.read_bytes()

    derived = hashlib.pbkdf2_hmac('sha256', raw, _SALT, 100_000, 32)
    return derived[:16], derived[16:]

def encrypt_api_key(plaintext: str, data_dir: Optional[Path] = None) -> str:
    if not plaintext or data_dir is None:
        return ""
    try:
        signing_key, encryption_key = _get_fernet_keys(data_dir)
        version, timestamp, iv = b"\x80", struct.pack(">Q", int(time.time())), os.urandom(16)
        ciphertext = _aes_cbc_encrypt(encryption_key, iv, plaintext.encode())
        basic_parts = version + timestamp + iv + ciphertext
        hmac_val = hmac.new(signing_key, basic_parts, hashlib.sha256).digest()
        return base64.urlsafe_b64encode(basic_parts + hmac_val).decode()
    except Exception:
        return ""

def decrypt_api_key(ciphertext: str, data_dir: Optional[Path] = None) -> str:
    if not ciphertext or data_dir is None:
        return ""
    try:
        data = base64.urlsafe_b64decode(ciphertext.encode())
        if data[0] != 0x80: return ""
        signing_key, encryption_key = _get_fernet_keys(data_dir)
        if not hmac.compare_digest(hmac.new(signing_key, data[:-32], hashlib.sha256).digest(), data[-32:]):
            return ""
        plaintext = _aes_cbc_decrypt(encryption_key, data[9:25], data[25:-32])
        return plaintext.decode('utf-8')
    except Exception:
        return ""
