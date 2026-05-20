export type AnalysisStatus = "pending" | "processing" | "completed" | "failed";
export type UserRole = "admin" | "teacher" | "student";

export type User = {
  id: string;
  username: string;
  display_name: string;
  role: UserRole;
};

export type SessionSummary = {
  id: string;
  course_id?: string | null;
  student_user_id?: string | null;
  student_name: string;
  course_name: string;
  assignment_name: string;
  assignment_requirements: string;
  original_filename: string;
  created_at: string;
  status: AnalysisStatus;
  error?: string | null;
  voice_qa_summary_ready: boolean;
};

export type AnalysisResponse = {
  session: SessionSummary;
  result?: AnalysisResult | null;
};

export type AnalysisResult = {
  report_brief?: {
    topic?: string;
    core_claims?: string[];
    methods_or_evidence?: string[];
  };
  question_plan?: QuestionPlanItem[];
  voice_qa_prompt?: string;
  voice_qa_summary?: string;
  teacher_attention?: string[];
  coverage_threshold?: Record<string, unknown>;
  _meta?: Record<string, unknown>;
};

export type QuestionPlanItem = {
  id?: string;
  priority?: string;
  focus?: string;
  question?: string;
  follow_up_when_insufficient?: string[];
  sufficient_answer_criteria?: string[];
  evidence_hint?: string;
};

export type SystemConfig = {
  configured: boolean;
  dashscope_api_key_masked: string;
  dashscope_base_url: string;
  dashscope_text_model: string;
  realtime_configured: boolean;
  volc_realtime_app_id_masked: string;
  volc_realtime_access_key_masked: string;
  volc_realtime_app_key_masked: string;
};

export type ConfigCheck = {
  configured: boolean;
  message: string;
};

export type CourseSummary = {
  id: string;
  name: string;
  teacher_name: string;
  teacher_user_id?: string | null;
  assignment_name: string;
  assignment_requirements: string;
  created_at: string;
  submission_count: number;
  student_count: number;
  analyzed_count: number;
  summarized_count: number;
};

export type CourseDetail = {
  course: CourseSummary;
  submissions: SessionSummary[];
};

export type StudentCourse = {
  course: CourseSummary;
  latest_submission?: SessionSummary | null;
};

export type QARecord = {
  id: string;
  report_id: string;
  question: string;
  answer: string;
  created_by_user_id?: string | null;
  created_at: string;
};

export type VoiceQASummary = {
  session: SessionSummary;
  qa_records: QARecord[];
  summary: string;
};
