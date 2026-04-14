"""
Unit tests for the vault (encryption) and backup modules.
"""

import os
import shutil
import tempfile

import pytest
from cryptography.fernet import InvalidToken

from lynx import database
from lynx.vault import (
    derive_key,
    generate_salt,
    encrypt_file,
    decrypt_file,
    is_vault_present,
    get_enc_path,
    get_salt_path,
    VaultSession,
)
from lynx.backup import (
    create_backup,
    restore_backup,
    has_backup,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmpdir():
    d = tempfile.mkdtemp(prefix="lynx_test_vault_")
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def db_path(tmpdir):
    return os.path.join(tmpdir, "portfolio.db")


@pytest.fixture
def populated_db(db_path):
    """Create a real SQLite portfolio DB with one instrument."""
    database.set_db_path(db_path)
    database.init_db()
    database.add_instrument("AAPL", 10, avg_purchase_price=150.0)
    return db_path


# ---------------------------------------------------------------------------
# Key derivation
# ---------------------------------------------------------------------------

class TestKeyDerivation:
    def test_deterministic(self):
        salt = b"0123456789abcdef"
        k1 = derive_key("password", salt)
        k2 = derive_key("password", salt)
        assert k1 == k2

    def test_different_salt_gives_different_key(self):
        s1 = generate_salt()
        s2 = generate_salt()
        k1 = derive_key("password", s1)
        k2 = derive_key("password", s2)
        assert k1 != k2

    def test_different_password_gives_different_key(self):
        salt = generate_salt()
        k1 = derive_key("alpha", salt)
        k2 = derive_key("beta", salt)
        assert k1 != k2


# ---------------------------------------------------------------------------
# File-level encrypt / decrypt
# ---------------------------------------------------------------------------

class TestFileEncryption:
    def test_roundtrip(self, tmpdir):
        plain = os.path.join(tmpdir, "data.bin")
        enc = os.path.join(tmpdir, "data.enc")
        out = os.path.join(tmpdir, "data.out")

        payload = b"Hello, Lynx!" * 100
        with open(plain, "wb") as f:
            f.write(payload)

        salt = generate_salt()
        key = derive_key("s3cret", salt)

        encrypt_file(plain, enc, key)
        assert os.path.isfile(enc)

        decrypt_file(enc, out, key)
        with open(out, "rb") as f:
            assert f.read() == payload

    def test_wrong_key_raises(self, tmpdir):
        plain = os.path.join(tmpdir, "data.bin")
        enc = os.path.join(tmpdir, "data.enc")
        out = os.path.join(tmpdir, "data.out")

        with open(plain, "wb") as f:
            f.write(b"secret data")

        salt = generate_salt()
        good = derive_key("correct", salt)
        bad = derive_key("wrong", salt)

        encrypt_file(plain, enc, good)

        with pytest.raises(InvalidToken):
            decrypt_file(enc, out, bad)


# ---------------------------------------------------------------------------
# Vault presence detection
# ---------------------------------------------------------------------------

class TestIsVaultPresent:
    def test_false_when_nothing(self, db_path):
        assert not is_vault_present(db_path)

    def test_false_when_only_enc(self, db_path):
        with open(get_enc_path(db_path), "w") as f:
            f.write("x")
        assert not is_vault_present(db_path)

    def test_false_when_only_salt(self, db_path):
        with open(get_salt_path(db_path), "w") as f:
            f.write("x")
        assert not is_vault_present(db_path)

    def test_true_when_both(self, db_path):
        for p in (get_enc_path(db_path), get_salt_path(db_path)):
            with open(p, "w") as f:
                f.write("x")
        assert is_vault_present(db_path)


# ---------------------------------------------------------------------------
# VaultSession lifecycle
# ---------------------------------------------------------------------------

class TestVaultSession:
    def test_setup_encryption(self, populated_db):
        db = populated_db
        VaultSession.setup_encryption(db, "pw")
        assert not os.path.isfile(db)
        assert is_vault_present(db)

    def test_open_close_preserves_data(self, populated_db):
        db = populated_db
        VaultSession.setup_encryption(db, "pw")

        session = VaultSession(db)
        working = session.open("pw")
        assert os.path.isfile(working)

        database.set_db_path(working)
        rows = database.get_all_instruments()
        assert len(rows) == 1
        assert rows[0]["ticker"] == "AAPL"

        session.close()
        assert not os.path.isfile(working)
        assert is_vault_present(db)

    def test_wrong_password_raises(self, populated_db):
        db = populated_db
        VaultSession.setup_encryption(db, "correct")

        session = VaultSession(db)
        with pytest.raises(InvalidToken):
            session.open("wrong")

    def test_disable_encryption(self, populated_db):
        db = populated_db
        VaultSession.setup_encryption(db, "pw")

        VaultSession.disable_encryption(db, "pw")
        assert os.path.isfile(db)
        assert not is_vault_present(db)

        database.set_db_path(db)
        rows = database.get_all_instruments()
        assert len(rows) == 1

    def test_disable_wrong_password_raises(self, populated_db):
        db = populated_db
        VaultSession.setup_encryption(db, "correct")
        with pytest.raises(InvalidToken):
            VaultSession.disable_encryption(db, "wrong")

    def test_data_mutation_persists(self, populated_db):
        """Changes made during a session survive close→re-open."""
        db = populated_db
        VaultSession.setup_encryption(db, "pw")

        # Session 1: add an instrument
        s1 = VaultSession(db)
        w1 = s1.open("pw")
        database.set_db_path(w1)
        database.add_instrument("GOOG", 5)
        s1.close()

        # Session 2: verify both instruments exist
        s2 = VaultSession(db)
        w2 = s2.open("pw")
        database.set_db_path(w2)
        rows = database.get_all_instruments()
        tickers = {r["ticker"] for r in rows}
        assert tickers == {"AAPL", "GOOG"}
        s2.close()


# ---------------------------------------------------------------------------
# Backup module
# ---------------------------------------------------------------------------

class TestVaultEdgeCases:
    def test_special_characters_in_password(self, populated_db):
        """Passwords with special chars, unicode, emojis work."""
        db = populated_db
        password = "p@$$w0rd!#%^&*()_+={} 🔐"
        VaultSession.setup_encryption(db, password)
        assert is_vault_present(db)

        session = VaultSession(db)
        working = session.open(password)
        database.set_db_path(working)
        rows = database.get_all_instruments()
        assert len(rows) == 1
        session.close()

    def test_very_long_password(self, populated_db):
        """Very long passwords are handled correctly."""
        db = populated_db
        password = "a" * 500
        VaultSession.setup_encryption(db, password)

        session = VaultSession(db)
        working = session.open(password)
        database.set_db_path(working)
        assert len(database.get_all_instruments()) == 1
        session.close()

    def test_close_is_idempotent(self, populated_db):
        """Calling close() multiple times is safe."""
        db = populated_db
        VaultSession.setup_encryption(db, "pw")

        session = VaultSession(db)
        session.open("pw")
        session.close()
        session.close()  # should not raise
        session.close()  # still safe

    def test_missing_salt_file_gives_clear_error(self, populated_db):
        """Opening vault with missing salt gives FileNotFoundError."""
        db = populated_db
        VaultSession.setup_encryption(db, "pw")

        # Remove the salt file
        os.unlink(get_salt_path(db))

        session = VaultSession(db)
        with pytest.raises(FileNotFoundError, match="salt file missing"):
            session.open("pw")

    def test_encrypt_preserves_multiple_instruments(self, db_path):
        """Multiple instruments survive encrypt → open → close → re-open."""
        database.set_db_path(db_path)
        database.init_db()
        database.add_instrument("AAPL", 10, avg_purchase_price=150.0)
        database.add_instrument("GOOG", 5, avg_purchase_price=100.0)
        database.add_instrument("MSFT", 20, avg_purchase_price=300.0)

        VaultSession.setup_encryption(db_path, "secure")

        for _ in range(3):  # open/close multiple times
            s = VaultSession(db_path)
            w = s.open("secure")
            database.set_db_path(w)
            rows = database.get_all_instruments()
            assert len(rows) == 3
            tickers = {r["ticker"] for r in rows}
            assert tickers == {"AAPL", "GOOG", "MSFT"}
            s.close()


class TestAtomicEncryption:
    """Test that encrypt_file is atomic (uses temp file + rename)."""

    def test_encrypt_creates_file(self, tmpdir):
        plain = os.path.join(tmpdir, "data.bin")
        enc = os.path.join(tmpdir, "data.enc")
        with open(plain, "wb") as f:
            f.write(b"test data")

        salt = generate_salt()
        key = derive_key("pw", salt)
        encrypt_file(plain, enc, key)
        assert os.path.isfile(enc)
        # No .tmp file left behind
        assert not os.path.isfile(enc + ".tmp")

    def test_encrypt_no_partial_on_bad_path(self, tmpdir):
        """If the output directory doesn't exist, encrypt fails cleanly."""
        plain = os.path.join(tmpdir, "data.bin")
        with open(plain, "wb") as f:
            f.write(b"test data")

        bad_enc = os.path.join(tmpdir, "nonexistent", "data.enc")
        salt = generate_salt()
        key = derive_key("pw", salt)
        with pytest.raises(FileNotFoundError):
            encrypt_file(plain, bad_enc, key)


class TestBackup:
    def test_create_backup_plain(self, populated_db):
        bak = create_backup(populated_db)
        assert bak is not None
        assert os.path.isfile(bak)
        assert bak.endswith(".bak")

    def test_create_backup_nonexistent(self, db_path):
        assert create_backup(db_path) is None

    def test_has_backup(self, populated_db):
        assert not has_backup(populated_db)
        create_backup(populated_db)
        assert has_backup(populated_db)

    def test_restore_plain(self, populated_db):
        db = populated_db
        create_backup(db)

        # Delete the DB
        os.unlink(db)
        assert not os.path.isfile(db)

        # Restore
        assert restore_backup(db)
        assert os.path.isfile(db)

        database.set_db_path(db)
        rows = database.get_all_instruments()
        assert len(rows) == 1

    def test_restore_no_backup(self, db_path):
        assert not restore_backup(db_path)

    def test_create_backup_encrypted(self, populated_db):
        db = populated_db
        VaultSession.setup_encryption(db, "pw")

        bak = create_backup(db, encrypted=True)
        assert bak is not None
        assert has_backup(db)

    def test_restore_encrypted(self, populated_db):
        db = populated_db
        VaultSession.setup_encryption(db, "pw")

        enc = get_enc_path(db)
        create_backup(db, encrypted=True)

        # Remove the encrypted file
        os.unlink(enc)
        assert not os.path.isfile(enc)

        # Restore
        assert restore_backup(db)
        assert os.path.isfile(enc)

        # Verify data is intact
        session = VaultSession(db)
        working = session.open("pw")
        database.set_db_path(working)
        rows = database.get_all_instruments()
        assert len(rows) == 1
        session.close()
