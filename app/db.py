import json
from datetime import datetime
from pathlib import Path

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    inspect,
    text,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "app.db"

engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},
    future=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    google_sub = Column(String, unique=True, nullable=False, index=True)
    email = Column(String, nullable=False)
    name = Column(String, nullable=True)
    picture = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    subscription_tier = Column(String, default="free", nullable=False)
    stripe_customer_id = Column(String, nullable=True, index=True)
    stripe_subscription_id = Column(String, nullable=True)
    mfa_enabled = Column(Boolean, default=False, nullable=False, server_default="0")
    mfa_method = Column(String, nullable=True)
    mfa_totp_secret = Column(String, nullable=True)
    mfa_recovery_codes = Column(Text, nullable=True)
    phone_number = Column(String, nullable=True)
    phone_verified = Column(Boolean, default=False, nullable=False, server_default="0")

    documents = relationship("Document", back_populates="user", cascade="all, delete-orphan")
    share_links = relationship("ShareLink", back_populates="user", cascade="all, delete-orphan")
    reminder_settings = relationship("ReminderSettings", back_populates="user", uselist=False, cascade="all, delete-orphan")
    checklist_results = relationship("ChecklistResult", back_populates="user", cascade="all, delete-orphan")


class Document(Base):
    __tablename__ = "documents"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    profile_id = Column(Integer, nullable=True, index=True)
    category = Column(String, nullable=False)
    title = Column(String, nullable=False)
    notes = Column(Text, nullable=True)
    issued_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    stored_filename = Column(String, nullable=False)
    original_filename = Column(String, nullable=False)
    mime_type = Column(String, nullable=False)
    size_bytes = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    content_hash = Column(String(64), nullable=True, index=True)
    sort_order = Column(Integer, nullable=True, default=0)
    expiration_rule_applied = Column(String, nullable=True)
    expiration_source = Column(String, nullable=True)
    issuing_state = Column(String(2), nullable=True)

    user = relationship("User", back_populates="documents")


class ShareLink(Base):
    __tablename__ = "share_links"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    token = Column(String, unique=True, nullable=False, index=True)
    label = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)
    profile_id = Column(Integer, nullable=True, index=True)

    user = relationship("User", back_populates="share_links")


class ReminderSettings(Base):
    __tablename__ = "reminder_settings"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True, index=True)
    email_enabled = Column(Integer, default=0)
    sms_enabled = Column(Integer, default=0)
    reminder_email = Column(String, nullable=True)
    phone_number = Column(String, nullable=True)
    reminder_days = Column(String, default="30,14,7,0")

    user = relationship("User", back_populates="reminder_settings")

    def get_days_list(self) -> list[int]:
        try:
            return [int(d.strip()) for d in (self.reminder_days or "30,14,7,0").split(",") if d.strip().isdigit()]
        except Exception:
            return [30, 14, 7, 0]


class Event(Base):
    __tablename__ = "events"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    event_type = Column(String, nullable=False, index=True)
    meta = Column(Text, nullable=True)
    ok = Column(Integer, default=1, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class ChecklistResult(Base):
    __tablename__ = "checklist_results"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    profile_type = Column(String, nullable=False)
    missing_items = Column(Text, nullable=True)
    completed_items = Column(Text, nullable=True)
    expiring_items = Column(Text, nullable=True)
    expired_items = Column(Text, nullable=True)
    readiness_score = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="checklist_results")

    def get_missing(self) -> list[str]:
        try:
            return json.loads(self.missing_items or "[]")
        except Exception:
            return []

    def get_completed(self) -> list[str]:
        try:
            return json.loads(self.completed_items or "[]")
        except Exception:
            return []

    def get_expiring(self) -> list[str]:
        try:
            return json.loads(self.expiring_items or "[]")
        except Exception:
            return []

    def get_expired(self) -> list[str]:
        try:
            return json.loads(self.expired_items or "[]")
        except Exception:
            return []


def init_db() -> None:
    Base.metadata.create_all(engine)
    _ensure_sqlite_columns()


def _ensure_sqlite_columns() -> None:
    try:
        insp = inspect(engine)
        tables = insp.get_table_names()

        if "events" not in tables:
            with engine.begin() as conn:
                conn.execute(text(
                    "CREATE TABLE IF NOT EXISTS events ("
                    "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
                    "  user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,"
                    "  event_type VARCHAR NOT NULL,"
                    "  meta TEXT,"
                    "  ok INTEGER NOT NULL DEFAULT 1,"
                    "  created_at DATETIME DEFAULT (datetime('now'))"
                    ")"
                ))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_events_event_type ON events (event_type)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_events_created_at ON events (created_at)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_events_user_id ON events (user_id)"))

        if "users" in tables:
            cols = {c["name"] for c in insp.get_columns("users")}
            with engine.begin() as conn:
                if "subscription_tier" not in cols:
                    conn.execute(text("ALTER TABLE users ADD COLUMN subscription_tier VARCHAR DEFAULT 'free'"))
                if "stripe_customer_id" not in cols:
                    conn.execute(text("ALTER TABLE users ADD COLUMN stripe_customer_id VARCHAR"))
                if "stripe_subscription_id" not in cols:
                    conn.execute(text("ALTER TABLE users ADD COLUMN stripe_subscription_id VARCHAR"))
                if "mfa_enabled" not in cols:
                    conn.execute(text("ALTER TABLE users ADD COLUMN mfa_enabled INTEGER NOT NULL DEFAULT 0"))
                if "mfa_method" not in cols:
                    conn.execute(text("ALTER TABLE users ADD COLUMN mfa_method VARCHAR"))
                if "mfa_totp_secret" not in cols:
                    conn.execute(text("ALTER TABLE users ADD COLUMN mfa_totp_secret VARCHAR"))
                if "mfa_recovery_codes" not in cols:
                    conn.execute(text("ALTER TABLE users ADD COLUMN mfa_recovery_codes TEXT"))
                if "phone_number" not in cols:
                    conn.execute(text("ALTER TABLE users ADD COLUMN phone_number VARCHAR"))
                if "phone_verified" not in cols:
                    conn.execute(text("ALTER TABLE users ADD COLUMN phone_verified INTEGER NOT NULL DEFAULT 0"))

        if "documents" in tables:
            cols = {c["name"] for c in insp.get_columns("documents")}
            with engine.begin() as conn:
                if "content_hash" not in cols:
                    conn.execute(text("ALTER TABLE documents ADD COLUMN content_hash VARCHAR(64)"))
                if "profile_id" not in cols:
                    conn.execute(text("ALTER TABLE documents ADD COLUMN profile_id INTEGER"))
                if "sort_order" not in cols:
                    conn.execute(text("ALTER TABLE documents ADD COLUMN sort_order INTEGER DEFAULT 0"))
                if "expiration_rule_applied" not in cols:
                    conn.execute(text("ALTER TABLE documents ADD COLUMN expiration_rule_applied VARCHAR"))
                if "expiration_source" not in cols:
                    conn.execute(text("ALTER TABLE documents ADD COLUMN expiration_source VARCHAR"))
                if "issuing_state" not in cols:
                    conn.execute(text("ALTER TABLE documents ADD COLUMN issuing_state VARCHAR(2)"))

        if "share_links" in tables:
            cols = {c["name"] for c in insp.get_columns("share_links")}
            with engine.begin() as conn:
                if "profile_id" not in cols:
                    conn.execute(text("ALTER TABLE share_links ADD COLUMN profile_id INTEGER"))
    except Exception:
        pass


def get_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
