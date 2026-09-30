from __future__ import annotations

import asyncio
import copy
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import UploadFile
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app import database, main
import backend.app.store as store_module
from backend.app.course_catalog import seed_courses
from backend.app.models import SystemConfigIn
from backend.app.services.assessment import finalize_assessment, validate_analysis
from backend.app.services.dashscope_analyzer import _json_completion, analyze_report_file, source_chunks, summarize_voice_qa
from backend.app.services.prompt_templates import complete_question_plan
from backend.app.services.submission_files import SubmissionError, collect_submission, decode_source

ROOT = Path(__file__).resolve().parents[1]
CATALOG = json.loads((ROOT / "data/courses/compiler-2026.json").read_text(encoding="utf-8"))
SPEC = CATALOG["assignment_spec"]


def analysis_fixture(stage_id="lab1"):
    stages = [s for s in SPEC["stages"] if stage_id == "all" or s["id"] == stage_id]
    return dict(report_brief=dict(topic="测试", core_claims=[], methods_or_evidence=[]),
                stage_assessments=[dict(stage_id=s["id"], stage_name=s["name"], conclusion="有待答辩核实",
                    tasks=[dict(task_id=t["id"], status="partial", score=80, implementation_details="见源文件的实现",
                        evidence=["compiler.c:L1"], strengths=["实现框架"], weaknesses=["测试不足"], verification_questions=["如何测试？"])
                        for t in s["tasks"]]) for s in stages],
                question_plan=[dict(id=f"q_{s['id']}", stage_id=s["id"], category="implementation", required=True,
                    priority="high", focus="代码理解", question="解释自己的代码和测试？") for s in stages], teacher_attention=[])


def assessment_fixture(plan, record_id="r1"):
    return dict(summary="测试总结", strengths=["结构明确"], weaknesses=["测试不足"], improvements=["补充边界测试"],
                familiarity="基本熟悉", familiarity_rationale="能解释部分实现",
                assignment=dict(score=80, rationale="任务完成情况", evidence=["compiler.c:L1"]),
                oral_defense=dict(score=70, rationale="解释了实现", evidence=[record_id]),
                reflection=dict(score=90, rationale="反思具体", evidence=[record_id]),
                question_coverage=[dict(question_id=q["id"], answered=True, record_ids=[record_id]) for q in plan])


class UploadTests(unittest.TestCase):
    def collect(self, files):
        with tempfile.TemporaryDirectory() as root:
            return asyncio.run(collect_submission(files, Path(root) / "submission"))[1]

    def test_compiler_sources_and_gb18030(self):
        manifest = self.collect([UploadFile(filename=n, file=io.BytesIO("//中文\nint main(){}".encode("gb18030")))
                                 for n in ["compiler.c", "def.h", "lex.l", "parser.y", "parser.g4", "Makefile"]])
        self.assertEqual(len(manifest), 6)
        self.assertTrue(all(m["sha256"] for m in manifest))
        self.assertIn("中文", decode_source("中文".encode("gb18030"), "lex.l"))

    def test_zip_preserves_directories_and_reports_binary_artifacts(self):
        data = io.BytesIO()
        with zipfile.ZipFile(data, "w") as archive:
            archive.writestr("phase1/lex.l", "%%\n[a-z]+ return ID;\n%%")
            archive.writestr("phase2/parser.y", "expr: ID;")
            archive.writestr("report.md", "报告")
            archive.writestr("compiler.exe", b"MZ\0test")
        manifest = self.collect([UploadFile(filename="project.zip", file=io.BytesIO(data.getvalue()))])
        self.assertEqual(manifest[0]["name"], "project.zip/phase1/lex.l")
        self.assertEqual(manifest[-1]["kind"], "excluded")

    def test_zip_traversal_rejected(self):
        for name in ["../bad.c", "C:/bad.c", "/bad.c", "..\\bad.c"]:
            data = io.BytesIO()
            with zipfile.ZipFile(data, "w") as archive:
                archive.writestr(name, "bad")
            with self.assertRaises(SubmissionError):
                self.collect([UploadFile(filename="bad.zip", file=io.BytesIO(data.getvalue()))])

    def test_binary_disguised_as_code_and_empty_rejected(self):
        for data in [b"\0binary", b""]:
            with self.assertRaises(SubmissionError):
                self.collect([UploadFile(filename="main.c", file=io.BytesIO(data))])

    def test_duplicate_names_rejected(self):
        with self.assertRaises(SubmissionError):
            self.collect([UploadFile(filename="a.c", file=io.BytesIO(b"a")), UploadFile(filename="a.c", file=io.BytesIO(b"b"))])

    def test_long_source_tail_is_included(self):
        content = "long=" + "x" * 60_000 + "\nTAIL_REQUIREMENT_MARKER\n"
        chunks = source_chunks(content)
        self.assertGreater(len(chunks), 2)
        self.assertIn("TAIL_REQUIREMENT_MARKER", chunks[-1])
        self.assertEqual(sum(c.count("x") for c in chunks), 60_000)


