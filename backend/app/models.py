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


class ReportSession(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    course_id: str | None = None
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
    student_name: str
    course_name: str
    assignment_name: str
    assignment_requirements: str = ""
    original_filename: str
    created_at: datetime
    status: AnalysisStatus
    error: str | None = None


class AnalysisResponse(BaseModel):
    session: SessionSummary
    result: dict[str, Any] | None = None


class SystemConfigIn(BaseModel):
    dashscope_api_key: str = Field(default="", min_length=0)
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    dashscope_text_model: str = "qwen-long"


class SystemConfigOut(BaseModel):
    configured: bool
    dashscope_api_key_masked: str = ""
    dashscope_base_url: str
    dashscope_text_model: str


class ConfigCheckResponse(BaseModel):
    configured: bool
    message: str


class CourseCreate(BaseModel):
    name: str
    teacher_name: str = ""
    assignment_name: str
    assignment_requirements: str


class Course(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex[:8])
    name: str
    teacher_name: str = ""
    assignment_name: str
    assignment_requirements: str
    created_at: datetime = Field(default_factory=datetime.now)


class CourseSummary(BaseModel):
    id: str
    name: str
    teacher_name: str
    assignment_name: str
    assignment_requirements: str
    created_at: datetime
    submission_count: int


class CourseDetail(BaseModel):
    course: CourseSummary
    submissions: list[SessionSummary]
