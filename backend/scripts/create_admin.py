from getpass import getpass

from sqlalchemy import func, select

from app.core.security import hash_password
from app.database import SessionLocal
from app.models import User

email = input("Admin email: ").strip().lower()
name = input("Admin display name: ").strip()
if "@" not in email or len(name) < 2:
    raise SystemExit("Enter a valid email and a name of at least two characters.")
password = getpass("Admin password (8+ characters): ")
if len(password) < 8:
    raise SystemExit("Password must be at least 8 characters.")
if password != getpass("Confirm admin password: "):
    raise SystemExit("Passwords did not match.")

with SessionLocal() as db:
    user = db.scalar(select(User).where(func.lower(User.email) == email))
    if user is None:
        user = User(name=name, email=email, password_hash=hash_password(password), role="admin")
        db.add(user)
        action = "created"
    else:
        confirmation = input(f"Type PROMOTE {email} to grant this existing account admin access: ")
        if confirmation != f"PROMOTE {email}":
            raise SystemExit("Promotion cancelled; no account changes were made.")
        user.role = "admin"
        user.name = name
        user.password_hash = hash_password(password)
        action = "promoted"
    db.commit()

print(f"Admin account {action}: {email}")
