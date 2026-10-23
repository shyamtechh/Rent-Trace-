import sqlite3
from datetime import datetime
from pathlib import Path

from sqlalchemy import func, select, text

from app.core.config import DATABASE_URL
from app.database import SessionLocal
from app.models import User

SQLITE_PATH = Path(__file__).resolve().parents[1] / "data" / "renttrace.db"
if DATABASE_URL.startswith("sqlite"):
    raise SystemExit("Set DATABASE_URL to PostgreSQL before importing legacy SQLite users.")
if not SQLITE_PATH.exists():
    raise SystemExit(f"Legacy SQLite database not found: {SQLITE_PATH}")

source = sqlite3.connect(f"file:{SQLITE_PATH.as_posix()}?mode=ro", uri=True)
source.row_factory = sqlite3.Row
columns = {column[1] for column in source.execute("PRAGMA table_info(users)")}
required = {"id", "name", "email", "password_hash"}
if not required.issubset(columns):
    source.close()
    raise SystemExit("Legacy users table does not contain the expected columns; no data was copied.")
legacy_users = [dict(row) for row in source.execute("SELECT * FROM users ORDER BY id")]
source.close()

inserted = 0
skipped = 0
with SessionLocal() as target:
    try:
        for row in legacy_users:
            email = row["email"].strip().lower()
            exists = target.scalar(select(User.id).where(func.lower(User.email) == email))
            if exists is not None:
                skipped += 1
                continue
            created_at = row.get("created_at")
            if isinstance(created_at, str):
                try:
                    created_at = datetime.fromisoformat(created_at)
                except ValueError:
                    created_at = None
            updated_at = row.get("updated_at")
            if isinstance(updated_at, str):
                try:
                    updated_at = datetime.fromisoformat(updated_at)
                except ValueError:
                    updated_at = None
            target.add(User(
                id=row["id"],
                name=row["name"],
                email=email,
                password_hash=row["password_hash"],
                role=row.get("role") or "user",
                is_active=bool(row.get("is_active", 1)),
                created_at=created_at,
                updated_at=updated_at or created_at,
            ))
            inserted += 1
        if target.get_bind().dialect.name == "postgresql":
            target.execute(text(
                "SELECT setval(pg_get_serial_sequence('users', 'id'), "
                "GREATEST(COALESCE((SELECT MAX(id) FROM users), 1), 1), "
                "EXISTS(SELECT 1 FROM users))"
            ))
        target.commit()
    except Exception:
        target.rollback()
        raise

print(f"Legacy users copied: {inserted}; already present and skipped: {skipped}.")
print("The original SQLite file was opened read-only and was not modified or deleted.")
