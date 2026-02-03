from sqlalchemy import Column, String, Text, Integer, DateTime, Boolean, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from datetime import datetime
from enum import Enum

Base = declarative_base()


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ModelMode(str, Enum):
    FAST = "fast"
    BALANCED = "balanced"
    ACCURATE = "accurate"


class EmailScope(str, Enum):
    UNREAD = "unread"
    INBOX = "inbox"
    RECENT = "recent"
    ALL = "all"


class User(Base):
    __tablename__ = "users"

    id = Column(String(255), primary_key=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(255))
    picture = Column(Text)
    encrypted_access_token = Column(Text)
    encrypted_refresh_token = Column(Text)
    token_expiry = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    last_login = Column(DateTime(timezone=True))
    is_active = Column(Boolean, default=True)


class Job(Base):
    __tablename__ = "jobs"

    id = Column(String(36), primary_key=True)
    user_id = Column(String(255), nullable=False, index=True)
    status = Column(String(20), default=JobStatus.PENDING, index=True)
    mode = Column(String(20), default=ModelMode.FAST)
    scope = Column(String(20), default=EmailScope.UNREAD)
    total_emails = Column(Integer, default=0)
    processed_emails = Column(Integer, default=0)
    error_count = Column(Integer, default=0)
    category_counts = Column(JSON, default=dict)
    errors = Column(JSON, default=list)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    completed_at = Column(DateTime(timezone=True))
    celery_task_id = Column(String(255))


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), unique=True, nullable=False)
    color = Column(String(7), nullable=False)
    description = Column(Text)
    gmail_label = Column(String(100))
    created_at = Column(DateTime(timezone=True), server_default=func.now())