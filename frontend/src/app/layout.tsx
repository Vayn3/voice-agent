import type { Metadata } from "next";
import { ShellNav } from "./ShellNav";
import "./globals.css";

export const metadata: Metadata = {
  title: "课程报告智能助教",
  description: "上传课程报告并生成语音问答提问计划和总结"
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
          <ShellNav />
          {children}
        </div>
      </body>
    </html>
  );
}
