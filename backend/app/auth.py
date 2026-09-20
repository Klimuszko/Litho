import base64
import hashlib
import os
import re
import secrets
import sqlite3
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Literal

from pydantic import BaseModel, Field


USERNAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{2,31}$")
SESSION_TTL_SECONDS = 12 * 60 * 60
SCRYPT_N = 2**15
SCRYPT_R = 8
SCRYPT_P = 3


class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=1, max_length=256)


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    display_name: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=8, max_length=256)
    role: Literal["admin", "operator"] = "operator"


class UserUpdate(BaseModel):
    display_name: str = Field(min_length=1, max_length=80)
    role: Literal["admin", "operator"]
    active: bool


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=8, max_length=256)


class PasswordReset(BaseModel):
    new_password: str = Field(min_length=8, max_length=256)


def _utc_timestamp() -> int:
    return int(time.time())


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_username(username: str) -> str:
    normalized = username.strip().lower()
    if not USERNAME_PATTERN.fullmatch(normalized):
        raise ValueError("Username must contain 3-32 lowercase letters, digits, dots, dashes or underscores")
    return normalized


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P,
        dklen=64, maxmem=192 * 1024 * 1024,
    )
    return "$".join((
        "scrypt", str(SCRYPT_N), str(SCRYPT_R), str(SCRYPT_P),
        base64.urlsafe_b64encode(salt).decode("ascii"),
        base64.urlsafe_b64encode(derived).decode("ascii"),
    ))


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, salt, expected = encoded.split("$")
        if algorithm != "scrypt":
            return False
        actual = hashlib.scrypt(
            password.encode("utf-8"), salt=base64.urlsafe_b64decode(salt),
            n=int(n), r=int(r), p=int(p), dklen=64, maxmem=192 * 1024 * 1024,
        )
        return secrets.compare_digest(actual, base64.urlsafe_b64decode(expected))
    except (ValueError, TypeError):
        return False


