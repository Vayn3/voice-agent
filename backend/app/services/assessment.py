from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field

class TaskReview(BaseModel):
    task_id: str
    status: Literal["met", "partial", "missing", "insufficient_evidence"]
    score: float = Field(ge=0, le=100)
    implementation_details: str = Field(min_length=1)
    evidence: list[str]
    strengths: list[str]
    weaknesses: list[str]
    verification_questions: list[str]

class StageReview(BaseModel):
    stage_id: str
    stage_name: str
    tasks: list[TaskReview]
    conclusion: str

class Question(BaseModel):
    id: str
    stage_id: str = ""
    category: str = "implementation"
    required: bool = True
    priority: Literal["high", "medium", "low"] = "high"
    focus: str
    question: str = Field(min_length=1)
    follow_up_when_insufficient: list[str] = Field(default_factory=list)
    sufficient_answer_criteria: list[str] = Field(default_factory=list)
    evidence_hint: str = "未明确"

class Analysis(BaseModel):
    report_brief: dict
    stage_assessments: list[StageReview] = Field(default_factory=list)
    question_plan: list[Question] = Field(min_length=1)
    teacher_attention: list[str] = Field(default_factory=list)

class ScoreComponent(BaseModel):
    score: float = Field(ge=0, le=100)
    rationale: str = Field(min_length=1)
    evidence: list[str] = Field(min_length=1)

class Coverage(BaseModel):
    question_id: str
    answered: bool
    record_ids: list[str]

class FinalAssessment(BaseModel):
    summary: str = Field(min_length=1)
    strengths: list[str]
    weaknesses: list[str]
    improvements: list[str]
    familiarity: Literal["熟悉", "基本熟悉", "部分熟悉", "证据不足"]
    familiarity_rationale: str
    assignment: ScoreComponent
    oral_defense: ScoreComponent
    reflection: ScoreComponent
    question_coverage: list[Coverage]

def selected_stages(spec: dict, stage_id: str) -> list[dict]:
    return [s for s in spec.get("stages", []) if stage_id == "all" or s["id"] == stage_id]

def validate_analysis(data: dict, spec: dict, stage_id: str) -> dict:
    result = Analysis.model_validate(data).model_dump()
    expected = {s["id"]: s for s in selected_stages(spec, stage_id)}
    actual = {s["stage_id"]: s for s in result["stage_assessments"]}
    if len(actual) != len(result["stage_assessments"]) or set(actual) != set(expected):
        raise ValueError("分析必须覆盖所选范围全部阶段，不得重复、遗漏或添加阶段。")
    required_scores = []
    for sid, template in expected.items():
        reviewed = actual[sid]
        tasks = {t["task_id"]: t for t in reviewed["tasks"]}
        if len(tasks) != len(reviewed["tasks"]) or set(tasks) != {t["id"] for t in template["tasks"]}:
            raise ValueError(f"阶段 {sid} 必须逐项覆盖全部必做与选做任务。")
        scores = []
        for criterion in template["tasks"]:
            review = tasks[criterion["id"]]
            review["title"] = criterion["title"]
            review["optional"] = criterion["optional"]
            if review["status"] in {"missing", "insufficient_evidence"}:
                review["score"] = 0
            if review["status"] in {"met", "partial"} and not review["evidence"]:
                raise ValueError("声称满足或部分满足的任务必须提供证据。")
            if not criterion["optional"]:
                scores.append(review["score"])
                required_scores.append(review["score"])
        reviewed["completion_score"] = round(sum(scores) / len(scores), 1) if scores else 0
        if not any(q["stage_id"] == sid and q["category"] == "implementation" and q["required"] for q in result["question_plan"]):
            raise ValueError(f"缺少阶段 {sid} 的必答实现细节问题。")
    ids = [q["id"] for q in result["question_plan"]]
    if len(ids) != len(set(ids)):
        raise ValueError("提问计划问题ID重复。")
    result["preliminary_assignment_score"] = round(sum(required_scores) / len(required_scores), 1) if required_scores else None
    result["scoring_scope"] = "全部实验与课设阶段" if stage_id == "all" else next((s["name"] for s in expected.values()), "当前作业")
    if not expected:
        result["scoring_scope"] = "当前课程作业"
    return result

def finalize_assessment(data: dict, question_plan: list[dict], records: list[dict], scope: str) -> dict:
    result = FinalAssessment.model_validate(data).model_dump()
    record_map = {r["id"]: r for r in records}
    coverage = {c["question_id"]: c for c in result["question_coverage"]}
    if len(coverage) != len(result["question_coverage"]) or set(coverage) - {q["id"] for q in question_plan}:
        raise ValueError("总结中的问答覆盖ID不合法。")
    missing = []
    used_records: set[str] = set()
    for question in question_plan:
        if not question.get("required", True):
            continue
        item = coverage.get(question["id"])
        if not item or not item["answered"] or not item["record_ids"] or any(
            rid not in record_map or not record_map[rid]["answer"].strip() or not record_map[rid]["question"].strip()
            for rid in item["record_ids"]
        ):
            missing.append(question["id"])
        elif not (set(item["record_ids"]) - used_records):
            # One answer cannot silently stand in for every separate required question.
            missing.append(question["id"])
        else:
            used_records.update(item["record_ids"])
    total = 0.0
    for component, weight in {"assignment": 60, "oral_defense": 30, "reflection": 10}.items():
        result[component]["weight"] = weight
        points = round(result[component]["score"] * weight / 100, 2)
        result[component]["weighted_points"] = points
        total += points
    result["final_score"] = round(total, 1) if not missing else None
    result["status"] = "final" if not missing else "insufficient_qa"
    result["missing_required_questions"] = missing
    result["scoring_scope"] = scope
    result["grading_note"] = "作业60% + 实现理解与答辩30% + 学习反思10%；系统补充建议，供教师复核。"
    return result
