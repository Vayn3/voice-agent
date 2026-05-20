from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from sqlalchemy import delete, select

from backend.app.database import (
    CourseEnrollmentRow,
    CourseRow,
    QARecordRow,
    ReportRow,
    SessionLocal,
    UserRow,
    count_reports_for_course,
    hash_password,
)
from backend.app.models import AnalysisStatus, Course, QARecord, ReportSession, UserOut, UserRole


class MySQLStore:
    def replace_for_student_course(self, session: ReportSession) -> ReportSession:
        with SessionLocal() as db:
            existing_query = select(ReportRow.id).where(ReportRow.course_id == session.course_id)
            if session.student_user_id:
                existing_query = existing_query.where(ReportRow.student_user_id == session.student_user_id)
            else:
                existing_query = existing_query.where(ReportRow.student_name == session.student_name)
            existing_ids = list(db.scalars(existing_query).all())
            if existing_ids:
                db.execute(delete(QARecordRow).where(QARecordRow.report_id.in_(existing_ids)))
                db.execute(delete(ReportRow).where(ReportRow.id.in_(existing_ids)))
                db.commit()
        return self.add(session)

    def add(self, session: ReportSession) -> ReportSession:
        with SessionLocal() as db:
            db.add(
                ReportRow(
                    id=session.id,
                    course_id=session.course_id,
                    student_user_id=session.student_user_id,
                    student_name=session.student_name,
                    course_name=session.course_name,
                    assignment_name=session.assignment_name,
                    assignment_requirements=session.assignment_requirements,
                    original_filename=session.original_filename,
                    stored_path=str(session.stored_path),
                    created_at=session.created_at,
                    status=session.status,
                    result=session.result,
                    error=session.error,
                )
            )
            db.commit()
        return session

    def get(self, session_id: str) -> ReportSession | None:
        with SessionLocal() as db:
            row = db.get(ReportRow, session_id)
            return _report_from_row(row) if row else None

    def list(self) -> list[ReportSession]:
        with SessionLocal() as db:
            rows = db.scalars(select(ReportRow).order_by(ReportRow.created_at.desc())).all()
            return [_report_from_row(row) for row in rows]

    def list_by_course(self, course_id: str) -> list[ReportSession]:
        with SessionLocal() as db:
            rows = db.scalars(
                select(ReportRow)
                .where(ReportRow.course_id == course_id)
                .order_by(ReportRow.created_at.desc())
            ).all()
            return [_report_from_row(row) for row in _latest_rows_by_student(rows)]

    def latest_for_student_course(self, student_user_id: str, course_id: str) -> ReportSession | None:
        with SessionLocal() as db:
            row = db.scalar(
                select(ReportRow)
                .where(ReportRow.course_id == course_id)
                .where(ReportRow.student_user_id == student_user_id)
                .order_by(ReportRow.created_at.desc())
                .limit(1)
            )
            return _report_from_row(row) if row else None

    def mark_processing(self, session_id: str) -> None:
        self._update_status(session_id, AnalysisStatus.processing, error=None)

    def mark_completed(self, session_id: str, result: dict) -> None:
        self._update_status(session_id, AnalysisStatus.completed, result=result, error=None)

    def mark_failed(self, session_id: str, error: str) -> None:
        self._update_status(session_id, AnalysisStatus.failed, error=error)

    def update_result(self, session_id: str, result: dict) -> ReportSession | None:
        with SessionLocal() as db:
            row = db.get(ReportRow, session_id)
            if row is None:
                return None
            row.result = result
            db.commit()
            db.refresh(row)
            return _report_from_row(row)

    def add_course(self, course: Course) -> Course:
        with SessionLocal() as db:
            db.add(
                CourseRow(
                    id=course.id,
                    name=course.name,
                    teacher_name=course.teacher_name,
                    teacher_user_id=course.teacher_user_id,
                    assignment_name=course.assignment_name,
                    assignment_requirements=course.assignment_requirements,
                    created_at=course.created_at,
                )
            )
            db.commit()
        return course

    def get_course(self, course_id: str) -> Course | None:
        with SessionLocal() as db:
            row = db.get(CourseRow, course_id)
            return _course_from_row(row) if row else None

    def list_courses(self) -> list[Course]:
        with SessionLocal() as db:
            rows = db.scalars(select(CourseRow).order_by(CourseRow.created_at.desc())).all()
            return [_course_from_row(row) for row in rows]

    def list_courses_by_teacher(self, teacher_user_id: str) -> list[Course]:
        with SessionLocal() as db:
            rows = db.scalars(
                select(CourseRow)
                .where(CourseRow.teacher_user_id == teacher_user_id)
                .order_by(CourseRow.created_at.desc())
            ).all()
            return [_course_from_row(row) for row in rows]

    def course_submission_count(self, course_id: str) -> int:
        with SessionLocal() as db:
            return count_reports_for_course(db, course_id)

    def course_stats(self, course_id: str) -> dict[str, int]:
        with SessionLocal() as db:
            report_rows = db.scalars(
                select(ReportRow)
                .where(ReportRow.course_id == course_id)
                .order_by(ReportRow.created_at.desc())
            ).all()
            rows = _latest_rows_by_student(report_rows)
            student_keys = {
                row.student_user_id or row.student_name.strip()
                for row in rows
                if row.student_user_id or row.student_name.strip()
            }
            return {
                "submission_count": len(rows),
                "student_count": max(len(student_keys), self.course_enrollment_count(course_id)),
                "analyzed_count": sum(1 for row in rows if row.status == AnalysisStatus.completed),
                "summarized_count": sum(
                    1
                    for row in rows
                    if isinstance(row.result, dict) and bool(row.result.get("voice_qa_summary"))
                ),
            }

    def course_enrollment_count(self, course_id: str) -> int:
        with SessionLocal() as db:
            return len(
                db.scalars(
                    select(CourseEnrollmentRow.student_user_id).where(CourseEnrollmentRow.course_id == course_id)
                ).all()
            )

    def enroll_course(self, course_id: str, student_user_id: str, student_name: str) -> Course | None:
        with SessionLocal() as db:
            course = db.get(CourseRow, course_id)
            if course is None:
                return None
            exists = db.scalar(
                select(CourseEnrollmentRow)
                .where(CourseEnrollmentRow.course_id == course_id)
                .where(CourseEnrollmentRow.student_user_id == student_user_id)
            )
            if exists is None:
                db.add(
                    CourseEnrollmentRow(
                        id=uuid4().hex,
                        course_id=course_id,
                        student_user_id=student_user_id,
                        student_name=student_name,
                    )
                )
                db.commit()
            return _course_from_row(course)

    def list_enrolled_courses(self, student_user_id: str) -> list[Course]:
        with SessionLocal() as db:
            rows = db.scalars(
                select(CourseRow)
                .join(CourseEnrollmentRow, CourseEnrollmentRow.course_id == CourseRow.id)
                .where(CourseEnrollmentRow.student_user_id == student_user_id)
                .order_by(CourseEnrollmentRow.created_at.desc())
            ).all()
            return [_course_from_row(row) for row in rows]

    def authenticate_user(self, username: str, password: str) -> UserOut | None:
        with SessionLocal() as db:
            row = db.scalar(select(UserRow).where(UserRow.username == username.strip()))
            if row is None or row.password_hash != hash_password(password):
                return None
            return _user_from_row(row)

    def create_user(self, username: str, password: str, display_name: str = "") -> UserOut | None:
        normalized_username = username.strip()
        if not normalized_username or not password:
            return None
        with SessionLocal() as db:
            exists = db.scalar(select(UserRow).where(UserRow.username == normalized_username))
            if exists is not None:
                return None
            row = UserRow(
                id=uuid4().hex,
                username=normalized_username,
                password_hash=hash_password(password),
                display_name=display_name.strip() or normalized_username,
                role=UserRole.student,
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            return _user_from_row(row)

    def list_users(self) -> list[UserOut]:
        with SessionLocal() as db:
            rows = db.scalars(select(UserRow).order_by(UserRow.created_at.desc())).all()
            return [_user_from_row(row) for row in rows]

    def update_user_role(self, user_id: str, role: UserRole) -> UserOut | None:
        with SessionLocal() as db:
            row = db.get(UserRow, user_id)
            if row is None:
                return None
            row.role = role
            db.commit()
            db.refresh(row)
            return _user_from_row(row)

    def add_qa_record(self, report_id: str, question: str, answer: str, user_id: str | None) -> QARecord:
        record = QARecord(
            id=uuid4().hex,
            report_id=report_id,
            question=question.strip(),
            answer=answer.strip(),
            created_by_user_id=user_id,
        )
        with SessionLocal() as db:
            db.add(
                QARecordRow(
                    id=record.id,
                    report_id=record.report_id,
                    question=record.question,
                    answer=record.answer,
                    created_by_user_id=record.created_by_user_id,
                    created_at=record.created_at,
                )
            )
            db.commit()
        return record

    def list_qa_records(self, report_id: str) -> list[QARecord]:
        with SessionLocal() as db:
            rows = db.scalars(
                select(QARecordRow)
                .where(QARecordRow.report_id == report_id)
                .order_by(QARecordRow.created_at.asc())
            ).all()
            return [
                QARecord(
                    id=row.id,
                    report_id=row.report_id,
                    question=row.question,
                    answer=row.answer,
                    created_by_user_id=row.created_by_user_id,
                    created_at=row.created_at,
                )
                for row in rows
            ]

    def _update_status(
        self,
        session_id: str,
        status: AnalysisStatus,
        *,
        result: dict | None = None,
        error: str | None = None,
    ) -> None:
        with SessionLocal() as db:
            row = db.get(ReportRow, session_id)
            if row is None:
                return
            row.status = status
            row.error = error
            if result is not None:
                row.result = result
            db.commit()


def _report_from_row(row: ReportRow) -> ReportSession:
    return ReportSession(
        id=row.id,
        course_id=row.course_id,
        student_user_id=row.student_user_id,
        student_name=row.student_name,
        course_name=row.course_name,
        assignment_name=row.assignment_name,
        assignment_requirements=row.assignment_requirements,
        original_filename=row.original_filename,
        stored_path=Path(row.stored_path),
        created_at=row.created_at,
        status=row.status,
        result=row.result,
        error=row.error,
    )


def _latest_rows_by_student(rows: list[ReportRow]) -> list[ReportRow]:
    latest: dict[str, ReportRow] = {}
    for row in rows:
        key = row.student_user_id or row.student_name.strip() or row.id
        if key not in latest:
            latest[key] = row
    return list(latest.values())


def _course_from_row(row: CourseRow) -> Course:
    return Course(
        id=row.id,
        name=row.name,
        teacher_name=row.teacher_name,
        teacher_user_id=row.teacher_user_id,
        assignment_name=row.assignment_name,
        assignment_requirements=row.assignment_requirements,
        created_at=row.created_at,
    )


def _user_from_row(row: UserRow) -> UserOut:
    return UserOut(
        id=row.id,
        username=row.username,
        display_name=row.display_name,
        role=row.role,
    )


store = MySQLStore()
