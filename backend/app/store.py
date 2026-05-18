from __future__ import annotations

import json
from pathlib import Path
from threading import Lock

from backend.app.models import AnalysisStatus, Course, ReportSession

BASE_DIR = Path(__file__).resolve().parents[2]
BUSINESS_DATA_PATH = BASE_DIR / "data" / "business.json"


class InMemorySessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, ReportSession] = {}
        self._courses: dict[str, Course] = {}
        self._lock = Lock()
        self._load()

    def add(self, session: ReportSession) -> ReportSession:
        with self._lock:
            self._sessions[session.id] = session
            self._save_locked()
        return session

    def get(self, session_id: str) -> ReportSession | None:
        with self._lock:
            return self._sessions.get(session_id)

    def list(self) -> list[ReportSession]:
        with self._lock:
            return sorted(
                self._sessions.values(),
                key=lambda item: item.created_at,
                reverse=True,
            )

    def list_by_course(self, course_id: str) -> list[ReportSession]:
        with self._lock:
            return sorted(
                [
                    session
                    for session in self._sessions.values()
                    if session.course_id == course_id
                ],
                key=lambda item: item.created_at,
                reverse=True,
            )

    def mark_processing(self, session_id: str) -> None:
        with self._lock:
            self._sessions[session_id].status = AnalysisStatus.processing
            self._sessions[session_id].error = None
            self._save_locked()

    def mark_completed(self, session_id: str, result: dict) -> None:
        with self._lock:
            self._sessions[session_id].status = AnalysisStatus.completed
            self._sessions[session_id].result = result
            self._sessions[session_id].error = None
            self._save_locked()

    def mark_failed(self, session_id: str, error: str) -> None:
        with self._lock:
            self._sessions[session_id].status = AnalysisStatus.failed
            self._sessions[session_id].error = error
            self._save_locked()

    def add_course(self, course: Course) -> Course:
        with self._lock:
            self._courses[course.id] = course
            self._save_locked()
        return course

    def get_course(self, course_id: str) -> Course | None:
        with self._lock:
            return self._courses.get(course_id)

    def list_courses(self) -> list[Course]:
        with self._lock:
            return sorted(
                self._courses.values(),
                key=lambda item: item.created_at,
                reverse=True,
            )

    def course_submission_count(self, course_id: str) -> int:
        with self._lock:
            return sum(
                1 for session in self._sessions.values() if session.course_id == course_id
            )

    def _load(self) -> None:
        if not BUSINESS_DATA_PATH.exists():
            return
        data = json.loads(BUSINESS_DATA_PATH.read_text(encoding="utf-8"))
        self._courses = {
            item["id"]: Course(**item) for item in data.get("courses", [])
        }
        self._sessions = {
            item["id"]: ReportSession(**item) for item in data.get("sessions", [])
        }

    def _save_locked(self) -> None:
        BUSINESS_DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "courses": [
                course.model_dump(mode="json") for course in self._courses.values()
            ],
            "sessions": [
                session.model_dump(mode="json")
                for session in self._sessions.values()
            ],
        }
        BUSINESS_DATA_PATH.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


store = InMemorySessionStore()
