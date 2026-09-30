"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { RequireRole } from "@/app/RequireRole";
import { CourseRequirements, FinalScore, LabAssessment } from "@/app/LabAssessment";
import { createCourse, getCourse, getSession, listCourses, listQARecords } from "@/lib/api";
import type { AnalysisResponse, CourseDetail, CourseSummary, QARecord, SessionSummary, User } from "@/types/api";

type TeacherView = "courses" | "create";
type ReportTab = "questions" | "records" | "summary";

export default function TeacherPage() {
  return (
    <RequireRole roles={["teacher"]}>
      {(user) => <TeacherWorkspace currentUser={user} />}
    </RequireRole>
  );
}

function TeacherWorkspace({ currentUser }: { currentUser: User }) {
  const [view, setView] = useState<TeacherView>("courses");
  const [courses, setCourses] = useState<CourseSummary[]>([]);
  const [selectedCourseId, setSelectedCourseId] = useState("");
  const [detail, setDetail] = useState<CourseDetail | null>(null);
  const [selectedReport, setSelectedReport] = useState<AnalysisResponse | null>(null);
  const [message, setMessage] = useState("");
  const [saving, setSaving] = useState(false);

  const selectedCourse = useMemo(
    () => courses.find((course) => course.id === selectedCourseId),
    [courses, selectedCourseId]
  );

  useEffect(() => {
    refreshCourses();
  }, [currentUser.id]);

  useEffect(() => {
    if (!selectedCourseId) {
      setDetail(null);
      return;
    }
    refreshCourseDetail(selectedCourseId);
  }, [selectedCourseId]);

  async function refreshCourses() {
    try {
      const payload = await listCourses(currentUser.role === "admin" ? null : currentUser.id);
      setCourses(payload);
      setSelectedCourseId((current) => current || payload[0]?.id || "");
    } catch {
      setMessage("后端服务未连接，请确认 FastAPI 已启动。");
    }
  }

  async function refreshCourseDetail(courseId: string) {
    const payload = await getCourse(courseId);
    setDetail(payload);
  }

  async function handleCreateCourse(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    setSaving(true);
    setMessage("");
    const form = new FormData(formElement);
    try {
      const course = await createCourse({
        name: String(form.get("name") || ""),
        teacher_name: String(form.get("teacher_name") || currentUser.display_name || ""),
        teacher_user_id: currentUser.id,
        assignment_name: String(form.get("assignment_name") || ""),
        assignment_requirements: String(form.get("assignment_requirements") || "")
      });
      formElement.reset();
      await refreshCourses();
      setSelectedCourseId(course.id);
      setView("courses");
      setMessage("课程已创建。");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "创建课程失败");
    } finally {
      setSaving(false);
    }
  }

  async function inspectSubmission(submission: SessionSummary) {
    const payload = await getSession(submission.id);
    setSelectedReport(payload);
  }

  return (
    <>
      <section className="workspace">
        <div className="page-head">
          <div>
            <p className="eyebrow">老师端</p>
            <h1>{view === "create" ? "创建课程" : "我的课程"}</h1>
          </div>
          <div className="segmented">
            <button className={view === "courses" ? "active" : ""} type="button" onClick={() => setView("courses")}>
              我的课程
            </button>
            <button className={view === "create" ? "active" : ""} type="button" onClick={() => setView("create")}>
              创建课程
            </button>
          </div>
        </div>

        {message && (
          <p className={message.includes("已") ? "message success" : "message error"}>
            {message}
          </p>
        )}

        {view === "create" ? (
          <form className="form" onSubmit={handleCreateCourse}>
            <div className="grid">
              <label>
                课程名称
                <input name="name" placeholder="例如：推荐系统" required />
              </label>
              <label>
                老师姓名
                <input name="teacher_name" placeholder="例如：王老师" defaultValue={currentUser.display_name} />
              </label>
              <label>
                作业名称
                <input name="assignment_name" placeholder="例如：课程报告" required />
              </label>
            </div>
            <label>
              课程作业要求
              <textarea
                name="assignment_requirements"
                placeholder="输入评分维度、必答要点、报告结构、实验要求、禁止事项等"
                required
                rows={6}
              />
            </label>
            <button className="primary-button" type="submit" disabled={saving}>
              {saving ? "创建中..." : "创建课程"}
            </button>
          </form>
        ) : (
          <TeacherCourses
            courses={courses}
            detail={detail}
            selectedCourse={selectedCourse}
            selectedCourseId={selectedCourseId}
            selectedReport={selectedReport}
            onRefreshCourses={refreshCourses}
            onSelectCourse={(courseId) => {
              setSelectedCourseId(courseId);
              setSelectedReport(null);
            }}
            onInspectSubmission={inspectSubmission}
          />
        )}
      </section>
    </>
  );
}

