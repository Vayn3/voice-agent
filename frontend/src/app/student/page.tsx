"use client";

import Link from "next/link";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { RequireRole } from "@/app/RequireRole";
import {
  checkConfig,
  createCourseSession,
  enrollCourse,
  getSession,
  listStudentCourses
} from "@/lib/api";
import type { AnalysisResponse, CourseSummary, StudentCourse, User } from "@/types/api";

type StudentView = "courses" | "join";

export default function StudentPage() {
  return (
    <RequireRole roles={["student"]}>
      {(user) => <StudentWorkspace currentUser={user} />}
    </RequireRole>
  );
}

function StudentWorkspace({ currentUser }: { currentUser: User }) {
  const [view, setView] = useState<StudentView>("courses");
  const [items, setItems] = useState<StudentCourse[]>([]);
  const [selectedCourseId, setSelectedCourseId] = useState("");
  const [session, setSession] = useState<AnalysisResponse | null>(null);
  const [fileName, setFileName] = useState("选择或拖入课程报告文件");
  const [status, setStatus] = useState("等待提交");
  const [message, setMessage] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [joining, setJoining] = useState(false);

  const selectedItem = useMemo(
    () => items.find((item) => item.course.id === selectedCourseId),
    [items, selectedCourseId]
  );
  const selectedCourse = selectedItem?.course;
  const latestSubmission = selectedItem?.latest_submission;
  const activeSessionId = session?.session.id || latestSubmission?.id || "";
  const activeSubmission = session?.session || latestSubmission;
  const canEnterQA =
    activeSubmission?.status === "completed" && !activeSubmission.voice_qa_summary_ready;
  const isAnalyzing = submitting || session?.session.status === "pending" || session?.session.status === "processing";

  useEffect(() => {
    refreshCourses();
  }, [currentUser.id]);

  useEffect(() => {
    if (!session?.session.id) return;
    if (["completed", "failed"].includes(session.session.status)) return;

    const timer = window.setInterval(async () => {
      try {
        const payload = await getSession(session.session.id);
        setSession(payload);
        if (payload.session.status === "completed") {
          setStatus("报告分析完毕，可以进入问答界面。");
          await refreshCourses(payload.session.course_id || selectedCourseId);
        } else if (payload.session.status === "failed") {
          setStatus(`分析失败：${payload.session.error || "未知错误"}`);
        } else {
          setStatus(payload.session.status === "processing" ? "正在分析报告" : "等待分析");
        }
      } catch (error) {
        setStatus(error instanceof Error ? error.message : "获取分析状态失败");
      }
    }, 1800);

    return () => window.clearInterval(timer);
  }, [session?.session.id, session?.session.status, selectedCourseId]);

  async function refreshCourses(nextSelectedId?: string) {
    try {
      const payload = await listStudentCourses(currentUser.id);
      setItems(payload);
      setSelectedCourseId((current) => nextSelectedId || current || payload[0]?.course.id || "");
    } catch {
      setMessage("后端服务未连接，请确认 FastAPI 已启动。");
    }
  }

  async function handleJoinCourse(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setJoining(true);
    setMessage("");
    const form = new FormData(event.currentTarget);
    const courseCode = String(form.get("course_code") || "").trim();
    try {
      const course = await enrollCourse(courseCode, {
        student_user_id: currentUser.id,
        student_name: currentUser.display_name
      });
      await refreshCourses(course.id);
      setView("courses");
      setMessage("课程加入成功。");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "加入课程失败");
    } finally {
      setJoining(false);
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    if (!selectedCourseId) {
      setMessage("请先选择一个已加入课程。");
      return;
    }
    const checked = await checkConfig();
    if (!checked.configured) {
      setMessage(checked.message);
      return;
    }

    const formData = new FormData(formElement);
    formData.set("student_user_id", currentUser.id);
    setSubmitting(true);
    setMessage("");
    setStatus("正在上传报告");
    try {
      const payload = await createCourseSession(selectedCourseId, formData);
      setSession(payload);
      setStatus("已提交，等待报告分析。");
      await refreshCourses(selectedCourseId);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "提交失败");
      setStatus("提交失败");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="workspace">
      <div className="page-head">
        <div>
          <p className="eyebrow">学生端</p>
          <h1>{view === "join" ? "加入课程" : "我的课程"}</h1>
        </div>
        <div className="segmented">
          <button className={view === "courses" ? "active" : ""} type="button" onClick={() => setView("courses")}>
            我的课程
          </button>
          <button className={view === "join" ? "active" : ""} type="button" onClick={() => setView("join")}>
            加入课程
          </button>
        </div>
      </div>

      {message && (
        <p className={message.includes("成功") ? "message success" : "message error"}>
          {message}
        </p>
      )}

      {view === "join" ? (
        <form className="form" onSubmit={handleJoinCourse}>
          <label>
            课程码
            <input name="course_code" placeholder="请输入老师提供的课程码" required />
          </label>
          <button className="primary-button" type="submit" disabled={joining}>
            {joining ? "加入中..." : "加入课程"}
          </button>
        </form>
      ) : (
        <div className="student-course-grid">
          <section className="panel flat">
            <div className="panel-head">
              <h2>已加入课程</h2>
            </div>
            {items.length ? (
              <div className="list-stack">
                {items.map((item) => (
                  <button
                    className={item.course.id === selectedCourseId ? "list-button active" : "list-button"}
                    key={item.course.id}
                    type="button"
                    onClick={() => {
                      setSelectedCourseId(item.course.id);
                      setSession(null);
                      setStatus(item.latest_submission ? studentSubmissionStatus(item.latest_submission) : "等待提交");
                    }}
                  >
                    <strong>{item.course.name}</strong>
                    <span>{item.course.assignment_name}</span>
                    <span>状态：{item.latest_submission ? studentSubmissionStatus(item.latest_submission) : "未提交报告"}</span>
                    <code>课程码：{item.course.id}</code>
                  </button>
                ))}
              </div>
            ) : (
              <div className="empty">还没有加入课程，请先通过课程码加入。</div>
            )}
          </section>

          <section className="panel flat">
            <div className="panel-head">
              <h2>课程要求</h2>
            </div>
            {selectedCourse ? (
              <div className="brief-list">
                <div className="brief-item">
                  <strong>{selectedCourse.name}</strong>
                  <p className="hint">课程码：{selectedCourse.id}</p>
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
              <div className="empty">选择课程后查看要求。</div>
            )}
          </section>

          <section className="panel flat full">
            <div className="panel-head">
              <h2>提交报告</h2>
              {canEnterQA && activeSessionId && (
                <Link className="secondary-button" href={`/student/qa/${activeSessionId}`}>
                  进入问答界面
                </Link>
              )}
            </div>

            {selectedCourse ? (
              <>
                <form className="form" onSubmit={handleSubmit}>
                  <input name="student_name" type="hidden" value={currentUser.display_name} />
                  <label className="dropzone">
                    <input
                      name="report_file"
                      type="file"
                      accept=".pdf,.doc,.docx,.md,.txt"
                      required
                      onChange={(event) =>
                        setFileName(event.currentTarget.files?.[0]?.name || "选择或拖入课程报告文件")
                      }
                    />
                    <strong>{fileName}</strong>
                    <small>支持 PDF、Word、Markdown、TXT</small>
                  </label>
                  <button className="primary-button" type="submit" disabled={isAnalyzing}>
                    {isAnalyzing ? "正在分析报告..." : "上传并分析报告"}
                  </button>
                </form>
                <section className="status-row">
                  <div>
                    <p className="label">当前状态</p>
                    <strong>{session ? status : latestSubmission ? studentSubmissionStatus(latestSubmission) : status}</strong>
                  </div>
                  <div>
                    <p className="label">会话 ID</p>
                    <code>{activeSessionId || "-"}</code>
                  </div>
                </section>
              </>
            ) : (
              <div className="empty">请先加入并选择课程。</div>
            )}
          </section>
        </div>
      )}
    </section>
  );
}

function studentSubmissionStatus(submission: StudentCourse["latest_submission"]) {
  if (!submission) return "未提交报告";
  if (submission.voice_qa_summary_ready) return "已完成问答总结";
  const map: Record<string, string> = {
    pending: "等待分析",
    processing: "分析中",
    completed: "报告已分析",
    failed: "失败"
  };
  return map[submission.status] || submission.status;
}