class LoginRateLimiter:
    def __init__(self, attempts: int = 10, window_seconds: int = 15 * 60, max_keys: int = 10_000):
        self.attempts = attempts
        self.window_seconds = window_seconds
        self.max_keys = max_keys
        self._failures: dict[str, deque[float]] = defaultdict(deque)
        self._lock = RLock()

    def allowed(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            failures = self._failures[key]
            while failures and failures[0] <= now - self.window_seconds:
                failures.popleft()
            return len(failures) < self.attempts

    def fail(self, key: str) -> None:
        with self._lock:
            if key not in self._failures and len(self._failures) >= self.max_keys:
                oldest = min(self._failures, key=lambda item: self._failures[item][-1])
                self._failures.pop(oldest, None)
            self._failures[key].append(time.monotonic())

    def success(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)


class AuthStore:
    def __init__(self, database: Path | None = None):
        self.database = database or Path(os.getenv("LITHO_AUTH_DB", "/data/auth.sqlite3"))
        self._lock = RLock()
        self._initialized_for: Path | None = None
        self._dummy_hash: str | None = None

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self) -> None:
        with self._lock:
            database = self.database.resolve()
            if self._initialized_for == database and database.exists():
                return
            database.parent.mkdir(parents=True, exist_ok=True)
            with self._connect() as connection:
                connection.executescript("""
                    PRAGMA journal_mode = WAL;
                    CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                        display_name TEXT NOT NULL,
                        password_hash TEXT NOT NULL,
                        role TEXT NOT NULL CHECK(role IN ('admin', 'operator')),
                        active INTEGER NOT NULL DEFAULT 1,
                        created_at TEXT NOT NULL,
                        password_changed_at TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS sessions (
                        token_hash TEXT PRIMARY KEY,
                        csrf_token TEXT NOT NULL,
                        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        created_at INTEGER NOT NULL,
                        expires_at INTEGER NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS sessions_expires_idx ON sessions(expires_at);
                """)
                count = connection.execute("SELECT COUNT(*) FROM users").fetchone()[0]
                username = os.getenv("LITHO_BOOTSTRAP_ADMIN_USERNAME", "").strip()
                password = os.getenv("LITHO_BOOTSTRAP_ADMIN_PASSWORD", "")
                if count == 0 and username and password:
                    try:
                        bootstrap = UserCreate(
                            username=username,
                            display_name=os.getenv("LITHO_BOOTSTRAP_ADMIN_DISPLAY_NAME", "Administrator"),
                            password=password,
                            role="admin",
                        )
                    except Exception as exc:
                        raise RuntimeError(
                            "Invalid LITHO_BOOTSTRAP_ADMIN_* configuration; password must contain at least 8 characters"
                        ) from exc
                    self._insert_user(connection, bootstrap)
            try:
                database.chmod(0o600)
            except OSError:
                pass
            self._initialized_for = database

    def _insert_user(self, connection: sqlite3.Connection, user: UserCreate) -> dict:
        username = normalize_username(user.username)
        now = _utc_iso()
        cursor = connection.execute(
            "INSERT INTO users(username, display_name, password_hash, role, active, created_at, password_changed_at) VALUES(?,?,?,?,1,?,?)",
            (username, user.display_name.strip(), hash_password(user.password), user.role, now, now),
        )
        return self.get_user(cursor.lastrowid, connection)

    @staticmethod
    def _public_user(row: sqlite3.Row) -> dict:
        return {
            "id": row["id"], "username": row["username"], "display_name": row["display_name"],
            "role": row["role"], "active": bool(row["active"]), "created_at": row["created_at"],
        }

    def get_user(self, user_id: int, connection: sqlite3.Connection | None = None) -> dict:
        owned = connection is None
        connection = connection or self._connect()
        try:
            row = connection.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            if not row:
                raise KeyError(user_id)
            return self._public_user(row)
        finally:
            if owned:
                connection.close()

    def authenticate(self, username: str, password: str) -> dict | None:
        self.initialize()
        try:
            username = normalize_username(username)
        except ValueError:
            username = "invalid-user"
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
            if not row and self._dummy_hash is None:
                with self._lock:
                    if self._dummy_hash is None:
                        self._dummy_hash = hash_password("constant-dummy-password")
            encoded = row["password_hash"] if row else self._dummy_hash
            valid = verify_password(password, encoded)
            if not row or not valid or not row["active"]:
                return None
            return self._public_user(row)

    def create_session(self, user_id: int) -> tuple[str, str]:
        self.initialize()
        token = secrets.token_urlsafe(32)
        csrf = secrets.token_urlsafe(32)
        now = _utc_timestamp()
        with self._connect() as connection:
            connection.execute("DELETE FROM sessions WHERE expires_at <= ?", (now,))
            connection.execute(
                "INSERT INTO sessions(token_hash, csrf_token, user_id, created_at, expires_at) VALUES(?,?,?,?,?)",
                (hashlib.sha256(token.encode()).hexdigest(), csrf, user_id, now, now + SESSION_TTL_SECONDS),
            )
        return token, csrf

    def session(self, token: str | None) -> dict | None:
        if not token:
            return None
        self.initialize()
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT s.csrf_token, s.expires_at, u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=?",
                (token_hash,),
            ).fetchone()
            if not row or row["expires_at"] <= _utc_timestamp() or not row["active"]:
                connection.execute("DELETE FROM sessions WHERE token_hash=?", (token_hash,))
                return None
            user = self._public_user(row)
            user["csrf_token"] = row["csrf_token"]
            return user

    @staticmethod
    def valid_csrf(session: dict, token: str | None) -> bool:
        return bool(token) and secrets.compare_digest(session["csrf_token"], token)

    def destroy_session(self, token: str | None) -> None:
        if not token:
            return
        self.initialize()
        with self._connect() as connection:
            connection.execute("DELETE FROM sessions WHERE token_hash=?", (hashlib.sha256(token.encode()).hexdigest(),))

    def list_users(self) -> list[dict]:
        self.initialize()
        with self._connect() as connection:
            return [self._public_user(row) for row in connection.execute("SELECT * FROM users ORDER BY created_at")]

    def user_count(self) -> int:
        self.initialize()
        with self._connect() as connection:
            return int(connection.execute("SELECT COUNT(*) FROM users").fetchone()[0])

    def create_user(self, user: UserCreate) -> dict:
        self.initialize()
        with self._lock, self._connect() as connection:
            return self._insert_user(connection, user)

    def update_user(self, user_id: int, update: UserUpdate, acting_user_id: int) -> dict:
        self.initialize()
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            current = connection.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
            if not current:
                raise KeyError(user_id)
            removes_admin = current["role"] == "admin" and current["active"] and (update.role != "admin" or not update.active)
            if removes_admin:
                admins = connection.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND active=1").fetchone()[0]
                if admins <= 1:
                    raise RuntimeError("last_admin")
            if user_id == acting_user_id and not update.active:
                raise RuntimeError("self_deactivation")
            connection.execute(
                "UPDATE users SET display_name=?, role=?, active=? WHERE id=?",
                (update.display_name.strip(), update.role, int(update.active), user_id),
            )
            if not update.active:
                connection.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
            return self.get_user(user_id, connection)

    def reset_password(self, user_id: int, new_password: str) -> None:
        self.initialize()
        with self._lock, self._connect() as connection:
            if not connection.execute("SELECT 1 FROM users WHERE id=?", (user_id,)).fetchone():
                raise KeyError(user_id)
            connection.execute(
                "UPDATE users SET password_hash=?, password_changed_at=? WHERE id=?",
                (hash_password(new_password), _utc_iso(), user_id),
            )
            connection.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))


auth_store = AuthStore()
login_limiter = LoginRateLimiter(attempts=10)
password_limiter = LoginRateLimiter(attempts=5)
