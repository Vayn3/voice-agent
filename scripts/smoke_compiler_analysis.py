"""Explicit live API acceptance using synthetic materials, never a real student's grade."""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.services.config_store import config_store
from backend.app.services.dashscope_analyzer import analyze_report_file, summarize_voice_qa


def run_live():
    catalog = json.loads((ROOT / "data/courses/compiler-2026.json").read_text(encoding="utf-8"))
    config = config_store.require_private()
    with tempfile.TemporaryDirectory(prefix="compiler-acceptance-") as temporary:
        temp = Path(temporary)
        (temp / "lex.l").write_bytes(b'''%option noyywrap
%{
#include <stdio.h>
%}
%%
"if" { printf("(IF,if)\\n"); }
[a-zA-Z_][a-zA-Z0-9_]* { printf("(ID,%s)\\n", yytext); }
[0-9]+ { printf("(INT,%s)\\n", yytext); }
[ \\t\\r\\n]+ ;
. { fprintf(stderr,"illegal character: %s\\n",yytext); }
%%
int main(void) { return yylex(); }
''')
        # Intentionally incomplete manual scanner: evidence must identify the missing DFA implementation.
        (temp / "manual.c").write_bytes(b'''#include <stdio.h>
int main(void) { puts("TODO: manual DFA scanner"); return 0; }
''')
        report = temp / "report.docx"
        with zipfile.ZipFile(report, "w") as archive:
            archive.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
            archive.writestr("_rels/.rels", '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
            archive.writestr("word/document.xml", '<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>系统验收样例（非学生作业）：已编写Flex规则。构建命令flex lex.l，然后gcc lex.yy.c -o lexer。测试if abc 12 @，预期IF、ID、INT二元组和错误字符信息。手工自动机尚未完成，manual.c仅为占位。没有实际运行记录。AI建议了标识符正则，由自己检查了规则顺序。</w:t></w:r></w:p></w:body></w:document>')
        manifest = [dict(name=p.name, stored_path=str(p), size=p.stat().st_size,
                         kind="source" if p.suffix in {".l", ".c"} else "document")
                    for p in [temp / "lex.l", temp / "manual.c", report]]
        print("Live sample: reviewing .l + .c + Word using configured models", flush=True)
        analysis = analyze_report_file(file_path=report, student_name="系统验收样例（非学生）", course_name=catalog["name"],
                assignment_name=catalog["assignment_name"], assignment_requirements=catalog["assignment_requirements"],
                config=config, submission_files=manifest, assignment_spec=catalog["assignment_spec"], stage_id="lab1")
        print(json.dumps({"reviewed_files":analysis["_meta"]["reviewed_files"], "chunks":analysis["_meta"]["review_chunks"],
              "tasks":[dict(task=t["task_id"],status=t["status"],score=t["score"]) for s in analysis["stage_assessments"] for t in s["tasks"]]}, ensure_ascii=False), flush=True)
        records = []
        for index, q in enumerate(analysis["question_plan"]):
            answers = {
                "implementation": "我的lex.l把if关键字规则放在标识符规则之前，同长匹配时优先较早规则，较长标识符ifx仍匹配ID。yytext保存当前单词，输出二元组；点规则报错误字符，空白规则跳过。手工DFA还没完成，仅有TODO占位。我只写了预期输出，没有实际运行，所以功能还要验证。",
                "learning": "我学到了正则与词法单词的对应，关键字规则顺序和最长匹配不同。手工自动机尚未完成，状态转换仍需学习。",
                "ai_experience": "使用AI建议标识符正则，感觉能快速给框架，但需要我检查规则顺序并实际测试ifx和非法字符，AI输出不能直接当正确结果。",
                "course_feeling": "编译技术的理论开始和代码对应了，Flex比较容易上手，自动机状态设计仍困难。",
                "course_suggestions": "希望提供更多错误字符、关键字和标识符边界的示例，并增加手工自动机状态图的讲解。",
            }
            records.append(dict(id=f"acceptance_record_{index}", question=q["question"], answer=answers.get(q["category"], answers["implementation"])))
        print("Live sample: checking structured summary and score with simulated answers", flush=True)
        assessment = summarize_voice_qa(file_path=report, student_name="系统验收样例（非学生）", course_name=catalog["name"],
                assignment_name=catalog["assignment_name"], assignment_requirements=catalog["assignment_requirements"],
                report_analysis=analysis, qa_records=records, config=config)
        target = ROOT / "outputs" / "compiler-live-acceptance.json"
        target.write_text(json.dumps(dict(label="系统验收，模拟回答，非学生成绩", analysis=analysis, assessment=assessment),
                         ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(dict(status=assessment["status"], final_score=assessment["final_score"], artifact=str(target)), ensure_ascii=False), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Call configured billable model APIs with synthetic samples")
    if not parser.parse_args().live:
        parser.error("Explicit --live is required. Offline tests: python -m unittest discover -s tests -v")
    run_live()
