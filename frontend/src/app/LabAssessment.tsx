import type { AnalysisResult, CourseSummary } from "@/types/api";

export function CourseRequirements({ course }: { course: CourseSummary }) {
  return <div className="lab-requirements">
    <p><strong>任课教师：</strong>{course.teacher_name || "未填写"}</p>
    {course.assignment_spec?.stages?.map((stage) => <details key={stage.id}>
      <summary>{stage.name}</summary>
      {stage.tasks.map((task) => <div className="brief-item" key={task.id}>
        <strong>{task.title} · {task.optional ? "选做" : "必做"}</strong><p>{task.requirement}</p>
      </div>)}
    </details>)}
    <details open={!course.assignment_spec?.stages?.length}>
      <summary>完整任务书与提交、答辩、评分要求</summary>
      <p className="qa-summary">{course.assignment_requirements}</p>
    </details>
  </div>;
}

const statuses: Record<string, string> = { met: "满足", partial: "部分满足", missing: "未完成", insufficient_evidence: "证据不足" };

export function LabAssessment({ result }: { result: AnalysisResult | null | undefined }) {
  if (!result) return null;
  return <div className="lab-assessment">
    {result.stage_assessments?.length ? <>
      <h3>实验完成度与实现分析</h3>
      <p className="hint">评价范围：{result.scoring_scope} · 必做任务粗略完成度：{result.preliminary_assignment_score ?? "待核实"}/100。最终评分结合语音答辩表现。</p>
      {result.stage_assessments.map((stage) => <details key={stage.stage_id} open>
        <summary>{stage.stage_name} · {stage.completion_score}/100</summary>
        <p>{stage.conclusion}</p>
        {stage.tasks.map((task) => <article className="brief-item" key={task.task_id}>
          <strong>{task.title}（{task.optional ? "选做" : "必做"}） · {statuses[task.status] || task.status} · {task.score}/100</strong>
          <p>{task.implementation_details}</p>
          <p><strong>证据：</strong>{task.evidence.join("；") || "未找到可核实证据"}</p>
          <p><strong>优点：</strong>{task.strengths.join("；") || "暂无明确证据"}</p>
          <p><strong>不足：</strong>{task.weaknesses.join("；") || "暂无明确不足"}</p>
        </article>)}
      </details>)}
    </> : null}
    {result.teacher_attention?.length ? <div className="brief-item"><strong>待核实与关注点</strong><ul>{result.teacher_attention.map((item, i) => <li key={i}>{item}</li>)}</ul></div> : null}
    {result.file_coverage?.length ? <details><summary>文件审查覆盖情况（{result.file_coverage.filter(f => f.status === "reviewed").length}份已审查）</summary>
      <ul>{result.file_coverage.map((file, i) => <li key={i}>{file.name}：{file.status === "reviewed" ? `已审查 · ${file.chunks}块` : file.reason || "未分析"}</li>)}</ul>
      <p className="hint">源码全部分块静态阅读，未执行程序；PDF/Word使用文档模型解析，提取质量需结合证据核实。</p>
    </details> : null}
  </div>;
}

export function FinalScore({ result }: { result: AnalysisResult | null | undefined }) {
  const assessment = result?.final_assessment;
  if (!assessment) return null;
  const components = [["作业质量", assessment.assignment], ["实现理解与答辩", assessment.oral_defense], ["学习反思", assessment.reflection]] as const;
  return <div className="final-assessment">
    <h3>{assessment.final_score === null ? "答辩尚不完整，暂不生成最终分" : `最终建议评分：${assessment.final_score} / 100`}</h3>
    <p>评分范围：{assessment.scoring_scope}</p>
    <p>作业熟悉度：{assessment.familiarity} · {assessment.familiarity_rationale}</p>
    {components.map(([name, component]) => <div className="brief-item" key={name}>
      <strong>{name}：{component.score}/100 · 权重{component.weight}% · 折合{component.weighted_points}分</strong>
      <p>{component.rationale}</p><p className="hint">依据：{component.evidence.join("；")}</p>
    </div>)}
    {assessment.missing_required_questions?.length ? <p className="message">待补充必答问题：{assessment.missing_required_questions.join("、")}</p> : null}
    <p><strong>优点：</strong>{assessment.strengths.join("；")}</p>
    <p><strong>不足：</strong>{assessment.weaknesses.join("；")}</p>
    <p><strong>改进建议：</strong>{assessment.improvements.join("；")}</p>
    <p className="hint">{assessment.grading_note}</p>
  </div>;
}
