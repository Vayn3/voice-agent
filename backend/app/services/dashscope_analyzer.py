from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable

from openai import OpenAI
from pydantic import BaseModel, Field

from backend.app.models import SystemConfigIn
from backend.app.services.assessment import finalize_assessment, validate_analysis
from backend.app.services.prompt_templates import (
    TRUST_BOUNDARY, build_report_analysis_prompt, build_review_prompt,
    build_voice_prompt, build_voice_qa_summary_prompt, complete_question_plan,
)
from backend.app.services.submission_files import (
    DOCUMENT_EXTENSIONS, MAX_TEXT_CHARS, SubmissionError, decode_source, public_files, read_legacy_doc,
)

logger = logging.getLogger(__name__)
CHUNK_CHARS = 24_000
MAX_REVIEW_CHARS = 180_000


class FileReview(BaseModel):
    findings: list[dict[str, Any]]
    dependencies: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)


def _client(config: SystemConfigIn) -> OpenAI:
    return OpenAI(api_key=config.dashscope_api_key, base_url=config.dashscope_base_url, timeout=180, max_retries=2)


def _json_completion(client: OpenAI, model: str, messages: list[dict],
                     validator: Callable[[dict], dict], max_tokens: int = 12_000) -> dict:
    conversation = list(messages)
    for attempt in range(2):
        response = client.chat.completions.create(model=model, messages=conversation, max_tokens=max_tokens)
        choice = response.choices[0]
        content = choice.message.content or ""
        try:
            if choice.finish_reason == "length":
                raise ValueError("模型输出超长被截断，请按阶段拆分提交。")
            stripped = content.strip()
            if stripped.startswith("```"):
                stripped = stripped.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            data = json.loads(stripped)
            if not isinstance(data, dict):
                raise ValueError("模型输出不是JSON对象。")
            return validator(data)
        except (ValueError, TypeError, KeyError) as exc:
            if attempt:
                raise RuntimeError(f"模型分析格式/覆盖校验失败：{exc}") from exc
            conversation.extend([
                {"role": "assistant", "content": content},
                {"role": "user", "content": f"输出校验失败：{exc}。重新输出完整JSON，保持教师任务ID并覆盖全部所选阶段和任务，不省略字段。"},
            ])
    raise RuntimeError("未获取有效模型分析。")


def source_chunks(content: str) -> list[str]:
    """Every character is included; line labels survive boundaries, including very long lines."""
    chunks: list[str] = []
    current = ""
    for number, line in enumerate(content.splitlines(keepends=True), 1):
        # Long generated/source lines are subdivided, not discarded.
        for start in range(0, len(line), CHUNK_CHARS - 80):
            label = f"L{number}" + (f"[字符{start + 1}起]" if start else "")
            piece = f"{label}: {line[start:start + CHUNK_CHARS - 80]}"
            if len(current) + len(piece) > CHUNK_CHARS:
                chunks.append(current)
                current = ""
            current += piece if piece.endswith(("\n", "\r")) else piece + "\n"
    if current:
        chunks.append(current)
    return chunks


def _manifest(file_path: Path, submission_files: list[dict] | None) -> list[dict]:
    if submission_files:
        return submission_files
    return [dict(name=file_path.name, stored_path=str(file_path), kind="document", size=file_path.stat().st_size)]


