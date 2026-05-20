from __future__ import annotations

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class AnalysisStatus(str, Enum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class UserRole(str, Enum):
    admin = "admin"
    teacher = "teacher"
    student = "student"


class UserLogin(BaseModel):
    username: str
    password: str


class UserRegister(BaseModel):
    username: str
    password: str
    display_name: str = ""


class UserOut(BaseModel):
    id: str
    username: str
    display_name: str
    role: UserRole


class UserRoleUpdate(BaseModel):
    role: UserRole


class ReportSession(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    course_id: str | None = None
    student_user_id: str | None = None
    student_name: str
    course_name: str
    assignment_name: str
    assignment_requirements: str = ""
    original_filename: str
    stored_path: Path
    created_at: datetime = Field(default_factory=datetime.now)
    status: AnalysisStatus = AnalysisStatus.pending
    result: dict[str, Any] | None = None
    error: str | None = None


class SessionSummary(BaseModel):
    id: str
    course_id: str | None = None
    student_user_id: str | None = None
    student_name: str
    course_name: str
    assignment_name: str
    assignment_requirements: str = ""
    original_filename: str
    created_at: datetime
    status: AnalysisStatus
    error: str | None = None
    voice_qa_summary_ready: bool = False


class AnalysisResponse(BaseModel):
    session: SessionSummary
    result: dict[str, Any] | None = None


class VoiceQASummaryResponse(BaseModel):
    session: SessionSummary
    qa_records: list["QARecord"]
    summary: str


class SystemConfigIn(BaseModel):
    dashscope_api_key: str = Field(default="", min_length=0)
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    dashscope_text_model: str = "qwen-long"
    volc_realtime_app_id: str = Field(default="", min_length=0)
    volc_realtime_access_key: str = Field(default="", min_length=0)
    volc_realtime_app_key: str = Field(default="", min_length=0)


class SystemConfigOut(BaseModel):
    configured: bool
    dashscope_api_key_masked: str = ""
    dashscope_base_url: str
    dashscope_text_model: str
    realtime_configured: bool = False
    volc_realtime_app_id_masked: str = ""
    volc_realtime_access_key_masked: str = ""
    volc_realtime_app_key_masked: str = ""


class ConfigCheckResponse(BaseModel):
    configured: bool
    message: str


class CourseCreate(BaseModel):
    name: str
    teacher_name: str = ""
    teacher_user_id: str | None = None
    assignment_name: str
    assignment_requirements: str


class Course(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex[:8])
    name: str
    teacher_name: str = ""
    teacher_user_id: str | None = None
    assignment_name: str
    assignment_requirements: str
    created_at: datetime = Field(default_factory=datetime.now)


class CourseSummary(BaseModel):
    id: str
    name: str
    teacher_name: str
    teacher_user_id: str | None = None
    assignment_name: str
    assignment_requirements: str
    created_at: datetime
    submission_count: int
    student_count: int = 0
    analyzed_count: int = 0
    summarized_count: int = 0


class CourseDetail(BaseModel):
    course: CourseSummary
    submissions: list[SessionSummary]


class CourseJoinRequest(BaseModel):
    student_user_id: str
    student_name: str = ""


class StudentCourse(BaseModel):
    course: CourseSummary
    latest_submission: SessionSummary | None = None


class QARecordCreate(BaseModel):
    question: str
    answer: str
    created_by_user_id: str | None = None


class QARecord(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    report_id: str
    question: str
    answer: str
    created_by_user_id: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)
