"use client";

import Link from "next/link";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { RequireRole } from "@/app/RequireRole";
import { CourseRequirements, FinalScore, LabAssessment } from "@/app/LabAssessment";
import {
  checkConfig,
  createCourseSession,
  enrollCourse,
  getSession,
  listQARecords,
  listStudentCourses,
  listCourses
} from "@/lib/api";
import type { AnalysisResponse, CourseSummary, QARecord, SessionSummary, StudentCourse, User } from "@/types/api";

type StudentView = "courses" | "join";
type CourseDetailMode = "overview" | "upload" | "records" | "summary";

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
  const [detailMode, setDetailMode] = useState<CourseDetailMode>("overview");
  const [qaRecords, setQARecords] = useState<QARecord[]>([]);
  const [qaMessage, setQAMessage] = useState("");
  const [fileName, setFileName] = useState("选择或拖入课程报告文件");
  const [status, setStatus] = useState("等待提交");
  const [message, setMessage] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [joining, setJoining] = useState(false);
  const [availableCourses, setAvailableCourses] = useState<CourseSummary[]>([]);

  const selectedItem = useMemo(
    () => items.find((item) => item.course.id === selectedCourseId),
    [items, selectedCourseId]
  );
  const selectedCourse = selectedItem?.course;
  const latestSubmission = selectedItem?.latest_submission;
  const activeSessionId = session?.session.id || latestSubmission?.id || "";
  const activeSubmission = session?.session || latestSubmission;
  const activeResult = session?.session.id === activeSessionId ? session.result : null;
  const displayStatus = submitting
    ? status
    : activeSubmission
      ? studentSubmissionStatus(activeSubmission)
      : "未提交报告";
  const isAnalyzing =
    submitting || activeSubmission?.status === "pending" || activeSubmission?.status === "processing";

  useEffect(() => {
    refreshCourses();
    listCourses().then(setAvailableCourses).catch(() => {});
  }, [currentUser.id]);

  useEffect(() => {
    if (!latestSubmission?.id) return;
    let cancelled = false;
    getSession(latestSubmission.id).then(payload => {
      if (!cancelled) setSession(current => current?.session.course_id === selectedCourseId ? current : payload);
    }).catch(() => {});
    return () => { cancelled = true; };
  }, [latestSubmission?.id, selectedCourseId]);

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

  async function openReportMode(mode: CourseDetailMode) {
    setMessage("");
    setQAMessage("");
    if (mode === "overview") {
      setDetailMode("overview");
      return;
    }
    if (!activeSessionId) return;
    try {
      const payload = await getSession(activeSessionId);
      setSession(payload);
      setDetailMode(mode);
      if (mode === "records") {
        const records = await listQARecords(activeSessionId);
        setQARecords(records);
      }
    } catch (error) {
      const text = error instanceof Error ? error.message : "加载报告信息失败";
      if (mode === "records") {
        setQAMessage(text);
      } else {
        setMessage(text);
      }
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
      setDetailMode("overview");
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
          <div className="brief-list">
            {availableCourses.map(course => <div className="brief-item" key={course.id}>
              <strong>{course.name}</strong><p>教师：{course.teacher_name} · 课程码：{course.id}</p>
            </div>)}
          </div>
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
                      setDetailMode("overview");
                      setQARecords([]);
                      setQAMessage("");
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

          <section className="panel flat student-course-detail">
            <div className="panel-head">
              <h2>{selectedCourse ? selectedCourse.name : "课程信息"}</h2>
            </div>
            {selectedCourse ? (
              <StudentCourseDetail
                activeResult={activeResult}
                activeSessionId={activeSessionId}
                activeSubmission={activeSubmission}
                currentUser={currentUser}
                detailMode={detailMode}
                fileName={fileName}
                isAnalyzing={isAnalyzing}
                qaMessage={qaMessage}
                qaRecords={qaRecords}
                selectedCourse={selectedCourse}
                status={displayStatus}
                submitting={submitting}
                onEnterUpload={() => {
                  setDetailMode("upload");
                  setMessage("");
                }}
                onFileNameChange={setFileName}
                submissions={selectedItem?.submissions || []}
                onSelectSubmission={async (id) => {
                  try {
                    setSession(await getSession(id));
                    setDetailMode("overview");
                  } catch (error) { setMessage(error instanceof Error ? error.message : "读取提交失败"); }
                }}
                onOpenReportMode={openReportMode}
                onSubmit={handleSubmit}
              />
            ) : (
              <div className="empty">选择课程后查看要求。</div>
            )}
          </section>
        </div>
      )}
    </section>
  );
}

