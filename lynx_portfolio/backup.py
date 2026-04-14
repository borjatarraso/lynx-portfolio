"""
Backup and restore for the portfolio database.

Keeps a single ``.bak`` copy (overwritten each session).  For encrypted
databases the backup covers the ``.enc`` and ``.salt`` files.
"""

import os
import shutil
from typing import Optional

from .vault import ENC_SUFFIX, SALT_SUFFIX

BAK_SUFFIX = ".bak"


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def _bak_path(path: str) -> str:
    return path + BAK_SUFFIX


# ---------------------------------------------------------------------------
# Create backup
# ---------------------------------------------------------------------------

def create_backup(db_path: str, encrypted: bool = False) -> Optional[str]:
    """Copy the current database (or vault files) to a ``.bak`` sibling.

    Returns the primary backup path on success, or *None* if the source
    does not exist.
    """
    if encrypted:
        enc = db_path + ENC_SUFFIX
        salt = db_path + SALT_SUFFIX
        if not os.path.isfile(enc):
            return None
        shutil.copy2(enc, _bak_path(enc))
        if os.path.isfile(salt):
            shutil.copy2(salt, _bak_path(salt))
        return _bak_path(enc)
    else:
        if not os.path.isfile(db_path):
            return None
        shutil.copy2(db_path, _bak_path(db_path))
        return _bak_path(db_path)


# ---------------------------------------------------------------------------
# Restore backup
# ---------------------------------------------------------------------------

def restore_backup(db_path: str) -> bool:
    """Restore the database from the most recent backup.

    Auto-detects whether the backup is for an encrypted or plain database.
    Returns *True* on success, *False* if no suitable backup exists.
    """
    enc_bak = _bak_path(db_path + ENC_SUFFIX)
    salt_bak = _bak_path(db_path + SALT_SUFFIX)
    plain_bak = _bak_path(db_path)

    # Prefer encrypted backup if present
    if os.path.isfile(enc_bak):
        shutil.copy2(enc_bak, db_path + ENC_SUFFIX)
        if os.path.isfile(salt_bak):
            shutil.copy2(salt_bak, db_path + SALT_SUFFIX)
        return True

    if os.path.isfile(plain_bak):
        shutil.copy2(plain_bak, db_path)
        return True

    return False


# ---------------------------------------------------------------------------
# Query
# ---------------------------------------------------------------------------

def has_backup(db_path: str) -> bool:
    """Return *True* if any backup file exists for *db_path*."""
    return (
        os.path.isfile(_bak_path(db_path))
        or os.path.isfile(_bak_path(db_path + ENC_SUFFIX))
    )
