"use client";

import Link from "next/link";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { checkConfig, createCourseSession, getSession, listCourses } from "@/lib/api";
import type { AnalysisResponse, CourseSummary } from "@/types/api";

export default function StudentPage() {
  const [courses, setCourses] = useState<CourseSummary[]>([]);
  const [selectedCourseId, setSelectedCourseId] = useState("");
  const [fileName, setFileName] = useState("选择或拖入课程报告文件");
  const [session, setSession] = useState<AnalysisResponse | null>(null);
  const [status, setStatus] = useState("等待提交");
  const [message, setMessage] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const selectedCourse = useMemo(
    () => courses.find((course) => course.id === selectedCourseId),
    [courses, selectedCourseId]
  );
  const result = session?.result;

  useEffect(() => {
    listCourses()
      .then((payload) => {
        setCourses(payload);
        setSelectedCourseId(payload[0]?.id || "");
      })
      .catch(() => setMessage("后端服务未连接，请确认 FastAPI 已启动。"));
  }, []);

  useEffect(() => {
    if (!session?.session.id) return;
    if (["completed", "failed"].includes(session.session.status)) return;

    const timer = window.setInterval(async () => {
      try {
        const payload = await getSession(session.session.id);
        setSession(payload);
        if (payload.session.status === "completed") {
          setStatus("分析完成，可以进入问答");
        } else if (payload.session.status === "failed") {
          setStatus(`分析失败：${payload.session.error || "未知错误"}`);
        } else {
          setStatus(payload.session.status === "processing" ? "正在生成问题" : "等待分析");
        }
      } catch (error) {
        setStatus(error instanceof Error ? error.message : "获取分析状态失败");
      }
    }, 1800);

    return () => window.clearInterval(timer);
  }, [session?.session.id, session?.session.status]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage("");

    if (!selectedCourseId) {
      setMessage("请先选择一个课程。");
      return;
    }

    const checked = await checkConfig();
    if (!checked.configured) {
      setMessage(checked.message);
      setStatus("系统配置未完成");
      return;
    }

    setSubmitting(true);
    setStatus("正在上传报告");
    try {
      const formData = new FormData(event.currentTarget);
      const payload = await createCourseSession(selectedCourseId, formData);
      setSession(payload);
      setStatus("已提交，等待分析");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "提交失败");
      setStatus("提交失败");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <>
      <section className="workspace">
        <div className="page-head">
          <div>
            <p className="eyebrow">学生端</p>
            <h1>加入课程并提交报告</h1>
          </div>
          <div className="badge">{courses.length} 门可加入课程</div>
        </div>

        {message && (
          <p className="message error">
            {message.includes("DashScope") ? <Link href="/config">{message}</Link> : message}
          </p>
        )}

        {!courses.length && (
          <p className="message">当前还没有课程，请老师先在老师端创建课程。</p>
        )}

        <form className="form" onSubmit={handleSubmit}>
          <div className="grid two">
            <label>
              选择课程
              <select
                value={selectedCourseId}
                onChange={(event) => setSelectedCourseId(event.currentTarget.value)}
                required
              >
                {courses.map((course) => (
                  <option key={course.id} value={course.id}>
                    {course.name} / {course.assignment_name} / {course.id}
                  </option>
                ))}
              </select>
            </label>
            <label>
              学生姓名
              <input name="student_name" placeholder="例如：张三" required />
            </label>
          </div>

          {selectedCourse && (
            <div className="brief-item">
              <strong>{selectedCourse.name}</strong>
              <p className="hint">课程码：{selectedCourse.id}</p>
              <p><strong>作业：</strong>{selectedCourse.assignment_name}</p>
              <p><strong>要求：</strong>{selectedCourse.assignment_requirements}</p>
            </div>
          )}

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

          <button className="primary-button" type="submit" disabled={submitting || !courses.length}>
            {submitting ? "提交中..." : "提交报告并生成问题"}
          </button>
        </form>

        <section className="status-row">
          <div>
            <p className="label">当前状态</p>
            <strong>{status}</strong>
          </div>
          <div>
            <p className="label">会话 ID</p>
            <code>{session?.session.id || "-"}</code>
          </div>
        </section>
      </section>

      <section className="result-layout">
        <article className="panel">
          <div className="panel-head">
            <h2>报告概览</h2>
          </div>
          {result?.report_brief ? (
            <div className="brief-list">
              <div className="brief-item">
                <strong>主题：</strong>{result.report_brief.topic || "未明确"}
              </div>
              <div className="brief-item">
                <strong>核心结论：</strong>
                <ul>{(result.report_brief.core_claims || ["未明确"]).map((item) => <li key={item}>{item}</li>)}</ul>
              </div>
            </div>
          ) : (
            <div className="empty">提交后这里会显示报告分析概览。</div>
          )}
        </article>

        <article className="panel">
          <div className="panel-head">
            <h2>语音问答 Prompt</h2>
          </div>
          <pre className="prompt-box">{result?.voice_qa_prompt || "等待生成。"}</pre>
        </article>

        <article className="panel full">
          <div className="panel-head">
            <h2>需要回答的问题</h2>
          </div>
          {result?.question_plan?.length ? (
            <div className="question-list">
              {result.question_plan.map((item, index) => (
                <div className="question-item" key={item.id || index}>
                  <header>
                    <strong>{item.focus || item.id || "追问点"}</strong>
                    <span className="priority">{item.priority || "medium"}</span>
                  </header>
                  <p>{item.question}</p>
                  <p><strong>回答充分标准：</strong></p>
                  <ul>
                    {(item.sufficient_answer_criteria || ["未明确"]).map((text) => (
                      <li key={text}>{text}</li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          ) : (
            <div className="empty">问题计划生成后会显示在这里。</div>
          )}
        </article>
      </section>
    </>
  );
}
