from __future__ import annotations

import hashlib
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import pymysql
from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    ForeignKey,
    String,
    Text,
    create_engine,
    func,
    select,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

from backend.app.models import AnalysisStatus, UserRole

DEFAULT_DATABASE_URL = "mysql+pymysql://root:root@127.0.0.1:3306/voiceTA?charset=utf8mb4"
DATABASE_URL = os.getenv("VOICE_TA_DATABASE_URL", DEFAULT_DATABASE_URL)


class Base(DeclarativeBase):
    pass


class UserRow(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(64))
    display_name: Mapped[str] = mapped_column(String(64))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class CourseRow(Base):
    __tablename__ = "courses"

    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    teacher_name: Mapped[str] = mapped_column(String(64), default="")
    teacher_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    assignment_name: Mapped[str] = mapped_column(String(160))
    assignment_requirements: Mapped[str] = mapped_column(Text)
    assignment_spec: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    reports: Mapped[list["ReportRow"]] = relationship(back_populates="course")
    enrollments: Mapped[list["CourseEnrollmentRow"]] = relationship(back_populates="course")


class CourseEnrollmentRow(Base):
    __tablename__ = "course_enrollments"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id"), index=True)
    student_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    student_name: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    course: Mapped[CourseRow] = relationship(back_populates="enrollments")


class ReportRow(Base):
    __tablename__ = "reports"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    course_id: Mapped[str | None] = mapped_column(ForeignKey("courses.id"), nullable=True, index=True)
    student_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    student_name: Mapped[str] = mapped_column(String(64))
    course_name: Mapped[str] = mapped_column(String(120))
    assignment_name: Mapped[str] = mapped_column(String(160))
    assignment_requirements: Mapped[str] = mapped_column(Text, default="")
    original_filename: Mapped[str] = mapped_column(String(255))
    stored_path: Mapped[str] = mapped_column(String(500))
    stage_id: Mapped[str] = mapped_column(String(32), default="all")
    submission_files: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    assignment_spec: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    status: Mapped[AnalysisStatus] = mapped_column(Enum(AnalysisStatus), default=AnalysisStatus.pending)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    course: Mapped[CourseRow | None] = relationship(back_populates="reports")
    qa_records: Mapped[list["QARecordRow"]] = relationship(back_populates="report")


class QARecordRow(Base):
    __tablename__ = "qa_records"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    report_id: Mapped[str] = mapped_column(ForeignKey("reports.id"), index=True)
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    created_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    report: Mapped[ReportRow] = relationship(back_populates="qa_records")


def _server_url() -> str:
    return DATABASE_URL.rsplit("/", 1)[0]


def init_database() -> None:
    _ensure_database_exists()
    Base.metadata.create_all(bind=engine)
    _ensure_compatible_schema()
    _seed_default_users()
    from backend.app.course_catalog import seed_courses
    seed_courses()


