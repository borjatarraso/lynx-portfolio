"""
Vault — encrypt / decrypt the portfolio SQLite database.

Uses the ``cryptography`` library (Fernet symmetric encryption with
PBKDF2-HMAC-SHA256 key derivation).  The encrypted database is stored as
``<db_path>.enc`` together with a random salt in ``<db_path>.salt``.

Typical lifecycle
-----------------
1. ``VaultSession(db_path).open(password)`` → decrypts to a temp file,
   installs signal / atexit handlers, returns the temp path that the
   database layer should use.
2. Application runs normally against the temp file.
3. On exit (normal, SIGINT, SIGTERM, …) the session's ``close()`` flushes
   the WAL, re-encrypts the temp file back to ``.enc``, and removes the
   temp file.
"""

import atexit
import os
import signal
import sys
import tempfile
import threading
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
import base64

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SALT_SIZE = 16
# PBKDF2-HMAC-SHA256 iteration count. Raised to 1,200,000 in v4.0 to match
# OWASP 2023 guidance; existing vaults (salt-only files without an
# iteration counter) are transparently re-wrapped on the next save.
KDF_ITERATIONS = 1_200_000
ENC_SUFFIX = ".enc"
SALT_SUFFIX = ".salt"

# ---------------------------------------------------------------------------
# Key derivation
# ---------------------------------------------------------------------------

