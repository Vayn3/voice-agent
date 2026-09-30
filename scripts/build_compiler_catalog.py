"""Rebuild the inspectable catalog from the taskbook transcription and structured criteria."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def task(id, title, requirement, optional=False):
    return dict(id=id, title=title, requirement=requirement, optional=optional)


def stage(id, name, tasks, questions):
    return dict(id=id, name=name, tasks=tasks, oral_focus=questions)


STAGES = [
    stage("lab1", "实验1：词法分析器的设计与实现", [
        task("lab1-flex", "Flex词法分析", "编写lex.l，使用Flex生成lex.yy.c、GCC生成词法分析可执行程序；以二元组输出单词，遇到错误字符显示错误信息。检查规则顺序、关键字与标识符区分、最长匹配与测试证据。"),
        task("lab1-automaton", "手工自动机词法分析", "依据自动机原理用C/C++编写词法分析器；输出单词二元组及错误字符信息。检查状态、转移、终态、回退或边界处理；不能只用Flex产物代替手工实现。"),
    ], ["指出lex.l中关键字和标识符如何区分，最长匹配与同长规则如何处理", "手工自动机状态如何设计，读到错误字符后如何继续扫描", "用自己的二元组定义解释一段实际输入及输出"]),
    stage("lab2", "实验2：语法分析器的设计与实现", [
        task("lab2-parser", "词法与语法协作", "为简单语言编写lex.l与parser.y，实现词法、语法分析；检查token、语义值、文法、优先级和结合性、语法错误处理。"),
        task("lab2-ast", "构造与显示AST", "实现displayAST.c显示抽象语法树，可在def.h定义共享类型与AST节点。检查产生式动作、树节点创建、子节点连接及可视化结果。"),
    ], ["选择一个parser.y产生式解释语义动作如何连接AST子节点", "表达式优先级与结合性在哪里定义，如何用测试验证", "AST显示与实际输入语法如何对应"]),
    stage("lab3", "实验3：符号表管理、语义检查与解释执行", [
        task("lab3-symbols", "单作用域符号表", "基于实验2的AST遍历解释执行；符号表保存变量名、类型（整型和单精度浮点）和值，首次赋值新增，后续赋值更新类型和值；不要求多作用域。"),
        task("lab3-input", "输入与动态类型", "输入类似赋值管理符号，按数据形式判定类型：12为整型、1.2为浮点型。"),
        task("lab3-arithmetic", "算术和类型转换", "运算符节点执行计算；操作数类型不同先转浮点；3/2必须得到整型1，3.0/2必须得到浮点1.500000。"),
        task("lab3-undefined", "未定义变量诊断", "a=b+100时若b未定义报语义错误；a不存在时新增、存在时更新。平台其他说明和测试样例未在任务书给出，需学生提供相应材料，不能虚构标准。"),
    ], ["用a=b+100说明未定义b与首次赋值a的区别", "输入12或1.2如何确定变量类型，重新赋值后属性如何更新", "3/2与3.0/2分别走哪条计算与转换路径"]),
    stage("design1", "课设阶段一：词法分析与语法分析", [
        task("design1-language", "语言定义与必需成分", "自定义文法并为语言命名，可采用C/C++/C#/Java部分语法。至少含char/int/float，算术、比较、自增自减、复合赋值，if/while/break/continue/for，多维数组，行注释和块注释；不要求预处理和多文件。"),
        task("design1-parser", "完整前端及AST开关", "实现词法与语法分析，可用LEX/FLEX、YACC/BISON、ANTLR(Java)或自行实现。阶段一展示AST，之后去掉常态显示，通过条件编译或设置控制。"),
        task("design1-extensions", "语言扩展", "字符串、switch和结构为选做；若实现应向教师说明并在报告中详细记录。", True),
    ], ["从自己的文法解释for循环、多维数组、复合赋值的解析", "如何消除文法冲突，AST调试显示如何关闭", "语言命名与功能取舍的依据是什么"]),
    stage("design2", "课设阶段二：符号表管理与语义分析", [
        task("design2-symbols", "符号表结构与管理", "无论前端是否使用工具，都要自行设计管理符号表，动态展示变化过程，完成相关属性计算与静态语义检查；调试显示可开关。按自定义文法说明作用域和类型管理策略。"),
        task("design2-errors", "静态语义错误", "实现多种静态语义错误检查，任务书原文为‘最低要求15种以上’，按不少于15种核查；必须列出不同错误类别、检测代码和独立触发样例，不能用同类错误的不同输入凑数。具体类别由实际文法决定，任务书未指定固定清单。"),
    ], ["符号表查找、插入与属性计算在哪里实现，何时更新", "选两种已实现的语义错误解释判定条件与定位方式", "如何证明错误类别达到任务书数量要求，避免重复计数"]),
    stage("design3", "课设阶段三：中间代码生成、代码优化", [
        task("design3-ir", "IR设计与生成", "定义中间代码形式，生成并显示中间代码，展示可开关；检查表达式、控制流、数组等支持范围，后续限制必须在报告中明确。"),
        task("design3-optimization", "代码优化", "基本块划分、DAG等中间代码优化为选做，未做不能扣必做分；实现时说明算法、优化前后结果与语义一致性证据。", True),
    ], ["以自己的if或循环代码解释标签、跳转与IR生成顺序", "临时变量和数组地址如何表示，IR显示如何关闭", "如实现优化，如何划分基本块并保证结果等价"]),
    stage("design4", "课设阶段四：目标代码生成", [
        task("design4-registers", "寄存器分配", "实现并说明寄存器分配策略，说明使用工具时自身配置和设计；检查临时变量映射、寄存器不足时的处理与IR衔接。"),
        task("design4-target", "目标语言与运行证据", "选定目标语言，建议MIPS并能在QTSPIM或MARS运行，但建议不作为唯一合格路线。阶段三/四可使用LLVM并自学文档。后续阶段可适当限制，例如目标生成仅支持整型，但必须在报告中说明。检查生成代码和实际运行证据；不要声称静态阅读已验证执行。"),
    ], ["追踪一条IR到目标指令及寄存器映射", "寄存器不足时如何处理，控制流跳转如何对应", "目标程序如何运行验证，限制在哪些阶段生效并如何说明"]),
]

POLICY = """\n\n四、本系统补充：提交、分析与语音答辩（不属于任务书原定评分标准）\n1. 可按基础实验1/2/3、课设阶段一/二/三/四提交，也可选全部阶段联合提交。每次可多选源代码、测试输入/期望输出、构建说明、报告或ZIP项目包。各次提交和问答保留，阶段提交仅评价当前阶段；全部阶段提交才形成综合作业评分。\n2. 请在报告或目录中注明文件所属阶段、运行步骤、完成范围、限制和AI辅助情况。源程序、目标程序、测试和报告仍需按任务书要求交头歌；本系统对二进制目标文件只记录存在性，不执行它们。\n3. 分析全部可读源代码与报告，逐阶段、逐任务给出实现细节、文件/行号或报告段落证据、满足程度、优点、缺点、粗略完成度与需答辩核实点。缺少材料写‘证据不足’，不得把报告自述当成已运行验证；选做项单列。\n4. 答辩一次问一个问题，结合该阶段实际代码追问设计、算法、类型/错误/控制流、测试和边界处理，检查能否解释自己的实现；必问学习收获、AI交互体验（未用AI则了解原因与独立解决方法）、对编译技术课程的感受和建议。允许AI辅助，不能只因用了AI推断不熟悉作业。\n5. 补充百分制建议：作业质量60%（必做任务满足度及测试/报告证据），实现理解与答辩表现30%，学习反思10%。反思按具体程度评价，不因课程意见是负面而扣分。未完整答辩不生成最终分；给出逐项依据、优缺点、真实性熟悉度判断、薄弱点及改进建议，最终分由系统计算并供教师复核。不得以表达口音、性格或AI使用本身评分。"""


def build():
    original = (ROOT / "docs" / "compiler-taskbook-transcription.txt").read_text(encoding="utf-8")
    spec = dict(version=1, source="docs/《编译技术》实验任务书(软件2026).doc", stages=STAGES,
                grading=dict(assignment=60, oral_defense=30, reflection=10),
                grading_origin="本系统补充建议，任务书未规定分值，由教师复核",
                semantic_error_minimum=15,
                global_requirements=["收集阅读文献、确定技术路线和系统方案，完成实现", "报告统一封面和目录，各小节可自行组织；提交标准格式打印版和电子版", "提交编译器源码、编译器或解释器目标程序、测试文件及报告", "头歌平台通关/作业目录提交；现场检查至少完成中间代码后可申请", "选做和特殊内容告知教师并在报告中说明，允许AI和其他工具辅助，功能仍须满足要求"])
    catalog = dict(id="COMP2026", name="编译技术实验", teacher_name="胡雯蔷", owner_username="teacher",
                   assignment_name="编译技术实验与完整编译器课程设计", assignment_requirements=original + POLICY,
                   assignment_spec=spec)
    target = ROOT / "data" / "courses" / "compiler-2026.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(target)


if __name__ == "__main__":
    build()