function StudentCourseDetail({
  activeResult,
  activeSessionId,
  activeSubmission,
  currentUser,
  detailMode,
  fileName,
  isAnalyzing,
  qaMessage,
  qaRecords,
  selectedCourse,
  status,
  submitting,
  onEnterUpload,
  onFileNameChange,
  submissions,
  onSelectSubmission,
  onOpenReportMode,
  onSubmit
}: {
  activeResult: AnalysisResponse["result"] | null;
  activeSessionId: string;
  activeSubmission: StudentCourse["latest_submission"];
  currentUser: User;
  detailMode: CourseDetailMode;
  fileName: string;
  isAnalyzing: boolean;
  qaMessage: string;
  qaRecords: QARecord[];
  selectedCourse: StudentCourse["course"];
  status: string;
  submitting: boolean;
  onEnterUpload: () => void;
  onFileNameChange: (name: string) => void;
  submissions: SessionSummary[];
  onSelectSubmission: (id: string) => Promise<void>;
  onOpenReportMode: (mode: CourseDetailMode) => Promise<void>;
  onSubmit: (event: FormEvent<HTMLFormElement>) => Promise<void>;
}) {
  const hasSubmitted = Boolean(activeSubmission);
  const isPendingOrProcessing =
    activeSubmission?.status === "pending" || activeSubmission?.status === "processing" || isAnalyzing;
  const isAnalyzed = activeSubmission?.status === "completed" && (!activeSubmission.voice_qa_summary_ready || activeSubmission.final_assessment_status === "insufficient_qa");
  const isSummarized = Boolean(activeSubmission?.voice_qa_summary_ready);
  const canUpload = !hasSubmitted || activeSubmission?.status === "failed" || detailMode === "upload";

  return (
    <div className="student-detail">
      <div className="brief-list">
        <div className="brief-item">
          <strong>作业：</strong>{selectedCourse.assignment_name}
        </div>
        <div className="brief-item">
          <strong>课程码：</strong>{selectedCourse.id}
        </div>
        <div className="brief-item">
          <strong>课程要求：</strong>
          <CourseRequirements course={selectedCourse} />
        </div>
        <div className="brief-item">
          <strong>我的提交状态：</strong>{status}
        </div>
      </div>

      {submissions.length ? <label>阶段提交历史（每次提交独立保留）
        <select value={activeSessionId} onChange={event => onSelectSubmission(event.currentTarget.value)}>
          {submissions.map(item => <option value={item.id} key={item.id}>
            {selectedCourse.assignment_spec?.stages?.find(stage => stage.id === item.stage_id)?.name || "全部阶段"} · {item.original_filename} · {studentSubmissionStatus(item)} · {new Date(item.created_at).toLocaleString()}
          </option>)}
        </select>
      </label> : null}
      {activeSubmission?.error && <p className="message error">{activeSubmission.error}</p>}
      {detailMode === "overview" && <LabAssessment result={activeResult} />}

      <div className="student-action-row">
        {hasSubmitted && !isPendingOrProcessing && <button className="secondary-button" type="button" onClick={onEnterUpload}>提交其他阶段 / 新版本</button>}
        {!hasSubmitted && (
          <button className="primary-button" type="button" onClick={onEnterUpload}>
            提交报告
          </button>
        )}
        {isAnalyzed && activeSessionId && (
          <>
            <Link className="primary-button" href={`/student/qa/${activeSessionId}`}>
              进入问答界面
            </Link>
            <button className="secondary-button" type="button" onClick={onEnterUpload}>
              重新上传
            </button>
          </>
        )}
        {isSummarized && (
          <>
            <button
              className={detailMode === "records" ? "secondary-button active" : "secondary-button"}
              type="button"
              onClick={() => onOpenReportMode("records")}
            >
              查看问答结果
            </button>
            <button
              className={detailMode === "summary" ? "secondary-button active" : "secondary-button"}
              type="button"
              onClick={() => onOpenReportMode("summary")}
            >
              查看总结报告
            </button>
            <button className="secondary-button" type="button" onClick={onEnterUpload}>
              重新上传
            </button>
          </>
        )}
        {activeSubmission?.status === "failed" && (
          <button className="primary-button" type="button" onClick={onEnterUpload}>
            重新上传
          </button>
        )}
      </div>

      {isPendingOrProcessing && detailMode === "overview" && (
        <div className="message">报告正在上传或分析中，完成后会出现后续操作按钮。</div>
      )}

      {canUpload && (
        <form className="form student-upload-form" onSubmit={onSubmit}>
          <input name="student_name" type="hidden" value={currentUser.display_name} />
          <label>本次提交与评分范围
            <select name="stage_id" defaultValue="all">
              <option value="all">全部实验与课设阶段（联合提交）</option>
              {selectedCourse.assignment_spec?.stages?.map(stage => <option key={stage.id} value={stage.id}>{stage.name}</option>)}
            </select>
            <small>阶段提交只评价本阶段；综合评分请选择全部阶段，并提交各阶段源码、测试和报告。</small>
          </label>
          <label className="dropzone">
            <input
              name="submission_files"
              type="file"
              multiple
              required
              onChange={(event) =>
                onFileNameChange(Array.from(event.currentTarget.files || []).map(file => file.name).join("、") || "选择源码、报告或ZIP项目包")
              }
            />
            <strong>{fileName}</strong>
            <small>可多选源代码（C/C++、.l、.y、.g4、Java、Python、LLVM等）、PDF、Word、文本或ZIP。单文件20MB，展开合计40MB、200个文件。旧版.doc需本机转换器。</small>
          </label>
          <button className="primary-button" type="submit" disabled={isAnalyzing || submitting}>
            {isAnalyzing || submitting ? "正在联合分析源码与文档..." : "上传并分析实验材料"}
          </button>
        </form>
      )}

      {detailMode === "records" && (
        <div className="report-section">
          <div className="panel-head">
            <h3>问答历史记录</h3>
          </div>
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

      {detailMode === "summary" && (
        <div className="report-section">
          <div className="panel-head">
            <h3>问答总结报告</h3>
          </div>
          <FinalScore result={activeResult} />
          {activeResult?.voice_qa_summary ? (
            <p className="qa-summary">{activeResult.voice_qa_summary}</p>
          ) : (
            <div className="empty">暂无总结报告。</div>
          )}
        </div>
      )}
    </div>
  );
}

function studentSubmissionStatus(submission: StudentCourse["latest_submission"]) {
  if (!submission) return "未提交报告";
  if (submission.final_assessment_status === "insufficient_qa") return "答辩尚不完整，请补充问答";
  if (typeof submission.final_score === "number") return `已完成评分：${submission.final_score}/100`;
  if (submission.voice_qa_summary_ready) return "已完成问答总结";
  const map: Record<string, string> = {
    pending: "等待分析",
    processing: "分析中",
    completed: "报告已分析",
    failed: "失败"
  };
  return map[submission.status] || submission.status;
}
