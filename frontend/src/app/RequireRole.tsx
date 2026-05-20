"use client";

import { useRouter } from "next/navigation";
import { ReactNode, useEffect, useState } from "react";
import { hasRole, readCurrentUser } from "@/lib/auth";
import type { User, UserRole } from "@/types/api";

export function RequireRole({
  roles,
  children
}: {
  roles: UserRole[];
  children: (user: User) => ReactNode;
}) {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [checked, setChecked] = useState(false);
  const rolesKey = roles.join(",");

  useEffect(() => {
    const current = readCurrentUser();
    setUser(current);
    setChecked(true);
    if (!hasRole(current, roles)) {
      router.replace("/login");
    }
  }, [router, rolesKey]);

  if (!checked) {
    return <section className="workspace"><p className="hint">正在校验登录状态...</p></section>;
  }

  if (!user || !hasRole(user, roles)) {
    return <section className="workspace"><p className="hint">正在跳转登录页...</p></section>;
  }

  return <>{children(user)}</>;
}
