from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from openai import OpenAI

from backend.app.models import SystemConfigIn
from backend.app.services.prompt_templates import build_report_analysis_prompt


def _client(config: SystemConfigIn) -> OpenAI:
    return OpenAI(
        api_key=config.dashscope_api_key,
        base_url=config.dashscope_base_url,
    )


def analyze_report_file(
    *,
    file_path: Path,
    student_name: str,
    course_name: str,
    assignment_name: str,
    assignment_requirements: str = "",
    config: SystemConfigIn,
) -> dict[str, Any]:
    client = _client(config)
    prompt = build_report_analysis_prompt(
        student_name=student_name,
        course_name=course_name,
        assignment_name=assignment_name,
        assignment_requirements=assignment_requirements,
    )

    with file_path.open("rb") as file_handle:
        file_object = client.files.create(file=file_handle, purpose="file-extract")

    completion = client.chat.completions.create(
        model=config.dashscope_text_model,
        messages=[
            {"role": "system", "content": f"fileid://{file_object.id}"},
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
    )

    content = completion.choices[0].message.content or "{}"
    print(
        "\n========== DashScope model raw response ==========\n"
        f"model: {completion.model}\n"
        f"uploaded_file_id: {file_object.id}\n"
        f"source_filename: {file_path.name}\n"
        "content:\n"
        f"{content}\n"
        "==================================================\n",
        flush=True,
    )
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        parsed = {
            "report_brief": {
                "topic": "模型返回了非 JSON 内容",
                "core_claims": [],
                "methods_or_evidence": [],
            },
            "question_plan": [],
            "voice_qa_prompt": content,
            "coverage_threshold": {
                "required_high_priority_completed": True,
                "max_follow_ups_per_question": 2,
                "done_rule": "需人工检查模型输出后再进入问答。",
            },
            "teacher_attention": ["模型输出格式异常，建议重新分析。"],
        }

    parsed["_meta"] = {
        "model": completion.model,
        "uploaded_file_id": file_object.id,
        "source_filename": file_path.name,
    }
    return parsed
