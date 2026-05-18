from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from backend.app.models import (
    AnalysisResponse,
    ConfigCheckResponse,
    Course,
    CourseCreate,
    CourseDetail,
    CourseSummary,
    ReportSession,
    SessionSummary,
    SystemConfigIn,
    SystemConfigOut,
)
from backend.app.services.config_store import MissingConfigError, config_store
from backend.app.services.dashscope_analyzer import analyze_report_file
from backend.app.store import store

BASE_DIR = Path(__file__).resolve().parents[2]
UPLOAD_DIR = BASE_DIR / "data" / "uploads"
ALLOWED_EXTENSIONS = {".pdf", ".doc", ".docx", ".md", ".txt"}

app = FastAPI(title="课程报告智能助教 API", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _summary(session: ReportSession) -> SessionSummary:
    return SessionSummary(
        id=session.id,
        course_id=session.course_id,
        student_name=session.student_name,
        course_name=session.course_name,
        assignment_name=session.assignment_name,
        assignment_requirements=session.assignment_requirements,
        original_filename=session.original_filename,
        created_at=session.created_at,
        status=session.status,
        error=session.error,
    )


def _course_summary(course: Course) -> CourseSummary:
    return CourseSummary(
        id=course.id,
        name=course.name,
        teacher_name=course.teacher_name,
        assignment_name=course.assignment_name,
        assignment_requirements=course.assignment_requirements,
        created_at=course.created_at,
        submission_count=store.course_submission_count(course.id),
    )


def _analyze_in_background(session_id: str) -> None:
    session = store.get(session_id)
    if session is None:
        return

    store.mark_processing(session_id)
    try:
        config = config_store.require_private()
        result = analyze_report_file(
            file_path=session.stored_path,
            student_name=session.student_name,
            course_name=session.course_name,
            assignment_name=session.assignment_name,
            assignment_requirements=session.assignment_requirements,
            config=config,
        )
        store.mark_completed(session_id, result)
    except Exception as exc:
        store.mark_failed(session_id, str(exc))


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/config", response_model=SystemConfigOut)
def get_config() -> SystemConfigOut:
    return config_store.read_public()


@app.put("/api/config", response_model=SystemConfigOut)
def save_config(config: SystemConfigIn) -> SystemConfigOut:
    return config_store.save(config)


@app.get("/api/config/check", response_model=ConfigCheckResponse)
def check_config() -> ConfigCheckResponse:
    configured = config_store.read_public().configured
    return ConfigCheckResponse(
        configured=configured,
        message="配置已完成" if configured else "请先在系统配置页面填写 DashScope API Key。",
    )


@app.post("/api/courses", response_model=CourseSummary)
def create_course(payload: CourseCreate) -> CourseSummary:
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="课程名称不能为空。")
    if not payload.assignment_name.strip():
        raise HTTPException(status_code=400, detail="作业名称不能为空。")
    if not payload.assignment_requirements.strip():
        raise HTTPException(status_code=400, detail="作业要求不能为空。")

    course = store.add_course(
        Course(
            name=payload.name.strip(),
            teacher_name=payload.teacher_name.strip(),
            assignment_name=payload.assignment_name.strip(),
            assignment_requirements=payload.assignment_requirements.strip(),
        )
    )
    return _course_summary(course)


@app.get("/api/courses", response_model=list[CourseSummary])
def list_courses() -> list[CourseSummary]:
    return [_course_summary(course) for course in store.list_courses()]


@app.get("/api/courses/{course_id}", response_model=CourseDetail)
def get_course(course_id: str) -> CourseDetail:
    course = store.get_course(course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="课程不存在。")
    return CourseDetail(
        course=_course_summary(course),
        submissions=[_summary(session) for session in store.list_by_course(course_id)],
    )


@app.get("/api/courses/{course_id}/sessions", response_model=list[SessionSummary])
def list_course_sessions(course_id: str) -> list[SessionSummary]:
    if store.get_course(course_id) is None:
        raise HTTPException(status_code=404, detail="课程不存在。")
    return [_summary(session) for session in store.list_by_course(course_id)]


@app.post("/api/courses/{course_id}/sessions", response_model=AnalysisResponse)
async def create_course_session(
    course_id: str,
    background_tasks: BackgroundTasks,
    student_name: str = Form(...),
    report_file: UploadFile = File(...),
) -> AnalysisResponse:
    course = store.get_course(course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="课程不存在。")

    return await _create_report_session(
        background_tasks=background_tasks,
        student_name=student_name,
        course_name=course.name,
        assignment_name=course.assignment_name,
        assignment_requirements=course.assignment_requirements,
        report_file=report_file,
        course_id=course.id,
    )


@app.post("/api/sessions", response_model=AnalysisResponse)
async def create_session(
    background_tasks: BackgroundTasks,
    student_name: str = Form(...),
    course_name: str = Form(...),
    assignment_name: str = Form(...),
    assignment_requirements: str = Form(""),
    report_file: UploadFile = File(...),
) -> AnalysisResponse:
    return await _create_report_session(
        background_tasks=background_tasks,
        student_name=student_name,
        course_name=course_name,
        assignment_name=assignment_name,
        assignment_requirements=assignment_requirements,
        report_file=report_file,
    )


async def _create_report_session(
    *,
    background_tasks: BackgroundTasks,
    student_name: str,
    course_name: str,
    assignment_name: str,
    assignment_requirements: str,
    report_file: UploadFile,
    course_id: str | None = None,
) -> AnalysisResponse:
    try:
        config_store.require_private()
    except MissingConfigError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    suffix = Path(report_file.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"暂不支持 {suffix or '无扩展名'} 文件，请上传 PDF、Word、Markdown 或文本文件。",
        )

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    temp_session = ReportSession(
        course_id=course_id,
        student_name=student_name.strip(),
        course_name=course_name.strip(),
        assignment_name=assignment_name.strip(),
        assignment_requirements=assignment_requirements.strip(),
        original_filename=report_file.filename or f"report{suffix}",
        stored_path=UPLOAD_DIR / "pending",
    )
    stored_path = UPLOAD_DIR / f"{temp_session.id}{suffix}"

    with stored_path.open("wb") as output:
        shutil.copyfileobj(report_file.file, output)

    temp_session.stored_path = stored_path
    session = store.add(temp_session)
    background_tasks.add_task(_analyze_in_background, session.id)
    return AnalysisResponse(session=_summary(session), result=None)


@app.get("/api/sessions", response_model=list[SessionSummary])
def list_sessions() -> list[SessionSummary]:
    return [_summary(session) for session in store.list()]


@app.get("/api/sessions/{session_id}", response_model=AnalysisResponse)
def get_session(session_id: str) -> AnalysisResponse:
    session = store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return AnalysisResponse(session=_summary(session), result=session.result)