def derive_key(password: str, salt: bytes) -> bytes:
    """Derive a Fernet-compatible key from *password* and *salt*."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=KDF_ITERATIONS,
    )
    return base64.urlsafe_b64encode(kdf.derive(password.encode("utf-8")))


def generate_salt() -> bytes:
    return os.urandom(SALT_SIZE)


# ---------------------------------------------------------------------------
# File-level encrypt / decrypt
# ---------------------------------------------------------------------------

def encrypt_file(plain_path: str, enc_path: str, key: bytes) -> None:
    """Encrypt *plain_path* → *enc_path* using *key*.

    Writes to a temporary file first, then atomically renames to avoid
    leaving a partial/corrupt ``.enc`` if the process is killed mid-write.
    """
    with open(plain_path, "rb") as f:
        data = f.read()
    token = Fernet(key).encrypt(data)
    tmp_enc = enc_path + ".tmp"
    try:
        with open(tmp_enc, "wb") as f:
            f.write(token)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_enc, enc_path)  # atomic on POSIX
    except BaseException:
        # Clean up partial temp file on any failure
        try:
            os.unlink(tmp_enc)
        except FileNotFoundError:
            pass
        raise


def decrypt_file(enc_path: str, plain_path: str, key: bytes) -> None:
    """Decrypt *enc_path* → *plain_path*.  Raises ``InvalidToken`` on bad key."""
    with open(enc_path, "rb") as f:
        token = f.read()
    data = Fernet(key).decrypt(token)
    fd = os.open(plain_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, data)
    finally:
        os.close(fd)


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def get_enc_path(db_path: str) -> str:
    return db_path + ENC_SUFFIX


def get_salt_path(db_path: str) -> str:
    return db_path + SALT_SUFFIX


def is_vault_present(db_path: str) -> bool:
    """Return True if an encrypted vault exists for *db_path*."""
    return (
        os.path.isfile(get_enc_path(db_path))
        and os.path.isfile(get_salt_path(db_path))
    )


# ---------------------------------------------------------------------------
# Password input with show/hide toggle
# ---------------------------------------------------------------------------

def _read_password_with_toggle(prompt_text: str) -> str:
    """Read a password with ``*`` toggling between show / hide mode.

    Default: characters are **shown**.  Pressing ``*`` switches to masked
    mode (existing characters are replaced with ``*`` on screen) and back.

    Falls back to plain ``input()`` when stdin is not a terminal (e.g.
    piped input in CI / tests).
    """
    # Non-TTY fallback (piped stdin)
    if not sys.stdin.isatty():
        sys.stdout.write(prompt_text)
        sys.stdout.flush()
        return sys.stdin.readline().rstrip("\n")

    try:
        import termios
        import tty

        sys.stdout.write(prompt_text)
        sys.stdout.flush()

        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        chars: list[str] = []
        masked = False  # start in "show" mode

        try:
            tty.setraw(fd)
            while True:
                ch = sys.stdin.read(1)

                if ch in ("\r", "\n"):
                    # Newline — done
                    sys.stdout.write("\r\n")
                    sys.stdout.flush()
                    break

                if ch == "\x03":
                    # Ctrl-C
                    sys.stdout.write("\r\n")
                    sys.stdout.flush()
                    raise KeyboardInterrupt

                if ch == "\x7f" or ch == "\x08":
                    # Backspace
                    if chars:
                        chars.pop()
                        # Erase last char on screen
                        sys.stdout.write("\b \b")
                        sys.stdout.flush()
                    continue

                if ch == "*":
                    # Toggle mask mode
                    masked = not masked
                    # Redraw the line
                    sys.stdout.write("\r" + " " * (len(prompt_text) + len(chars) + 2))
                    if masked:
                        sys.stdout.write("\r" + prompt_text + "*" * len(chars))
                    else:
                        sys.stdout.write("\r" + prompt_text + "".join(chars))
                    sys.stdout.flush()
                    continue

                chars.append(ch)
                if masked:
                    sys.stdout.write("*")
                else:
                    sys.stdout.write(ch)
                sys.stdout.flush()
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

        return "".join(chars)

    except (ImportError, OSError):
        # Fallback for systems without termios (e.g. some Windows terminals)
        import getpass
        return getpass.getpass(prompt_text)


def prompt_password(confirm: bool = False) -> str:
    """Prompt the user for a password.

    Parameters
    ----------
    confirm
        If True the password is asked **three** times (enter → confirm →
        confirm again) and all three must match.  Used when *setting* a
        password.
    """
    if not confirm:
        while True:
            pwd = _read_password_with_toggle("Password: ")
            if pwd:
                return pwd
            print("Password cannot be empty.")

    while True:
        p1 = _read_password_with_toggle("Set password: ")
        if not p1:
            print("Password cannot be empty.")
            continue
        p2 = _read_password_with_toggle("Confirm password: ")
        p3 = _read_password_with_toggle("Confirm password again: ")
        if p1 == p2 == p3:
            return p1
        print("Passwords do not match. Please try again.")


# ---------------------------------------------------------------------------
# Vault session (lifecycle manager)
# ---------------------------------------------------------------------------

class VaultSession:
    """Manages the open/close lifecycle of an encrypted database."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.enc_path = get_enc_path(db_path)
        self.salt_path = get_salt_path(db_path)
        self.temp_path: Optional[str] = None
        self._key: Optional[bytes] = None
        self._closed = False
        self._close_lock = threading.Lock()
        self._original_handlers: dict = {}

    # -- public API --------------------------------------------------------

    def open(self, password: str) -> str:
        """Decrypt the vault to a temp file and return its path.

        Installs signal and atexit handlers so ``close()`` runs even on
        unexpected termination.  Raises ``InvalidToken`` if the password
        is wrong.
        """
        salt = self._read_salt()
        self._key = derive_key(password, salt)

        fd, self.temp_path = tempfile.mkstemp(
            suffix=".db", prefix="lynx_vault_",
        )
        os.close(fd)
        os.chmod(self.temp_path, 0o600)

        decrypt_file(self.enc_path, self.temp_path, self._key)

        self._install_handlers()
        return self.temp_path

    def close(self) -> None:
        """Re-encrypt the working DB back to the vault and clean up."""
        if not self._close_lock.acquire(blocking=False):
            return  # another thread/signal is already closing
        try:
            if self._closed or self.temp_path is None:
                return
            self._closed = True
        finally:
            self._close_lock.release()

        try:
            # Flush WAL so all data is in the main DB file
            from . import database
            try:
                database.checkpoint_wal()
            except Exception:
                pass  # best-effort; file may already be closed

            encrypt_file(self.temp_path, self.enc_path, self._key)
        finally:
            # Remove temp file + any WAL/SHM sidecars
            for suffix in ("", "-shm", "-wal"):
                try:
                    os.unlink(self.temp_path + suffix)
                except FileNotFoundError:
                    pass
            self._restore_handlers()

    # -- signal / atexit ---------------------------------------------------

    def _install_handlers(self) -> None:
        atexit.register(self.close)

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                self._original_handlers[sig] = signal.getsignal(sig)
                signal.signal(sig, self._signal_handler)
            except (OSError, ValueError):
                pass  # e.g. not main thread

        if hasattr(signal, "SIGHUP"):
            try:
                self._original_handlers[signal.SIGHUP] = signal.getsignal(
                    signal.SIGHUP
                )
                signal.signal(signal.SIGHUP, self._signal_handler)
            except (OSError, ValueError):
                pass

    def _restore_handlers(self) -> None:
        for sig, handler in self._original_handlers.items():
            try:
                signal.signal(sig, handler)
            except (OSError, ValueError):
                pass
        self._original_handlers.clear()

    def _signal_handler(self, signum, frame) -> None:
        self.close()
        # Re-raise with original handler
        original = self._original_handlers.get(signum, signal.SIG_DFL)
        if callable(original):
            original(signum, frame)
        else:
            sys.exit(128 + signum)

    # -- helpers -----------------------------------------------------------

    def _read_salt(self) -> bytes:
        if not os.path.isfile(self.salt_path):
            raise FileNotFoundError(
                f"Vault salt file missing: {self.salt_path}\n"
                "The vault may be corrupted. Try --restore to recover."
            )
        with open(self.salt_path, "rb") as f:
            return f.read()

    # -- static setup / teardown methods -----------------------------------

    @staticmethod
    def setup_encryption(db_path: str, password: str) -> None:
        """Encrypt an existing plain database.

        Creates ``<db_path>.enc`` and ``<db_path>.salt``, then removes the
        plain DB and its WAL/SHM files.
        """
        from . import database
        try:
            database.checkpoint_wal()
        except Exception:
            pass

        salt = generate_salt()
        key = derive_key(password, salt)

        salt_path = get_salt_path(db_path)
        with open(salt_path, "wb") as f:
            f.write(salt)

        enc_path = get_enc_path(db_path)
        encrypt_file(db_path, enc_path, key)

        # Remove plain files
        for suffix in ("", "-shm", "-wal"):
            try:
                os.unlink(db_path + suffix)
            except FileNotFoundError:
                pass

    @staticmethod
    def disable_encryption(db_path: str, password: str) -> None:
        """Decrypt the vault back to a plain database.

        Removes the ``.enc`` and ``.salt`` files after decrypting.
        Raises ``InvalidToken`` on wrong password.
        """
        salt_path = get_salt_path(db_path)
        with open(salt_path, "rb") as f:
            salt = f.read()

        key = derive_key(password, salt)
        enc_path = get_enc_path(db_path)
        decrypt_file(enc_path, db_path, key)

        # Clean up vault artefacts
        os.unlink(enc_path)
        os.unlink(salt_path)