def analyze_report_file(*, file_path: Path, student_name: str, course_name: str, assignment_name: str,
                        assignment_requirements: str = "", config: SystemConfigIn,
                        submission_files: list[dict] | None = None, assignment_spec: dict | None = None,
                        stage_id: str = "all") -> dict[str, Any]:
    client = _client(config)
    spec = assignment_spec or {}
    manifest = _manifest(file_path, submission_files)
    reviews: list[dict] = []
    coverage: list[dict] = []
    text_chars = 0
    review_prompt = build_review_prompt(spec, stage_id, assignment_requirements)
    for item in manifest:
        if item["kind"] == "excluded":
            coverage.append(dict(name=item["name"], status="excluded", reason=item["reason"]))
            continue
        path = Path(item["stored_path"])
        suffix = path.suffix.lower()
        document_id = None
        try:
            if suffix in DOCUMENT_EXTENSIONS - {".doc"}:
                with path.open("rb") as handle:
                    document_id = client.files.create(file=handle, purpose="file-extract").id
                blocks = [None]
            else:
                content = read_legacy_doc(path) if suffix == ".doc" else decode_source(path.read_bytes(), item["name"])
                if not content.strip():
                    raise SubmissionError(f"{item['name']} 未提取到可读内容。")
                text_chars += len(content)
                if text_chars > MAX_TEXT_CHARS:
                    raise SubmissionError("可读内容超过120万字符，请按阶段拆分，不能静默截断。")
                blocks = source_chunks(content)
            for index, block in enumerate(blocks):
                messages = [{"role": "system", "content": TRUST_BOUNDARY}]
                if document_id:
                    messages.append({"role": "system", "content": f"fileid://{document_id}"})
                messages.append({"role": "user", "content": review_prompt +
                    f"\n文件：{item['name']}；块 {index + 1}/{len(blocks)}\n待评材料：\n" + (block or "读取所附完整文件。")})
                model = config.dashscope_text_model if document_id else config.dashscope_code_model
                reviewed = _json_completion(client, model, messages,
                                           lambda d: FileReview.model_validate(d).model_dump(), max_tokens=6000)
                reviews.append(dict(file=item["name"], chunk=index + 1, **reviewed))
                if len(json.dumps(reviews, ensure_ascii=False)) > MAX_REVIEW_CHARS:
                    raise SubmissionError("联合审查记录过长，请按阶段拆分提交；系统不会省略已分析材料。")
            coverage.append(dict(name=item["name"], status="reviewed", chunks=len(blocks),
                                 sha256=item.get("sha256"), mode="document_extract" if document_id else "full_text"))
        finally:
            if document_id:
                try:
                    client.files.delete(document_id)
                except Exception:
                    logger.warning("Failed to delete remote analysis file %s", document_id)

    prompt = build_report_analysis_prompt(student_name=student_name, course_name=course_name,
                assignment_name=assignment_name, assignment_requirements=assignment_requirements,
                assignment_spec=spec, stage_id=stage_id)
    analysis = _json_completion(client, config.dashscope_code_model, [
        {"role": "system", "content": TRUST_BOUNDARY},
        {"role": "user", "content": prompt + "\n完整文件清单：" + json.dumps(public_files(manifest), ensure_ascii=False) +
         "\n全部文件审查记录：" + json.dumps(reviews, ensure_ascii=False)},
    ], lambda d: validate_analysis(d, spec, stage_id), max_tokens=16_000)
    analysis["question_plan"] = complete_question_plan(analysis["question_plan"], course_name)
    analysis["voice_qa_prompt"] = build_voice_prompt(analysis, course_name)
    analysis["coverage_threshold"] = dict(required_high_priority_completed=True, max_follow_ups_per_question=2,
            done_rule="全部required问题（包括每阶段实现、学习收获、AI体验、课程感受、课程建议）已问并收到回答后结束。")
    analysis["file_coverage"] = coverage
    analysis["file_reviews"] = reviews
    analysis["_meta"] = dict(model=config.dashscope_code_model, document_model=config.dashscope_text_model,
                             stage_id=stage_id, reviewed_files=sum(c["status"] == "reviewed" for c in coverage),
                             review_chunks=len(reviews), source_characters=text_chars,
                             analysis_mode="全部可读内容静态审查，未执行学生程序；文档解析质量需结合证据核实")
    return analysis


def summarize_voice_qa(*, file_path: Path, student_name: str, course_name: str, assignment_name: str,
                       assignment_requirements: str = "", report_analysis: dict[str, Any] | None,
                       qa_records: list[dict], config: SystemConfigIn) -> dict[str, Any]:
    analysis = {k: v for k, v in (report_analysis or {}).items() if k not in
                {"voice_qa_summary", "final_assessment", "voice_qa_prompt"}}
    if not analysis.get("file_reviews"):
        # Older sessions only stored a brief and questions. Recover the original material
        # while retaining the plan that was actually used in their oral defense.
        recovered = analyze_report_file(file_path=file_path, student_name=student_name,
                    course_name=course_name, assignment_name=assignment_name,
                    assignment_requirements=assignment_requirements, config=config)
        analysis["file_reviews"] = recovered["file_reviews"]
        analysis["file_coverage"] = recovered["file_coverage"]
        analysis["report_brief"] = recovered["report_brief"]
    # Complete file reviews are reused rather than resending only the first upload.
    prompt = build_voice_qa_summary_prompt(student_name=student_name, course_name=course_name,
            assignment_name=assignment_name, assignment_requirements=assignment_requirements,
            report_analysis=json.dumps(analysis, ensure_ascii=False),
            qa_records=json.dumps(qa_records, ensure_ascii=False))
    return _json_completion(_client(config), config.dashscope_code_model, [
        {"role": "system", "content": TRUST_BOUNDARY}, {"role": "user", "content": prompt},
    ], lambda d: finalize_assessment(d, analysis.get("question_plan", []), qa_records,
                                    analysis.get("scoring_scope", "当前作业")))
