"""Κρυπτογραφημένο state (AES-256-GCM).

Στο δίσκο και στο branch `state` υπάρχει μόνο το `seen.db.enc`. Το SQLite σε
απλή μορφή ζει σε προσωρινό φάκελο μόνο όσο τρέχει ένα job και σβήνεται στο τέλος.
Το κλειδί (STATE_KEY, 32 bytes σε base64) υπάρχει μόνο στο Keychain και στα
GitHub Secrets. Αν χαθεί, το state απλά ξαναχτίζεται χωρίς ειδοποιήσεις.
"""
from __future__ import annotations

import base64
import contextlib
import hashlib
import logging
import os
import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

log = logging.getLogger(__name__)

MAGIC = b"UNWA1"  # έκδοση μορφής αρχείου
AAD = b"uniwa-notifier/seen.db"
ENC_NAME = "seen.db.enc"
PLAIN_NAME = "seen.db"


class VaultError(RuntimeError):
    pass


def generate_key() -> str:
    return base64.b64encode(AESGCM.generate_key(bit_length=256)).decode()


def _key(b64: str) -> bytes:
    try:
        key = base64.b64decode(b64.strip(), validate=True)
    except Exception as e:
        raise VaultError("Το STATE_KEY δεν είναι έγκυρο base64") from e
    if len(key) != 32:
        raise VaultError("Το STATE_KEY πρέπει να είναι 32 bytes (AES-256)")
    return key


def encrypt(data: bytes, b64key: str) -> bytes:
    nonce = os.urandom(12)
    return MAGIC + nonce + AESGCM(_key(b64key)).encrypt(nonce, data, AAD)


def decrypt(blob: bytes, b64key: str) -> bytes:
    if not blob.startswith(MAGIC):
        raise VaultError("Άγνωστη μορφή κρυπτογραφημένου state")
    nonce, ct = blob[len(MAGIC):len(MAGIC) + 12], blob[len(MAGIC) + 12:]
    try:
        return AESGCM(_key(b64key)).decrypt(nonce, ct, AAD)
    except Exception as e:
        raise VaultError("Αποτυχία αποκρυπτογράφησης state (λάθος STATE_KEY;)") from e


def _wipe(path: Path) -> None:
    """Best effort: γράφει μηδενικά πριν σβήσει το αρχείο."""
    with contextlib.suppress(OSError):
        size = path.stat().st_size
        with open(path, "r+b") as f:
            f.write(b"\0" * size)
            f.flush()
            os.fsync(f.fileno())
    with contextlib.suppress(OSError):
        path.unlink()


@contextlib.contextmanager
def open_state(state_dir: Path, b64key: str | None) -> Iterator[Path]:
    """Δίνει path προς ένα προσωρινό seen.db και το ξανακρυπτογραφεί στο τέλος.

    - Υπάρχει seen.db.enc → αποκρυπτογράφηση σε temp.
    - Υπάρχει μόνο παλιό seen.db σε απλή μορφή → χρησιμοποιείται και μετά σβήνεται (migration).
    - Το .enc ξαναγράφεται μόνο αν άλλαξε το περιεχόμενο, ώστε να μη γίνεται push σε κάθε run.
    """
    state_dir.mkdir(parents=True, exist_ok=True)
    enc_path, legacy = state_dir / ENC_NAME, state_dir / PLAIN_NAME

    if not b64key:
        log.warning("Λείπει STATE_KEY: το state μένει ΧΩΡΙΣ κρυπτογράφηση")
        yield legacy
        return

    tmp = Path(tempfile.mkdtemp(prefix="uniwa-"))
    os.chmod(tmp, 0o700)
    work = tmp / PLAIN_NAME
    before: bytes | None = None
    try:
        if enc_path.exists():
            plain = decrypt(enc_path.read_bytes(), b64key)
            work.write_bytes(plain)
            before = hashlib.sha256(plain).digest()
        elif legacy.exists():
            log.info("Μεταφορά παλιού state σε κρυπτογραφημένη μορφή")
            shutil.copyfile(legacy, work)
        if work.exists():
            os.chmod(work, 0o600)

        yield work

        if work.exists():
            plain = work.read_bytes()
            if before is None or hashlib.sha256(plain).digest() != before:
                tmp_enc = enc_path.with_suffix(".tmp")
                tmp_enc.write_bytes(encrypt(plain, b64key))
                tmp_enc.replace(enc_path)
        if legacy.exists():
            _wipe(legacy)
    finally:
        for p in tmp.glob("*"):
            _wipe(p)
        shutil.rmtree(tmp, ignore_errors=True)
