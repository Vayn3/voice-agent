from __future__ import annotations


def build_report_analysis_prompt(
    *,
    student_name: str,
    course_name: str,
    assignment_name: str,
    assignment_requirements: str = "",
) -> str:
    return f"""
你是“课程报告智能助教”的文档分析模块。请阅读系统消息中 fileid 对应的学生课程报告，
为后续实时语音问答阶段生成一份结构化提问计划。

基础信息：
- 学生：{student_name}
- 课程：{course_name}
- 作业项：{assignment_name}
- 作业要求：{assignment_requirements or "未提供"}

任务要求：
1. 先概括报告主题、核心结论、方法或实现路径。
2. 抽取报告中最值得追问的关键点，优先关注：论证薄弱处、数据或实验来源、方法选择理由、
   结果解释、与课程目标和作业要求的对应关系、可能存在的风险或不确定点。
3. 为语音问答生成可直接作为会话 system prompt 使用的中文提示词，要求 Agent 能按优先级逐题提问，
   在回答不足时自然追问，在信息充分时进入下一题。
4. 输出必须是严格 JSON，不要使用 Markdown 代码块，不要附加解释文字。

JSON 结构如下：
{{
  "report_brief": {{
    "topic": "一句话说明报告主题",
    "core_claims": ["核心结论1", "核心结论2"],
    "methods_or_evidence": ["报告使用的方法、材料或证据"]
  }},
  "question_plan": [
    {{
      "id": "q1",
      "priority": "high | medium | low",
      "focus": "追问焦点",
      "question": "语音阶段应先问学生的自然语言问题",
      "follow_up_when_insufficient": ["回答不足时的追问1", "追问2"],
      "sufficient_answer_criteria": ["什么样的信息算答全"],
      "evidence_hint": "报告中相关章节、段落或原文线索；找不到则写未明确"
    }}
  ],
  "voice_qa_prompt": "一段可直接注入实时语音模型的 system prompt，包含角色、提问顺序、追问策略、结束条件和禁问边界。",
  "coverage_threshold": {{
    "required_high_priority_completed": true,
    "max_follow_ups_per_question": 2,
    "done_rule": "何时结束问答"
  }},
  "teacher_attention": ["需要教师重点关注的风险或不确定点"]
}}
""".strip()


def build_voice_qa_summary_prompt(
    *,
    student_name: str,
    course_name: str,
    assignment_name: str,
    assignment_requirements: str = "",
    report_analysis: str,
    qa_records: str,
) -> str:
    return f"""
你是“课程报告智能助教”的问答总结模块。请阅读系统消息中的报告文件，并结合下面已有的报告分析结果和实时语音问答记录，生成一份面向教师的中文总结报告。

基础信息：
- 学生：{student_name}
- 课程：{course_name}
- 作业项：{assignment_name}
- 作业要求：{assignment_requirements or "未提供"}

已有报告分析结果：
{report_analysis}

实时语音问答记录：
{qa_records}

输出要求：
1. 只输出总结正文，不要输出 JSON，不要使用 Markdown 代码块。
2. 内容包含：报告核心内容概括、学生问答表现、已经回答清楚的点、仍然薄弱或需追问的点、教师评分/反馈建议。
3. 语言客观、具体、可直接展示在系统界面中。
4. 如果问答记录不足，请明确指出“不足以判断”的部分，不要编造学生回答。
""".strip()
