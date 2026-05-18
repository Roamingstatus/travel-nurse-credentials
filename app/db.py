from datetime import datetime
from pathlib import Path

from sqlalchemy import (
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

    documents = relationship("Document", back_populates="user", cascade="all, delete-orphan")
    share_links = relationship("ShareLink", back_populates="user", cascade="all, delete-orphan")


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


def init_db() -> None:
    Base.metadata.create_all(engine)
    _ensure_sqlite_columns()


def _ensure_sqlite_columns() -> None:
    try:
        insp = inspect(engine)
        tables = insp.get_table_names()
        if "documents" in tables:
            cols = {c["name"] for c in insp.get_columns("documents")}
            with engine.begin() as conn:
                if "content_hash" not in cols:
                    conn.execute(text("ALTER TABLE documents ADD COLUMN content_hash VARCHAR(64)"))
                if "profile_id" not in cols:
                    conn.execute(text("ALTER TABLE documents ADD COLUMN profile_id INTEGER"))
        if "documents" in tables:
            cols = {c["name"] for c in insp.get_columns("documents")}
            with engine.begin() as conn:
                if "sort_order" not in cols:
                    conn.execute(text("ALTER TABLE documents ADD COLUMN sort_order INTEGER DEFAULT 0"))
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
