from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Query, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from backend.app.database import init_database
from backend.app.models import (
    AnalysisResponse,
    ConfigCheckResponse,
    Course,
    CourseCreate,
    CourseDetail,
    CourseJoinRequest,
    CourseSummary,
    QARecord,
    QARecordCreate,
    ReportSession,
    SessionSummary,
    StudentCourse,
    SystemConfigIn,
    SystemConfigOut,
    UserLogin,
    UserOut,
    UserRegister,
    UserRoleUpdate,
    VoiceQASummaryResponse,
)
from backend.app.services.config_store import MissingConfigError, config_store
from backend.app.services.dashscope_analyzer import analyze_report_file, summarize_voice_qa
from backend.app.services.realtime_dialog import (
    DialogTranscript,
    RealtimeConfigError,
    RealtimeDialogClient,
    build_realtime_system_prompt,
)
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
        student_user_id=session.student_user_id,
        student_name=session.student_name,
        course_name=session.course_name,
        assignment_name=session.assignment_name,
        assignment_requirements=session.assignment_requirements,
        original_filename=session.original_filename,
        created_at=session.created_at,
        status=session.status,
        error=session.error,
        voice_qa_summary_ready=isinstance(session.result, dict) and bool(session.result.get("voice_qa_summary")),
    )


def _course_summary(course: Course) -> CourseSummary:
    stats = store.course_stats(course.id)
    return CourseSummary(
        id=course.id,
        name=course.name,
        teacher_name=course.teacher_name,
        teacher_user_id=course.teacher_user_id,
        assignment_name=course.assignment_name,
        assignment_requirements=course.assignment_requirements,
        created_at=course.created_at,
        submission_count=stats["submission_count"],
        student_count=stats["student_count"],
        analyzed_count=stats["analyzed_count"],
        summarized_count=stats["summarized_count"],
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


@app.on_event("startup")
def startup() -> None:
    init_database()


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/auth/login", response_model=UserOut)
def login(payload: UserLogin) -> UserOut:
    user = store.authenticate_user(payload.username, payload.password)
    if user is None:
        raise HTTPException(status_code=401, detail="用户名或密码错误。")
    return user


@app.post("/api/auth/register", response_model=UserOut)
def register(payload: UserRegister) -> UserOut:
    if len(payload.username.strip()) < 3:
        raise HTTPException(status_code=400, detail="用户名至少需要 3 个字符")
    if len(payload.password) < 6:
        raise HTTPException(status_code=400, detail="密码至少需要 6 个字符")
    user = store.create_user(payload.username, payload.password, payload.display_name)
    if user is None:
        raise HTTPException(status_code=409, detail="用户名已存在")
    return user


@app.get("/api/users", response_model=list[UserOut])
def list_users() -> list[UserOut]:
    return store.list_users()


@app.put("/api/users/{user_id}/role", response_model=UserOut)
def update_user_role(user_id: str, payload: UserRoleUpdate) -> UserOut:
    user = store.update_user_role(user_id, payload.role)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    return user


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
            teacher_user_id=payload.teacher_user_id,
            assignment_name=payload.assignment_name.strip(),
            assignment_requirements=payload.assignment_requirements.strip(),
        )
    )
    return _course_summary(course)


@app.get("/api/courses", response_model=list[CourseSummary])
def list_courses(teacher_user_id: str | None = Query(default=None)) -> list[CourseSummary]:
    courses = store.list_courses_by_teacher(teacher_user_id) if teacher_user_id else store.list_courses()
    return [_course_summary(course) for course in courses]


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
    student_user_id: str | None = Form(None),
    report_file: UploadFile = File(...),
) -> AnalysisResponse:
    course = store.get_course(course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="课程不存在。")

    if student_user_id:
        store.enroll_course(course.id, student_user_id, student_name)

    return await _create_report_session(
        background_tasks=background_tasks,
        student_name=student_name,
        course_name=course.name,
        assignment_name=course.assignment_name,
        assignment_requirements=course.assignment_requirements,
        report_file=report_file,
        course_id=course.id,
        student_user_id=student_user_id,
    )