class AssessmentTests(unittest.TestCase):
    def test_all_seven_stages_and_optional_score_exclusion(self):
        data = analysis_fixture("all")
        for s in data["stage_assessments"]:
            for t in s["tasks"]:
                if t["task_id"] in {"design1-extensions", "design3-optimization"}:
                    t.update(status="missing", score=0)
        result = validate_analysis(data, SPEC, "all")
        self.assertEqual(len(result["stage_assessments"]), 7)
        self.assertEqual(result["preliminary_assignment_score"], 80)

    def test_missing_stage_or_task_rejected(self):
        data = analysis_fixture("all")
        data["stage_assessments"].pop()
        with self.assertRaises(ValueError):
            validate_analysis(data, SPEC, "all")
        data = analysis_fixture()
        data["stage_assessments"][0]["tasks"].pop()
        with self.assertRaises(ValueError):
            validate_analysis(data, SPEC, "lab1")

    def test_reflection_questions_always_required(self):
        plan = complete_question_plan(validate_analysis(analysis_fixture(), SPEC, "lab1")["question_plan"])
        self.assertTrue({"learning", "ai_experience", "course_feeling", "course_suggestions"}.issubset({q["category"] for q in plan}))
        self.assertTrue(all(q["required"] for q in plan))

    def test_weighted_final_score_and_missing_answer_gate(self):
        plan = complete_question_plan(validate_analysis(analysis_fixture(), SPEC, "lab1")["question_plan"])
        data = assessment_fixture(plan)
        records = [dict(id=f"r{i}", question=q["question"], answer="回答") for i, q in enumerate(plan)]
        for i, coverage in enumerate(data["question_coverage"]):
            coverage["record_ids"] = [f"r{i}"]
        result = finalize_assessment(data, plan, records, "实验1")
        self.assertEqual(result["final_score"], 78)
        data["question_coverage"][-1]["record_ids"] = ["invented"]
        result = finalize_assessment(data, plan, records, "实验1")
        self.assertIsNone(result["final_score"])
        self.assertEqual(result["status"], "insufficient_qa")

    def test_one_record_cannot_cover_all_required_questions(self):
        plan = complete_question_plan(validate_analysis(analysis_fixture(), SPEC, "lab1")["question_plan"])
        result = finalize_assessment(assessment_fixture(plan), plan,
                                     [dict(id="r1", question="一个问题", answer="一个回答")], "实验1")
        self.assertIsNone(result["final_score"])

    def test_invalid_json_fails_instead_of_becoming_voice_prompt(self):
        create = lambda **kwargs: SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="not JSON"), finish_reason="stop")])
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        with self.assertRaises(RuntimeError):
            _json_completion(client, "test", [], lambda d: d)

    def test_whole_source_review_calls_and_chunk_evidence(self):
        responses = []
        messages = []
        def create(**kwargs):
            messages.append(kwargs["messages"])
            value = responses.pop(0)
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(value)), finish_reason="stop")])
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "compiler.c"
            content = "x" * 55_000 + "\nTAIL_MARKER"
            path.write_bytes(content.encode("utf-8"))
            responses.extend([dict(findings=[], dependencies=[], uncertainties=[])] * len(source_chunks(content)))
            responses.append(analysis_fixture())
            with patch("backend.app.services.dashscope_analyzer._client", return_value=client):
                result = analyze_report_file(file_path=path, student_name="验收", course_name="编译", assignment_name="实验",
                    config=SystemConfigIn(), assignment_spec=SPEC, stage_id="lab1")
            self.assertEqual(result["_meta"]["source_characters"], len(content))
            self.assertTrue(any("TAIL_MARKER" in m[-1]["content"] for m in messages[:-1]))
            self.assertEqual(result["file_coverage"][0]["chunks"], len(source_chunks(content)))

    def test_legacy_summary_recovers_original_material_and_preserves_questions(self):
        plan = [dict(id="old_q", question="原来的问题", required=True)]
        records = [dict(id="r1", question="原来的问题", answer="回答")]
        data = assessment_fixture(plan)
        captured = []
        def create(**kwargs):
            captured.append(kwargs["messages"][-1]["content"])
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(data)), finish_reason="stop")])
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        recovered = dict(file_reviews=[dict(evidence="FULL_ORIGINAL_DOCUMENT")], file_coverage=[], report_brief={})
        with patch("backend.app.services.dashscope_analyzer.analyze_report_file", return_value=recovered) as recovery, \
             patch("backend.app.services.dashscope_analyzer._client", return_value=client):
            result = summarize_voice_qa(file_path=Path("old.pdf"), student_name="验收", course_name="旧课程",
                    assignment_name="报告", report_analysis=dict(question_plan=plan), qa_records=records, config=SystemConfigIn())
        recovery.assert_called_once()
        self.assertIn("FULL_ORIGINAL_DOCUMENT", captured[0])
        self.assertEqual(result["question_coverage"][0]["question_id"], "old_q")


class DatabaseAPITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        database.Base.metadata.create_all(self.engine)
        factory = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.patches = [patch.object(database, "SessionLocal", factory), patch.object(store_module, "SessionLocal", factory),
                        patch.object(main, "init_database", lambda: None), patch.object(main, "UPLOAD_DIR", Path(self.temp.name)),
                        patch.object(main.config_store, "require_private", return_value=SystemConfigIn(dashscope_api_key="test-only")),
                        patch.object(main, "analyze_report_file", side_effect=lambda **kwargs: validate_analysis(analysis_fixture(kwargs['stage_id']), SPEC, kwargs['stage_id']))]
        for p in self.patches:
            p.start()
        database._seed_default_users()
        seed_courses()
        self.factory = factory
        self.client = TestClient(main.app)

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.engine.dispose()
        self.temp.cleanup()

    def test_catalog_reproducible_idempotent_and_visible_to_teacher(self):
        seed_courses()
        with self.factory() as db:
            rows = db.scalars(select(database.CourseRow)).all()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].teacher_name, "胡雯蔷")
        teacher = self.client.post("/api/auth/login", json=dict(username="teacher", password="teacher123")).json()
        result = self.client.get("/api/courses", params=dict(teacher_user_id=teacher["id"])).json()
        self.assertEqual(result[0]["name"], "编译技术实验")
        self.assertEqual(len(result[0]["assignment_spec"]["stages"]), 7)
        self.assertEqual(result[0]["assignment_spec"]["semantic_error_minimum"], 15)

    def test_multifile_api_preserves_stage_history_and_hides_local_paths(self):
        student = self.client.post("/api/auth/login", json=dict(username="student", password="student123")).json()
        for stage in ["lab1", "lab2", "lab1"]:
            response = self.client.post("/api/courses/COMP2026/sessions",
                data=dict(student_name="验收学生", student_user_id=student["id"], stage_id=stage),
                files=[("submission_files", ("lex.l", b"%%\n[a-z]+ return ID;\n%%", "text/plain")),
                       ("submission_files", ("main.c", b"int main(){}", "text/plain"))])
            self.assertEqual(response.status_code, 200, response.text)
            session = response.json()["session"]
            self.assertEqual(session["stage_id"], stage)
            self.assertNotIn("stored_path", session["submission_files"][0])
        history = self.client.get(f"/api/students/{student['id']}/courses").json()[0]
        self.assertEqual(len(history["submissions"]), 3)
        self.assertEqual(len(self.client.get("/api/courses/COMP2026").json()["submissions"]), 2)

    def test_bad_stage_and_no_files_rejected(self):
        result = self.client.post("/api/courses/COMP2026/sessions", data=dict(student_name="test", stage_id="bad"))
        self.assertEqual(result.status_code, 400)

    def test_summary_score_is_saved_and_returned(self):
        response = self.client.post("/api/courses/COMP2026/sessions", data=dict(student_name="验收", stage_id="lab1"),
                files={"report_file": ("legacy.c", b"int main(){}", "text/plain")})
        self.assertEqual(response.status_code, 200)
        sid = response.json()["session"]["id"]
        record = self.client.post(f"/api/sessions/{sid}/qa-records", json=dict(question="问题", answer="回答")).json()
        plan = self.client.get(f"/api/sessions/{sid}").json()["result"]["question_plan"]
        assessment = finalize_assessment(assessment_fixture(plan, record["id"]), plan, [record], "实验1")
        with patch.object(main, "summarize_voice_qa", return_value=assessment):
            result = self.client.post(f"/api/sessions/{sid}/voice-qa-summary")
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()["session"]["final_score"], 78)
        self.assertEqual(self.client.get(f"/api/sessions/{sid}").json()["result"]["final_assessment"]["final_score"], 78)
        result = self.client.post("/api/courses/COMP2026/sessions", data=dict(student_name="test", stage_id="lab1"))
        self.assertEqual(result.status_code, 400)


if __name__ == "__main__":
    unittest.main()
