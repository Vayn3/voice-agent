import type {
  AnalysisResponse,
  ConfigCheck,
  CourseDetail,
  CourseSummary,
  QARecord,
  SystemConfig,
  User
} from "@/types/api";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";

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

export async function saveConfig(input: {
  dashscope_api_key: string;
  dashscope_base_url: string;
  dashscope_text_model: string;
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

export async function listCourses(): Promise<CourseSummary[]> {
  const response = await fetch(`${API_BASE}/api/courses`, { cache: "no-store" });
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