function TeacherCourses({
  courses,
  detail,
  selectedCourse,
  selectedCourseId,
  selectedReport,
  onRefreshCourses,
  onSelectCourse,
  onInspectSubmission
}: {
  courses: CourseSummary[];
  detail: CourseDetail | null;
  selectedCourse?: CourseSummary;
  selectedCourseId: string;
  selectedReport: AnalysisResponse | null;
  onRefreshCourses: () => Promise<void>;
  onSelectCourse: (courseId: string) => void;
  onInspectSubmission: (submission: SessionSummary) => Promise<void>;
}) {
  return (
    <div className="teacher-grid">
      <section className="panel flat">
        <div className="panel-head">
          <h2>课程列表</h2>
          <button className="copy-button" type="button" onClick={onRefreshCourses}>
            刷新
          </button>
        </div>
        {courses.length ? (
          <div className="list-stack">
            {courses.map((course) => (
              <button
                className={course.id === selectedCourseId ? "list-button active" : "list-button"}
                key={course.id}
                type="button"
                onClick={() => onSelectCourse(course.id)}
              >
                <strong>{course.name}</strong>
                <span>{course.assignment_name}</span>
                <span>
                  {course.student_count} 名学生，{course.analyzed_count} 份报告已分析，{course.summarized_count} 份已生成问答总结
                </span>
                <code>课程码：{course.id}</code>
              </button>
            ))}
          </div>
        ) : (
          <div className="empty">还没有创建课程。</div>
        )}
      </section>

      <section className="panel flat">
        <div className="panel-head">
          <h2>课程信息</h2>
        </div>
        {selectedCourse ? (
          <div className="brief-list">
            <div className="brief-item">
              <strong>{selectedCourse.name}</strong>
              <p className="hint">课程码：{selectedCourse.id}</p>
            </div>
            <div className="metric-row">
              <div><strong>{selectedCourse.student_count}</strong><span>加入学生</span></div>
              <div><strong>{selectedCourse.analyzed_count}</strong><span>报告已分析</span></div>
              <div><strong>{selectedCourse.summarized_count}</strong><span>已生成总结</span></div>
            </div>
            <div className="brief-item">
              <strong>作业：</strong>{selectedCourse.assignment_name}
            </div>
            <div className="brief-item">
              <strong>要求：</strong>
              <CourseRequirements course={selectedCourse} />
            </div>
          </div>
        ) : (
          <div className="empty">选择课程后查看详情。</div>
        )}
      </section>

      <section className="panel flat full">
        <div className="panel-head">
          <h2>学生提交</h2>
        </div>
        {detail?.submissions.length ? (
          <div className="submission-grid">
            <div className="list-stack">
              {detail.submissions.map((submission) => (
                <button
                  className="list-button"
                  key={submission.id}
                  type="button"
                  onClick={() => onInspectSubmission(submission)}
                >
                  <strong>{submission.student_name}</strong>
                  <span>{submission.original_filename}</span>
                  <span>阶段：{detail.course.assignment_spec?.stages?.find(s => s.id === submission.stage_id)?.name || "全部阶段/课程作业"}</span>
                  <span>状态：{submissionStatus(submission)}</span>
                </button>
              ))}
            </div>
            <ReportPreview report={selectedReport} />
          </div>
        ) : (
          <div className="empty">这个课程还没有学生提交报告。</div>
        )}
      </section>
    </div>
  );
}

