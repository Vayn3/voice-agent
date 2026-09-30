import type {
  AnalysisResponse,
  ConfigCheck,
  CourseDetail,
  CourseSummary,
  QARecord,
  SystemConfig,
  StudentCourse,
  User,
  UserRole,
  VoiceQASummary
} from "@/types/api";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";

export function voiceQAWebSocketUrl(sessionId: string): string {
  const base = API_BASE.replace(/^http/, "ws");
  return `${base}/api/sessions/${sessionId}/voice-qa`;
}

async function parseResponse<T>(response: Response): Promise<T> {
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(payload?.detail || payload?.message || "请求失败");
  }
  return payload as T;
}

export async function getConfig(): Promise<SystemConfig> {
  const response = await fetch(`${API_BASE}/api/config`, { cache: "no-store" });
  return parseResponse<SystemConfig>(response);
}

export async function login(input: {
  username: string;
  password: string;
}): Promise<User> {
  const response = await fetch(`${API_BASE}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input)
  });
  return parseResponse<User>(response);
}

export async function register(input: {
  username: string;
  password: string;
  display_name: string;
}): Promise<User> {
  const response = await fetch(`${API_BASE}/api/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input)
  });
  return parseResponse<User>(response);
}

export async function listUsers(): Promise<User[]> {
  const response = await fetch(`${API_BASE}/api/users`, { cache: "no-store" });
  return parseResponse<User[]>(response);
}

export async function updateUserRole(userId: string, role: UserRole): Promise<User> {
  const response = await fetch(`${API_BASE}/api/users/${userId}/role`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ role })
  });
  return parseResponse<User>(response);
}

export async function saveConfig(input: {
  dashscope_api_key: string;
  dashscope_base_url: string;
  dashscope_text_model: string;
  dashscope_code_model: string;
  volc_realtime_api_key: string;
  volc_realtime_model_version: string;
}): Promise<SystemConfig> {
  const response = await fetch(`${API_BASE}/api/config`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input)
  });
  return parseResponse<SystemConfig>(response);
}

export async function checkConfig(): Promise<ConfigCheck> {
  const response = await fetch(`${API_BASE}/api/config/check`, {
    cache: "no-store"
  });
  return parseResponse<ConfigCheck>(response);
}

export async function createSession(formData: FormData): Promise<AnalysisResponse> {
  const response = await fetch(`${API_BASE}/api/sessions`, {
    method: "POST",
    body: formData
  });
  return parseResponse<AnalysisResponse>(response);
}

export async function getSession(sessionId: string): Promise<AnalysisResponse> {
  const response = await fetch(`${API_BASE}/api/sessions/${sessionId}`, {
    cache: "no-store"
  });
  return parseResponse<AnalysisResponse>(response);
}

export async function listCourses(teacherUserId?: string | null): Promise<CourseSummary[]> {
  const search = teacherUserId ? `?teacher_user_id=${encodeURIComponent(teacherUserId)}` : "";
  const response = await fetch(`${API_BASE}/api/courses${search}`, { cache: "no-store" });
  return parseResponse<CourseSummary[]>(response);
}

export async function createCourse(input: {
  name: string;
  teacher_name: string;
  teacher_user_id?: string | null;
  assignment_name: string;
  assignment_requirements: string;
}): Promise<CourseSummary> {
  const response = await fetch(`${API_BASE}/api/courses`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input)
  });
  return parseResponse<CourseSummary>(response);
}

export async function getCourse(courseId: string): Promise<CourseDetail> {
  const response = await fetch(`${API_BASE}/api/courses/${courseId}`, {
    cache: "no-store"
  });
  return parseResponse<CourseDetail>(response);
}

export async function createCourseSession(
  courseId: string,
  formData: FormData
): Promise<AnalysisResponse> {
  const response = await fetch(`${API_BASE}/api/courses/${courseId}/sessions`, {
    method: "POST",
    body: formData
  });
  return parseResponse<AnalysisResponse>(response);
}

export async function listQARecords(sessionId: string): Promise<QARecord[]> {
  const response = await fetch(`${API_BASE}/api/sessions/${sessionId}/qa-records`, {
    cache: "no-store"
  });
  return parseResponse<QARecord[]>(response);
}

export async function createQARecord(
  sessionId: string,
  input: { question: string; answer: string; created_by_user_id?: string | null }
): Promise<QARecord> {
  const response = await fetch(`${API_BASE}/api/sessions/${sessionId}/qa-records`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input)
  });
  return parseResponse<QARecord>(response);
}

export async function enrollCourse(
  courseId: string,
  input: { student_user_id: string; student_name: string }
): Promise<CourseSummary> {
  const response = await fetch(`${API_BASE}/api/courses/${courseId}/enroll`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input)
  });
  return parseResponse<CourseSummary>(response);
}

export async function listStudentCourses(studentUserId: string): Promise<StudentCourse[]> {
  const response = await fetch(`${API_BASE}/api/students/${studentUserId}/courses`, {
    cache: "no-store"
  });
  return parseResponse<StudentCourse[]>(response);
}

export async function createVoiceQASummary(sessionId: string): Promise<VoiceQASummary> {
  const response = await fetch(`${API_BASE}/api/sessions/${sessionId}/voice-qa-summary`, {
    method: "POST"
  });
  return parseResponse<VoiceQASummary>(response);
}
