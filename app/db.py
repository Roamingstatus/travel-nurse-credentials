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
    calendar_token = Column(String, nullable=True, unique=True, index=True)

    documents = relationship("Document", back_populates="user", cascade="all, delete-orphan")
    share_links = relationship("ShareLink", back_populates="user", cascade="all, delete-orphan")
    reminder_settings = relationship("ReminderSettings", back_populates="user", uselist=False, cascade="all, delete-orphan")
    reminder_logs = relationship("ReminderLog", foreign_keys="ReminderLog.user_id", cascade="all, delete-orphan")
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
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="reminder_settings")

    def get_days_list(self) -> list[int]:
        try:
            return [int(d.strip()) for d in (self.reminder_days or "30,14,7,0").split(",") if d.strip().isdigit()]
        except Exception:
            return [30, 14, 7, 0]


class ReminderLog(Base):
    __tablename__ = "reminder_logs"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    reminder_type = Column(String, nullable=False)
    days_before = Column(Integer, nullable=False)
    sent_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    status = Column(String, nullable=False, default="sent")
    provider_message_id = Column(String, nullable=True)
    error_message = Column(Text, nullable=True)


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


class ResumeAnalysis(Base):
    __tablename__ = "resume_analyses"

    id             = Column(Integer, primary_key=True)
    user_id        = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    target_role    = Column(String, nullable=True)
    tone           = Column(String, nullable=True)
    overall_score  = Column(Integer, nullable=True)
    category_scores = Column(Text, nullable=True)
    suggestions    = Column(Text, nullable=True)
    created_at     = Column(DateTime, default=datetime.utcnow)


class BetaFeedback(Base):
    __tablename__ = "beta_feedback"

    id               = Column(Integer, primary_key=True)
    user_id          = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    user_email       = Column(String, nullable=True)
    feedback_type    = Column(String, nullable=False)
    feature_area     = Column(String, nullable=False)
    severity         = Column(String, nullable=False, default="medium")
    message          = Column(Text, nullable=False)
    screenshot_filename = Column(String, nullable=True)
    page_url         = Column(String, nullable=True)
    user_agent       = Column(String, nullable=True)
    screen_size      = Column(String, nullable=True)
    status           = Column(String, nullable=False, default="new")
    created_at       = Column(DateTime, default=datetime.utcnow)


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
                if "calendar_token" not in cols:
                    conn.execute(text("ALTER TABLE users ADD COLUMN calendar_token VARCHAR"))
                    conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_calendar_token ON users (calendar_token)"))

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

        if "resume_analyses" not in tables:
            with engine.begin() as conn:
                conn.execute(text(
                    "CREATE TABLE IF NOT EXISTS resume_analyses ("
                    "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
                    "  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,"
                    "  target_role VARCHAR,"
                    "  tone VARCHAR,"
                    "  overall_score INTEGER,"
                    "  category_scores TEXT,"
                    "  suggestions TEXT,"
                    "  created_at DATETIME DEFAULT (datetime('now'))"
                    ")"
                ))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_resume_analyses_user_id ON resume_analyses (user_id)"))

        if "beta_feedback" not in tables:
            with engine.begin() as conn:
                conn.execute(text(
                    "CREATE TABLE IF NOT EXISTS beta_feedback ("
                    "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
                    "  user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,"
                    "  user_email VARCHAR,"
                    "  feedback_type VARCHAR NOT NULL,"
                    "  feature_area VARCHAR NOT NULL,"
                    "  severity VARCHAR NOT NULL DEFAULT 'medium',"
                    "  message TEXT NOT NULL,"
                    "  screenshot_filename VARCHAR,"
                    "  page_url VARCHAR,"
                    "  user_agent VARCHAR,"
                    "  screen_size VARCHAR,"
                    "  status VARCHAR NOT NULL DEFAULT 'new',"
                    "  created_at DATETIME DEFAULT (datetime('now'))"
                    ")"
                ))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_beta_feedback_user_id ON beta_feedback (user_id)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_beta_feedback_status ON beta_feedback (status)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_beta_feedback_created_at ON beta_feedback (created_at)"))

        if "reminder_settings" in tables:
            rs_cols = {c["name"] for c in insp.get_columns("reminder_settings")}
            with engine.begin() as conn:
                if "created_at" not in rs_cols:
                    conn.execute(text("ALTER TABLE reminder_settings ADD COLUMN created_at DATETIME DEFAULT (datetime('now'))"))
                if "updated_at" not in rs_cols:
                    conn.execute(text("ALTER TABLE reminder_settings ADD COLUMN updated_at DATETIME DEFAULT (datetime('now'))"))

        if "recruiter_template_feedback" not in tables:
            with engine.begin() as conn:
                conn.execute(text(
                    "CREATE TABLE IF NOT EXISTS recruiter_template_feedback ("
                    "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
                    "  share_token_id INTEGER REFERENCES share_links(id) ON DELETE SET NULL,"
                    "  role_type VARCHAR NOT NULL,"
                    "  required_documents TEXT NOT NULL DEFAULT '[]',"
                    "  timing VARCHAR NOT NULL,"
                    "  agency_type VARCHAR NOT NULL,"
                    "  optional_email VARCHAR,"
                    "  user_agent VARCHAR,"
                    "  created_at DATETIME DEFAULT (datetime('now'))"
                    ")"
                ))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_rtf_created_at ON recruiter_template_feedback (created_at)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_rtf_role_type ON recruiter_template_feedback (role_type)"))

        if "reminder_logs" not in tables:
            with engine.begin() as conn:
                conn.execute(text(
                    "CREATE TABLE IF NOT EXISTS reminder_logs ("
                    "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
                    "  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,"
                    "  document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,"
                    "  reminder_type VARCHAR NOT NULL,"
                    "  days_before INTEGER NOT NULL,"
                    "  sent_at DATETIME NOT NULL DEFAULT (datetime('now')),"
                    "  status VARCHAR NOT NULL DEFAULT 'sent',"
                    "  provider_message_id VARCHAR,"
                    "  error_message TEXT"
                    ")"
                ))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_reminder_logs_user_id ON reminder_logs (user_id)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_reminder_logs_sent_at ON reminder_logs (sent_at)"))

        if "test_runs" not in tables:
            with engine.begin() as conn:
                conn.execute(text(
                    "CREATE TABLE IF NOT EXISTS test_runs ("
                    "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
                    "  total_tests INTEGER NOT NULL DEFAULT 0,"
                    "  passed_tests INTEGER NOT NULL DEFAULT 0,"
                    "  failed_tests INTEGER NOT NULL DEFAULT 0,"
                    "  duration_ms INTEGER NOT NULL DEFAULT 0,"
                    "  created_at DATETIME DEFAULT (datetime('now'))"
                    ")"
                ))

        if "test_failures" not in tables:
            with engine.begin() as conn:
                conn.execute(text(
                    "CREATE TABLE IF NOT EXISTS test_failures ("
                    "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
                    "  run_id INTEGER NOT NULL REFERENCES test_runs(id) ON DELETE CASCADE,"
                    "  test_name VARCHAR NOT NULL,"
                    "  error_message TEXT,"
                    "  created_at DATETIME DEFAULT (datetime('now'))"
                    ")"
                ))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_test_failures_run_id ON test_failures (run_id)"))

    except Exception:
        pass


def get_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
