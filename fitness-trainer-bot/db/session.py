import os
import sqlite3
from pathlib import Path
from typing import Optional, Dict, Any


def get_db_path() -> Path:
    env_path = os.getenv("SQLITE_PATH")
    if env_path:
        return Path(env_path).expanduser().resolve()
    return Path(__file__).resolve().parent / "app.sqlite3"


def connect(db_path: Optional[Path] = None) -> sqlite3.Connection:
    path = db_path or get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path.as_posix())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL UNIQUE,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                age INTEGER,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            """
        )
        conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS trg_users_updated_at
            AFTER UPDATE ON users
            FOR EACH ROW
            BEGIN
                UPDATE users SET updated_at = datetime('now') WHERE id = NEW.id;
            END;
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL,
                tariff_code TEXT NOT NULL,
                out_sum REAL NOT NULL,
                inv_id INTEGER NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT 'pending',
                description TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                paid_at TEXT
            );
            """
        )


def get_user_by_telegram_id(telegram_id: int) -> Optional[Dict[str, Any]]:
    """
    Возвращает данные пользователя по его Telegram ID или None, если такого пользователя нет.
    """
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE telegram_id = ?;",
            (telegram_id,),
        ).fetchone()
        return dict(row) if row is not None else None


def upsert_user(
    *,
    telegram_id: int,
    username: Optional[str],
    first_name: str,
    last_name: str,
    age: int,
) -> int:
    """
    Inserts user if new, updates fields if telegram_id exists.
    Returns internal DB user id (users.id).
    """
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO users (telegram_id, username, first_name, last_name, age)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name,
                last_name = excluded.last_name,
                age = excluded.age;
            """,
            (telegram_id, username, first_name, last_name, age),
        )
        row = conn.execute("SELECT id FROM users WHERE telegram_id = ?;", (telegram_id,)).fetchone()
        return int(row["id"])


def create_payment(
    *,
    telegram_id: int,
    tariff_code: str,
    out_sum: float,
    inv_id: int,
    description: str,
    status: str = "pending",
) -> int:
    """
    Создаёт запись о платеже и возвращает её id.
    """
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO payments (telegram_id, tariff_code, out_sum, inv_id, status, description)
            VALUES (?, ?, ?, ?, ?, ?);
            """,
            (telegram_id, tariff_code, out_sum, inv_id, status, description),
        )
        row = conn.execute("SELECT id FROM payments WHERE inv_id = ?;", (inv_id,)).fetchone()
        return int(row["id"])


def update_payment_status(inv_id: int, status: str) -> None:
    with connect() as conn:
        if status == "success":
            conn.execute(
                """
                UPDATE payments
                SET status = ?, paid_at = datetime('now')
                WHERE inv_id = ?;
                """,
                (status, inv_id),
            )
        else:
            conn.execute(
                "UPDATE payments SET status = ? WHERE inv_id = ?;",
                (status, inv_id),
            )


def get_payment_by_inv_id(inv_id: int) -> Optional[Dict[str, Any]]:
    with connect() as conn:
        row = conn.execute("SELECT * FROM payments WHERE inv_id = ?;", (inv_id,)).fetchone()
        return dict(row) if row is not None else None

