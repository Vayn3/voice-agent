import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "课程报告智能助教",
  description: "上传课程报告并生成语音问答提问 Prompt"
};

export default function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body>
        <div className="app-shell">
          <header className="topbar">
            <Link href="/" className="brand">
              <span>Voice TA</span>
              <strong>课程报告智能助教</strong>
            </Link>
            <nav>
              <Link href="/">入口</Link>
              <Link href="/login">登录</Link>
              <Link href="/teacher">老师端</Link>
              <Link href="/student">学生端</Link>
              <Link href="/config">系统配置</Link>
            </nav>
          </header>
          {children}
        </div>
      </body>
    </html>
  );
}
