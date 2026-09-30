"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { RequireRole } from "@/app/RequireRole";
import { FinalScore } from "@/app/LabAssessment";
import { getSession } from "@/lib/api";
import type { AnalysisResponse } from "@/types/api";
import { VoiceQAConsole } from "../../VoiceQAConsole";

export default function StudentQAPage() {
  return (
    <RequireRole roles={["student"]}>
      {() => <StudentQAWorkspace />}
    </RequireRole>
  );
}

function StudentQAWorkspace() {
  const params = useParams<{ sessionId: string }>();
  const [session, setSession] = useState<AnalysisResponse | null>(null);
  const [message, setMessage] = useState("");

  async function refreshSession() {
    const payload = await getSession(params.sessionId);
    setSession(payload);
  }

  useEffect(() => {
    refreshSession().catch((error) =>
      setMessage(error instanceof Error ? error.message : "无法加载问答会话")
    );
  }, [params.sessionId]);

  return (
    <section className="workspace">
      <div className="page-head">
        <div>
          <p className="eyebrow">学生端</p>
          <h1>实时语音问答</h1>
        </div>
        <Link className="secondary-button" href="/student">返回我的课程</Link>
      </div>

      {message && <p className="message error">{message}</p>}
      {!session && !message && <p className="hint">正在加载问答会话...</p>}
      {session?.session.status !== "completed" && session && (
        <p className="message">报告还未分析完成，请稍后再进入问答。</p>
      )}
      {session?.session.status === "completed" && (
        <>
        <VoiceQAConsole
          sessionId={session.session.id}
          summary={session.result?.voice_qa_summary || ""}
          onSummary={refreshSession}
        />
        <FinalScore result={session.result} />
        </>
      )}
    </section>
  );
}
