"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { login } from "@/lib/api";
import { saveCurrentUser } from "@/lib/auth";

export default function LoginPage() {
  const router = useRouter();
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setLoading(true);
    setMessage("");
    try {
      const user = await login({
        username: String(form.get("username") || ""),
        password: String(form.get("password") || "")
      });
      saveCurrentUser(user);
      if (user.role === "admin") {
        router.push("/config");
      } else {
        router.push(user.role === "student" ? "/student" : "/teacher");
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "登录失败");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="workspace config-card">
      <div className="page-head">
        <div>
          <p className="eyebrow">用户校验</p>
          <h1>登录 Voice TA</h1>
        </div>
        <div className="badge">MySQL 用户体系</div>
      </div>

      {message && <p className="message error">{message}</p>}

      <form className="form" onSubmit={handleSubmit}>
        <label>
          用户名
          <input name="username" placeholder="teacher / student / admin" required />
        </label>
        <label>
          密码
          <input name="password" type="password" placeholder="请输入密码" required />
        </label>
        <button className="primary-button" type="submit" disabled={loading}>
          {loading ? "登录中..." : "登录"}
        </button>
      </form>

      <div className="brief-list">
        <div className="brief-item">
          <strong>默认账号</strong>
          <p className="hint">admin/admin123，teacher/teacher123，student/student123</p>
        </div>
      </div>
    </section>
  );
}