function ReportPreview({ report }: { report: AnalysisResponse | null }) {
  const [activeTab, setActiveTab] = useState<ReportTab>("questions");
  const [qaRecords, setQARecords] = useState<QARecord[]>([]);
  const [qaMessage, setQAMessage] = useState("");

  useEffect(() => {
    setActiveTab("questions");
    setQARecords([]);
    setQAMessage("");
    if (!report?.session.id) return;

    listQARecords(report.session.id)
      .then(setQARecords)
      .catch((error) => {
        setQAMessage(error instanceof Error ? error.message : "无法读取问答记录");
      });
  }, [report?.session.id]);

  if (!report) {
    return <div className="empty">选择一名学生后查看报告分析、问题计划和问答总结。</div>;
  }
  const result = report.result;
  const maxFollowUps =
    typeof result?.coverage_threshold?.max_follow_ups_per_question === "number"
      ? result.coverage_threshold.max_follow_ups_per_question
      : null;
  const highPriorityRequired =
    typeof result?.coverage_threshold?.required_high_priority_completed === "boolean"
      ? result.coverage_threshold.required_high_priority_completed
      : null;
  const doneRule =
    typeof result?.coverage_threshold?.done_rule === "string"
      ? result.coverage_threshold.done_rule
      : "";
  const questionStrategy = [
    "按问题优先级依次提问，一次只提出一个问题，等待学生回答后再进入下一步。",
    maxFollowUps !== null ? `回答不充分时，每个问题最多追问 ${maxFollowUps} 次。` : "",
    highPriorityRequired === true ? "高优先级问题需要覆盖完成后，再判断是否可以结束问答。" : "",
    doneRule ? `结束判断：${doneRule}` : ""
  ].filter(Boolean);
  if (report.session.status !== "completed") {
    return (
      <div className="brief-item">
        <strong>{report.session.student_name}</strong>
        <p>当前状态：{statusText(report.session.status)}</p>
        {report.session.error && <p className="message error">{report.session.error}</p>}
      </div>
    );
  }

  return (
    <div className="summary-preview">
      <h3>{report.session.student_name} 的报告</h3>
      <div className="report-overview">
        <div className="brief-item">
          <strong>状态：</strong>{result?.voice_qa_summary ? "已完成问答总结" : "报告已分析"}
        </div>
        <div className="brief-item">
          <strong>报告主题：</strong>{result?.report_brief?.topic || "未明确"}
        </div>
        <div className="brief-item">
          <strong>核心结论：</strong>
          <ul>{(result?.report_brief?.core_claims || ["未明确"]).map((item) => <li key={item}>{item}</li>)}</ul>
        </div>
      </div>

      <LabAssessment result={result} />
      <div className="report-tabs">
        <button className={activeTab === "questions" ? "active" : ""} type="button" onClick={() => setActiveTab("questions")}>
          生成问题
        </button>
        <button className={activeTab === "records" ? "active" : ""} type="button" onClick={() => setActiveTab("records")}>
          问答记录
        </button>
        <button className={activeTab === "summary" ? "active" : ""} type="button" onClick={() => setActiveTab("summary")}>
          总结报告
        </button>
      </div>

      {activeTab === "questions" && (
        <div className="report-section">
          <h4>生成的问题与提问策略</h4>
          <div className="brief-item">
            <strong>整体提问策略：</strong>
            <ul>
              {questionStrategy.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>
          {result?.voice_qa_prompt && (
            <div className="brief-item">
              <strong>传入语音模型的提问提示词：</strong>
              <p className="qa-summary">{result.voice_qa_prompt}</p>
            </div>
          )}
          {result?.question_plan?.length ? (
            <div className="question-list">
              {result.question_plan.map((item, index) => (
                <article className="question-item" key={item.id || index}>
                  <header>
                    <strong>{item.question || `问题 ${index + 1}`}</strong>
                    {item.priority && <span className="priority">{item.priority}</span>}
                  </header>
                  {item.focus && <p><strong>关注点：</strong>{item.focus}</p>}
                  {item.follow_up_when_insufficient?.length ? (
                    <p><strong>回答不足时追问：</strong>{item.follow_up_when_insufficient.join("；")}</p>
                  ) : null}
                  {item.sufficient_answer_criteria?.length ? (
                    <p><strong>充分回答标准：</strong>{item.sufficient_answer_criteria.join("；")}</p>
                  ) : null}
                  {item.evidence_hint && <p><strong>证据线索：</strong>{item.evidence_hint}</p>}
                </article>
              ))}
            </div>
          ) : (
            <div className="empty">暂无生成问题。</div>
          )}
        </div>
      )}

      {activeTab === "records" && (
        <div className="report-section">
          <h4>问答记录</h4>
          {qaMessage && <p className="message error">{qaMessage}</p>}
          {qaRecords.length ? (
            <div className="qa-record-list">
              {qaRecords.map((record, index) => (
                <article className="qa-record" key={record.id || index}>
                  <strong>Q{index + 1}：{record.question}</strong>
                  <p>A：{record.answer}</p>
                </article>
              ))}
            </div>
          ) : (
            <div className="empty">暂无问答记录。</div>
          )}
        </div>
      )}

      {activeTab === "summary" && (
        <div className="report-section">
          <h4>问答总结报告</h4>
          <FinalScore result={result} />
          {result?.voice_qa_summary ? (
            <p className="qa-summary">{result.voice_qa_summary}</p>
          ) : (
            <div className="empty">暂无总结报告。</div>
          )}
        </div>
      )}
    </div>
  );
}

function submissionStatus(submission: SessionSummary) {
  if (submission.status !== "completed") return statusText(submission.status);
  if (submission.final_assessment_status === "insufficient_qa") return "答辩尚不完整，待补充";
  if (typeof submission.final_score === "number") return `已完成评分：${submission.final_score}/100`;
  return submission.voice_qa_summary_ready ? "已完成问答总结" : "报告已分析";
}

function statusText(status: string) {
  const map: Record<string, string> = {
    pending: "等待分析",
    processing: "分析中",
    completed: "报告已分析",
    failed: "失败"
  };
  return map[status] || status;
}