def _ensure_database_exists() -> None:
    connection = pymysql.connect(
        host=os.getenv("VOICE_TA_DB_HOST", "127.0.0.1"),
        port=int(os.getenv("VOICE_TA_DB_PORT", "3306")),
        user=os.getenv("VOICE_TA_DB_USER", "root"),
        password=os.getenv("VOICE_TA_DB_PASSWORD", "root"),
        charset="utf8mb4",
        autocommit=True,
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "CREATE DATABASE IF NOT EXISTS voiceTA "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
    finally:
        connection.close()


def _ensure_compatible_schema() -> None:
    statements = [
        ("courses", "assignment_spec", "ALTER TABLE courses ADD COLUMN assignment_spec JSON NULL"),
        ("reports", "stage_id", "ALTER TABLE reports ADD COLUMN stage_id VARCHAR(32) NOT NULL DEFAULT 'all'"),
        ("reports", "submission_files", "ALTER TABLE reports ADD COLUMN submission_files JSON NULL"),
        ("reports", "assignment_spec", "ALTER TABLE reports ADD COLUMN assignment_spec JSON NULL"),
        ("users", "password_hash", "ALTER TABLE users ADD COLUMN password_hash VARCHAR(64) NOT NULL DEFAULT ''"),
        ("users", "display_name", "ALTER TABLE users ADD COLUMN display_name VARCHAR(64) NOT NULL DEFAULT ''"),
        ("users", "role", "ALTER TABLE users ADD COLUMN role VARCHAR(16) NOT NULL DEFAULT 'student'"),
        ("users", "created_at", "ALTER TABLE users ADD COLUMN created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP"),
        ("courses", "teacher_name", "ALTER TABLE courses ADD COLUMN teacher_name VARCHAR(64) NOT NULL DEFAULT ''"),
        ("courses", "teacher_user_id", "ALTER TABLE courses ADD COLUMN teacher_user_id VARCHAR(32) NULL"),
        ("courses", "assignment_name", "ALTER TABLE courses ADD COLUMN assignment_name VARCHAR(160) NOT NULL DEFAULT '课程报告'"),
        ("courses", "assignment_requirements", "ALTER TABLE courses ADD COLUMN assignment_requirements TEXT NOT NULL"),
        ("courses", "created_at", "ALTER TABLE courses ADD COLUMN created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP"),
        ("reports", "student_user_id", "ALTER TABLE reports ADD COLUMN student_user_id VARCHAR(32) NULL"),
        ("reports", "student_name", "ALTER TABLE reports ADD COLUMN student_name VARCHAR(64) NOT NULL DEFAULT ''"),
        ("reports", "course_name", "ALTER TABLE reports ADD COLUMN course_name VARCHAR(120) NOT NULL DEFAULT ''"),
        ("reports", "assignment_name", "ALTER TABLE reports ADD COLUMN assignment_name VARCHAR(160) NOT NULL DEFAULT '课程报告'"),
        ("reports", "assignment_requirements", "ALTER TABLE reports ADD COLUMN assignment_requirements TEXT NOT NULL"),
        ("reports", "original_filename", "ALTER TABLE reports ADD COLUMN original_filename VARCHAR(255) NOT NULL DEFAULT ''"),
        ("reports", "stored_path", "ALTER TABLE reports ADD COLUMN stored_path VARCHAR(500) NOT NULL DEFAULT ''"),
        ("reports", "created_at", "ALTER TABLE reports ADD COLUMN created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP"),
        ("reports", "status", "ALTER TABLE reports ADD COLUMN status VARCHAR(16) NOT NULL DEFAULT 'pending'"),
        ("reports", "result", "ALTER TABLE reports ADD COLUMN result JSON NULL"),
        ("reports", "error", "ALTER TABLE reports ADD COLUMN error TEXT NULL"),
        ("course_enrollments", "id", "ALTER TABLE course_enrollments ADD COLUMN id VARCHAR(32) NOT NULL"),
        ("course_enrollments", "course_id", "ALTER TABLE course_enrollments ADD COLUMN course_id VARCHAR(16) NOT NULL"),
        ("course_enrollments", "student_user_id", "ALTER TABLE course_enrollments ADD COLUMN student_user_id VARCHAR(32) NOT NULL"),
        ("course_enrollments", "student_name", "ALTER TABLE course_enrollments ADD COLUMN student_name VARCHAR(64) NOT NULL DEFAULT ''"),
        ("course_enrollments", "created_at", "ALTER TABLE course_enrollments ADD COLUMN created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP"),
    ]
    with engine.begin() as connection:
        for table_name, column_name, statement in statements:
            exists = connection.scalar(
                text(
                    "SELECT COUNT(*) FROM information_schema.columns "
                    "WHERE table_schema = DATABASE() "
                    "AND table_name = :table_name "
                    "AND column_name = :column_name"
                ),
                {"table_name": table_name, "column_name": column_name},
            )
            if not exists:
                connection.execute(text(statement))


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def _seed_default_users() -> None:
    defaults = [
        ("admin", "admin123", "系统管理员", UserRole.admin),
        ("teacher", "teacher123", "默认老师", UserRole.teacher),
        ("student", "student123", "默认学生", UserRole.student),
    ]
    with SessionLocal() as db:
        for username, password, display_name, role in defaults:
            exists = db.scalar(select(UserRow).where(UserRow.username == username))
            if exists:
                continue
            db.add(
                UserRow(
                    id=hashlib.md5(username.encode("utf-8")).hexdigest(),
                    username=username,
                    password_hash=hash_password(password),
                    display_name=display_name,
                    role=role,
                )
            )
        db.commit()


engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def count_reports_for_course(db: Session, course_id: str) -> int:
    return db.scalar(select(func.count(ReportRow.id)).where(ReportRow.course_id == course_id)) or 0
