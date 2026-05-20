"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { RequireRole } from "@/app/RequireRole";
import { createCourse, getCourse, getSession, listCourses } from "@/lib/api";
import type { AnalysisResponse, CourseDetail, CourseSummary, SessionSummary, User } from "@/types/api";

type TeacherView = "courses" | "create";

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
              <p>{selectedCourse.assignment_requirements}</p>
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
  if (!report) {
    return <div className="empty">选择一名学生后查看报告分析、问题计划和问答总结。</div>;
  }
  const result = report.result;
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
      <div className="brief-item">
        <strong>生成的问题：</strong>
        <ul>{(result?.question_plan || []).map((item, index) => <li key={item.id || index}>{item.question}</li>)}</ul>
      </div>
      {result?.voice_qa_summary && (
        <div className="brief-item">
          <strong>问答总结报告：</strong>
          <p className="qa-summary">{result.voice_qa_summary}</p>
        </div>
      )}
    </div>
  );
}

function submissionStatus(submission: SessionSummary) {
  if (submission.status !== "completed") return statusText(submission.status);
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
