"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { clearCurrentUser, readCurrentUser } from "@/lib/auth";
import type { User } from "@/types/api";

export function ShellNav() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);

  useEffect(() => {
    const refresh = () => setUser(readCurrentUser());
    refresh();
    window.addEventListener("voice-ta-auth-change", refresh);
    window.addEventListener("storage", refresh);
    return () => {
      window.removeEventListener("voice-ta-auth-change", refresh);
      window.removeEventListener("storage", refresh);
    };
  }, []);

  function handleLogout() {
    clearCurrentUser();
    router.replace("/login");
  }

  return (
    <header className="topbar">
      <Link href="/login" className="brand">
        <span>Voice TA</span>
        <strong>课程报告智能助教</strong>
      </Link>
      <nav>
        {user ? (
          <button className="nav-button" type="button" onClick={handleLogout}>
            注销
          </button>
        ) : (
          <>
            <Link href="/register">注册</Link>
            <Link href="/login">登录</Link>
          </>
        )}
      </nav>
    </header>
  );
}
