"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { register } from "@/lib/api";
import { saveCurrentUser } from "@/lib/auth";

export default function RegisterPage() {
  const router = useRouter();
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const password = String(form.get("password") || "");
    const confirmPassword = String(form.get("confirm_password") || "");
    if (password !== confirmPassword) {
      setMessage("两次输入的密码不一致");
      return;
    }

    setLoading(true);
    setMessage("");
    try {
      const user = await register({
        username: String(form.get("username") || ""),
        password,
        display_name: String(form.get("display_name") || "")
      });
      saveCurrentUser(user);
      router.push("/student");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "注册失败");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="workspace config-card">
      <div className="page-head">
        <div>
          <p className="eyebrow">用户注册</p>
          <h1>注册 Voice TA</h1>
        </div>
        <div className="badge">默认学生权限</div>
      </div>

      {message && <p className="message error">{message}</p>}

      <form className="form" onSubmit={handleSubmit}>
        <label>
          用户名
          <input name="username" placeholder="至少 3 个字符" required />
        </label>
        <label>
          显示名称
          <input name="display_name" placeholder="可选，默认使用用户名" />
        </label>
        <label>
          密码
          <input name="password" type="password" placeholder="至少 6 个字符" required />
        </label>
        <label>
          确认密码
          <input name="confirm_password" type="password" required />
        </label>
        <button className="primary-button" type="submit" disabled={loading}>
          {loading ? "注册中..." : "注册"}
        </button>
      </form>

      <p className="hint">
        已有账号？<Link href="/login">去登录</Link>
      </p>
    </section>
  );
}
