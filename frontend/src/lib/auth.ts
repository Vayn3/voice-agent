import type { User, UserRole } from "@/types/api";

const STORAGE_KEY = "voice_ta_user";

export function readCurrentUser(): User | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(STORAGE_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as User;
  } catch {
    window.localStorage.removeItem(STORAGE_KEY);
    return null;
  }
}

export function saveCurrentUser(user: User): void {
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(user));
  window.dispatchEvent(new Event("voice-ta-auth-change"));
}

export function clearCurrentUser(): void {
  window.localStorage.removeItem(STORAGE_KEY);
  window.dispatchEvent(new Event("voice-ta-auth-change"));
}

export function hasRole(user: User | null, roles: UserRole[]): boolean {
  return Boolean(user && roles.includes(user.role));
}