@app.post("/api/sessions", response_model=AnalysisResponse)
async def create_session(
    background_tasks: BackgroundTasks,
    student_name: str = Form(...),
    course_name: str = Form(...),
    assignment_name: str = Form(...),
    assignment_requirements: str = Form(""),
    student_user_id: str | None = Form(None),
    report_file: UploadFile = File(...),
) -> AnalysisResponse:
    return await _create_report_session(
        background_tasks=background_tasks,
        student_name=student_name,
        course_name=course_name,
        assignment_name=assignment_name,
        assignment_requirements=assignment_requirements,
        report_file=report_file,
        student_user_id=student_user_id,
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
    student_user_id: str | None = None,
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
        student_user_id=student_user_id,
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
    session = store.replace_for_student_course(temp_session) if course_id else store.add(temp_session)
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


@app.get("/api/sessions/{session_id}/qa-records", response_model=list[QARecord])
def list_qa_records(session_id: str) -> list[QARecord]:
    if store.get(session_id) is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return store.list_qa_records(session_id)


@app.post("/api/sessions/{session_id}/qa-records", response_model=QARecord)
def create_qa_record(session_id: str, payload: QARecordCreate) -> QARecord:
    if store.get(session_id) is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    if not payload.question.strip() or not payload.answer.strip():
        raise HTTPException(status_code=400, detail="问题和回答不能为空。")
    return store.add_qa_record(
        report_id=session_id,
        question=payload.question,
        answer=payload.answer,
        user_id=payload.created_by_user_id,
    )


@app.post("/api/courses/{course_id}/enroll", response_model=CourseSummary)
def enroll_course(course_id: str, payload: CourseJoinRequest) -> CourseSummary:
    if not payload.student_user_id.strip():
        raise HTTPException(status_code=400, detail="缺少学生用户 ID")
    course = store.enroll_course(
        course_id=course_id.strip(),
        student_user_id=payload.student_user_id.strip(),
        student_name=payload.student_name.strip(),
    )
    if course is None:
        raise HTTPException(status_code=404, detail="课程码不存在")
    return _course_summary(course)


@app.get("/api/students/{student_user_id}/courses", response_model=list[StudentCourse])
def list_student_courses(student_user_id: str) -> list[StudentCourse]:
    courses = store.list_enrolled_courses(student_user_id)
    return [
        StudentCourse(
            course=_course_summary(course),
            latest_submission=(
                _summary(session)
                if (session := store.latest_for_student_course(student_user_id, course.id)) is not None
                else None
            ),
        )
        for course in courses
    ]


@app.websocket("/api/sessions/{session_id}/voice-qa")
async def voice_qa_websocket(websocket: WebSocket, session_id: str) -> None:
    await websocket.accept()
    session = store.get(session_id)
    if session is None:
        await websocket.send_json({"type": "error", "message": "会话不存在"})
        await websocket.close()
        return
    if session.status != "completed" or not session.result:
        await websocket.send_json({"type": "error", "message": "请先等待报告分析完成"})
        await websocket.close()
        return

    result = session.result
    config = config_store.read_private()
    system_prompt = build_realtime_system_prompt(
        str(result.get("voice_qa_prompt") or ""),
        result.get("question_plan") or [],
    )
    transcript = DialogTranscript()
    client = RealtimeDialogClient(system_prompt=system_prompt, config=config)
    stop_event = asyncio.Event()

    try:
        await client.connect()
        await websocket.send_json(
            {
                "type": "ready",
                "sample_rate": 24000,
                "sample_format": "float32",
                "message": "实时语音问答已连接",
            }
        )
        await client.chat_text_query("请按照系统提示词开始本次课程报告语音问答，只说一句简短开场，然后提出第一个问题。")

        async def browser_to_dialog() -> None:
            while not stop_event.is_set():
                message = await websocket.receive()
                if stop_event.is_set():
                    break
                if message.get("bytes") is not None:
                    await client.send_audio(message["bytes"])
                elif message.get("text"):
                    payload = json.loads(message["text"])
                    if payload.get("type") == "finish":
                        stop_event.set()
                        break

        async def dialog_to_browser() -> None:
            while not stop_event.is_set():
                response = await client.receive()
                message_type = response.get("message_type")
                payload_msg = response.get("payload_msg")
                if message_type == "SERVER_ACK" and isinstance(payload_msg, bytes):
                    await websocket.send_bytes(payload_msg)
                    continue
                if message_type == "SERVER_ERROR":
                    await websocket.send_json({"type": "error", "message": str(response)})
                    stop_event.set()
                    break
                if message_type != "SERVER_FULL_RESPONSE":
                    continue

                event = response.get("event")
                transcript.absorb_text(event, payload_msg)
                final_text = transcript.finalize_event(event)
                if final_text:
                    await websocket.send_json(final_text)
                    if final_text.get("ended"):
                        stop_event.set()
                        try:
                            await client.finish_session()
                        except Exception:
                            pass
                        break

        tasks = [
            asyncio.create_task(browser_to_dialog()),
            asyncio.create_task(dialog_to_browser()),
        ]
        await stop_event.wait()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

        records = transcript.records()
        for record in records:
            if record["question"].strip() and record["answer"].strip():
                store.add_qa_record(
                    report_id=session_id,
                    question=record["question"],
                    answer=record["answer"],
                    user_id=session.student_user_id,
                )
        await websocket.send_json({"type": "done", "records": records})
    except RealtimeConfigError as exc:
        await websocket.send_json({"type": "error", "message": str(exc)})
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        await websocket.send_json({"type": "error", "message": str(exc)})
    finally:
        try:
            await client.finish_session()
            await client.finish_connection()
        except Exception:
            pass
        await client.close()
        try:
            await websocket.close()
        except Exception:
            pass


@app.post("/api/sessions/{session_id}/voice-qa-summary", response_model=VoiceQASummaryResponse)
def create_voice_qa_summary(session_id: str) -> VoiceQASummaryResponse:
    session = store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    if session.status != "completed" or not session.result:
        raise HTTPException(status_code=409, detail="请先等待报告分析完成")

    qa_records = store.list_qa_records(session_id)
    if not qa_records:
        raise HTTPException(status_code=409, detail="还没有可总结的问答记录")

    try:
        config = config_store.require_private()
    except MissingConfigError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    summary = summarize_voice_qa(
        file_path=session.stored_path,
        student_name=session.student_name,
        course_name=session.course_name,
        assignment_name=session.assignment_name,
        assignment_requirements=session.assignment_requirements,
        report_analysis=session.result,
        qa_records=[record.model_dump(mode="json") for record in qa_records],
        config=config,
    )
    next_result = dict(session.result or {})
    next_result["voice_qa_summary"] = summary
    updated = store.update_result(session_id, next_result) or session
    return VoiceQASummaryResponse(
        session=_summary(updated),
        qa_records=qa_records,
        summary=summary,
    )
