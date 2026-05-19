"use client";

import { FormEvent, useEffect, useState } from "react";
import { createCourse, getCourse, getSession, listCourses } from "@/lib/api";
import { hasRole, readCurrentUser } from "@/lib/auth";
import type { AnalysisResponse, CourseDetail, CourseSummary, SessionSummary, User } from "@/types/api";

export default function TeacherPage() {
  const [courses, setCourses] = useState<CourseSummary[]>([]);
  const [selectedCourseId, setSelectedCourseId] = useState("");
  const [detail, setDetail] = useState<CourseDetail | null>(null);
  const [selectedReport, setSelectedReport] = useState<AnalysisResponse | null>(null);
  const [currentUser, setCurrentUser] = useState<User | null>(null);
  const [message, setMessage] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setCurrentUser(readCurrentUser());
    refreshCourses();
  }, []);

  useEffect(() => {
    if (!selectedCourseId) {
      setDetail(null);
      return;
    }
    refreshCourseDetail(selectedCourseId);
  }, [selectedCourseId]);

  async function refreshCourses() {
    try {
      const payload = await listCourses();
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
        teacher_name: String(form.get("teacher_name") || currentUser?.display_name || ""),
        teacher_user_id: currentUser?.id || null,
        assignment_name: String(form.get("assignment_name") || ""),
        assignment_requirements: String(form.get("assignment_requirements") || "")
      });
      formElement.reset();
      await refreshCourses();
      setSelectedCourseId(course.id);
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
            <h1>创建课程与作业要求</h1>
          </div>
          <div className="badge">{courses.length} 门课程</div>
        </div>

        {message && (
          <p className={message.includes("已") ? "message success" : "message error"}>
            {message}
          </p>
        )}

        {!hasRole(currentUser, ["teacher", "admin"]) && (
          <p className="message error">请先使用老师或管理员账号登录后再创建和查看课程。</p>
        )}

        <form className="form" onSubmit={handleCreateCourse}>
          <div className="grid">
            <label>
              课程名称
              <input name="name" placeholder="例如：推荐系统" required />
            </label>
            <label>
              老师姓名
              <input name="teacher_name" placeholder="例如：王老师" defaultValue={currentUser?.display_name || ""} />
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
          <button className="primary-button" type="submit" disabled={saving || !hasRole(currentUser, ["teacher", "admin"])}>
            {saving ? "创建中..." : "创建课程"}
          </button>
        </form>
      </section>

      <section className="result-layout">
        <article className="panel">
          <div className="panel-head">
            <h2>课程列表</h2>
          </div>
          {courses.length ? (
            <div className="list-stack">
              {courses.map((course) => (
                <button
                  className={course.id === selectedCourseId ? "list-button active" : "list-button"}
                  key={course.id}
                  type="button"
                  onClick={() => {
                    setSelectedCourseId(course.id);
                    setSelectedReport(null);
                  }}
                >
                  <strong>{course.name}</strong>
                  <span>{course.assignment_name} · {course.submission_count} 份提交</span>
                  <code>课程码：{course.id}</code>
                </button>
              ))}
            </div>
          ) : (
            <div className="empty">暂无课程。</div>
          )}
        </article>

        <article className="panel">
          <div className="panel-head">
            <h2>课程详情</h2>
            {selectedCourseId && (
              <button
                className="copy-button"
                type="button"
                onClick={() => refreshCourseDetail(selectedCourseId)}
              >
                刷新
              </button>
            )}
          </div>
          {detail ? (
            <div className="brief-list">
              <div className="brief-item">
                <strong>{detail.course.name}</strong>
                <p className="hint">课程码：{detail.course.id}</p>
              </div>
              <div className="brief-item">
                <strong>作业：</strong>{detail.course.assignment_name}
              </div>
              <div className="brief-item">
                <strong>要求：</strong>
                <p>{detail.course.assignment_requirements}</p>
              </div>
            </div>
          ) : (
            <div className="empty">选择课程后查看详情。</div>
          )}
        </article>

        <article className="panel full">
          <div className="panel-head">
            <h2>学生提交与总结报告</h2>
          </div>
          {detail?.submissions.length ? (
            <div className="submission-grid">
              <div className="list-stack">
                {detail.submissions.map((submission) => (
                  <button
                    className="list-button"
                    key={submission.id}
                    type="button"
                    onClick={() => inspectSubmission(submission)}
                  >
                    <strong>{submission.student_name}</strong>
                    <span>{submission.original_filename}</span>
                    <span>状态：{statusText(submission.status)}</span>
                  </button>
                ))}
              </div>
              <ReportPreview report={selectedReport} />
            </div>
          ) : (
            <div className="empty">这个课程还没有学生提交报告。</div>
          )}
        </article>
      </section>
    </>
  );
}

function ReportPreview({ report }: { report: AnalysisResponse | null }) {
  if (!report) {
    return <div className="empty">选择一份学生提交后查看报告分析结果。</div>;
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
      <h3>{report.session.student_name} 的报告总结</h3>
      <div className="brief-item">
        <strong>报告主题：</strong>{result?.report_brief?.topic || "未明确"}
      </div>
      <div className="brief-item">
        <strong>核心结论：</strong>
        <ul>{(result?.report_brief?.core_claims || ["未明确"]).map((item) => <li key={item}>{item}</li>)}</ul>
      </div>
      <div className="brief-item">
        <strong>教师关注点：</strong>
        <ul>{(result?.teacher_attention || ["未明确"]).map((item) => <li key={item}>{item}</li>)}</ul>
      </div>
      <div className="brief-item">
        <strong>语音问答 Prompt：</strong>
        <pre className="prompt-box compact">{result?.voice_qa_prompt || "未生成"}</pre>
      </div>
    </div>
  );
}

function statusText(status: string) {
  const map: Record<string, string> = {
    pending: "等待分析",
    processing: "分析中",
    completed: "已完成",
    failed: "失败"
  };
  return map[status] || status;
}
