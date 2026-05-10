"""
Windows Credential Manager integration - secure API key storage.
"""
import sys
import ctypes
import ctypes.wintypes

TARGET_NAME = "DeepSeekBalanceMonitor"
CRED_TYPE_GENERIC = 1
CRED_PERSIST_LOCAL_MACHINE = 2


class _CREDENTIAL(ctypes.Structure):
    _fields_ = [
        ("Flags", ctypes.wintypes.DWORD),
        ("Type", ctypes.wintypes.DWORD),
        ("TargetName", ctypes.wintypes.LPWSTR),
        ("Comment", ctypes.wintypes.LPWSTR),
        ("LastWritten", ctypes.wintypes.FILETIME),
        ("CredentialBlobSize", ctypes.wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_byte)),
        ("Persist", ctypes.wintypes.DWORD),
        ("AttributeCount", ctypes.wintypes.DWORD),
        ("Attributes", ctypes.c_void_p),
        ("TargetAlias", ctypes.wintypes.LPWSTR),
        ("UserName", ctypes.wintypes.LPWSTR),
    ]


def _ensure_init():
    """Lazy-init the advapi32 bindings once per process."""
    if hasattr(_ensure_init, "_advapi32"):
        return _ensure_init._advapi32
    if sys.platform != "win32":
        _ensure_init._advapi32 = None
        return None
    a = ctypes.windll.advapi32
    a.CredWriteW.argtypes = [ctypes.POINTER(_CREDENTIAL), ctypes.wintypes.DWORD]
    a.CredWriteW.restype = ctypes.wintypes.BOOL
    a.CredReadW.argtypes = [ctypes.wintypes.LPCWSTR, ctypes.wintypes.DWORD,
                            ctypes.wintypes.DWORD, ctypes.POINTER(ctypes.POINTER(_CREDENTIAL))]
    a.CredReadW.restype = ctypes.wintypes.BOOL
    a.CredDeleteW.argtypes = [ctypes.wintypes.LPCWSTR, ctypes.wintypes.DWORD,
                              ctypes.wintypes.DWORD]
    a.CredDeleteW.restype = ctypes.wintypes.BOOL
    a.CredFree.argtypes = [ctypes.c_void_p]
    _ensure_init._advapi32 = a
    return a


def store_credential(api_key: str):
    a = _ensure_init()
    if a is None:
        return
    try:
        blob = api_key.encode("utf-16-le")
        cred = _CREDENTIAL()
        cred.Type = CRED_TYPE_GENERIC
        cred.TargetName = TARGET_NAME
        cred.CredentialBlobSize = len(blob)
        buf = ctypes.create_string_buffer(blob, len(blob))
        cred.CredentialBlob = ctypes.cast(buf, ctypes.POINTER(ctypes.c_byte))
        cred.Persist = CRED_PERSIST_LOCAL_MACHINE
        cred.UserName = ""
        a.CredWriteW(ctypes.byref(cred), 0)
    except Exception:
        pass


def read_credential() -> str | None:
    a = _ensure_init()
    if a is None:
        return None
    try:
        pcred = ctypes.POINTER(_CREDENTIAL)()
        if not a.CredReadW(TARGET_NAME, CRED_TYPE_GENERIC, 0, ctypes.byref(pcred)):
            return None
        cred = pcred.contents
        blob = ctypes.string_at(cred.CredentialBlob, cred.CredentialBlobSize)
        result = blob.decode("utf-16-le")
        a.CredFree(ctypes.cast(pcred, ctypes.c_void_p))
        return result
    except Exception:
        return None


def delete_credential():
    a = _ensure_init()
    if a is None:
        return
    try:
        a.CredDeleteW(TARGET_NAME, CRED_TYPE_GENERIC, 0)
    except Exception:
        pass
