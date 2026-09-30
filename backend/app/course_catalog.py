"""Git-tracked course definitions, applied idempotently to each local database."""
from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select

CATALOG_DIR = Path(__file__).resolve().parents[2] / "data" / "courses"


def seed_courses() -> list[str]:
    from backend.app.database import CourseRow, SessionLocal, UserRow

    loaded = []
    with SessionLocal() as db:
        for path in sorted(CATALOG_DIR.glob("*.json")):
            catalog = json.loads(path.read_text(encoding="utf-8"))
            owner = db.scalar(select(UserRow).where(UserRow.username == catalog["owner_username"]))
            if owner is None:
                raise RuntimeError(f"课程种子负责人账号不存在：{catalog['owner_username']}")
            row = db.get(CourseRow, catalog["id"])
            if row is None:
                row = CourseRow(id=catalog["id"])
                db.add(row)
            # Only reserved, catalog-managed IDs are synchronized. Other courses are untouched.
            row.name = catalog["name"]
            row.teacher_name = catalog["teacher_name"]
            row.teacher_user_id = owner.id
            row.assignment_name = catalog["assignment_name"]
            row.assignment_requirements = catalog["assignment_requirements"]
            row.assignment_spec = catalog["assignment_spec"]
            loaded.append(row.id)
        db.commit()
    return loaded
