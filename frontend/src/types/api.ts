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
  stage_id: string;
  submission_files: { name: string; size: number; kind: string; reason?: string }[];
  created_at: string;
  status: AnalysisStatus;
  error?: string | null;
  voice_qa_summary_ready: boolean;
  final_score?: number | null;
  final_assessment_status?: string | null;
};

export type AnalysisResponse = {
  session: SessionSummary;
  result?: AnalysisResult | null;
};

export type AnalysisResult = {
  stage_assessments?: StageAssessment[];
  preliminary_assignment_score?: number | null;
  scoring_scope?: string;
  file_coverage?: { name: string; status: string; chunks?: number; reason?: string }[];
  final_assessment?: FinalAssessment;
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
  stage_id?: string;
  category?: string;
  required?: boolean;
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
  dashscope_code_model: string;
  realtime_configured: boolean;
  volc_realtime_api_key_masked: string;
  volc_realtime_model_version: string;
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
  assignment_spec: AssignmentSpec;
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
  submissions: SessionSummary[];
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
  assessment: FinalAssessment;
};

export type AssignmentSpec = {
  stages?: { id: string; name: string; tasks: { id: string; title: string; requirement: string; optional: boolean }[]; oral_focus: string[] }[];
  grading_origin?: string;
};

export type StageAssessment = {
  stage_id: string;
  stage_name: string;
  completion_score: number;
  conclusion: string;
  tasks: {
    task_id: string; title: string; optional: boolean; status: string; score: number;
    implementation_details: string; evidence: string[]; strengths: string[]; weaknesses: string[];
    verification_questions: string[];
  }[];
};

export type FinalAssessment = {
  summary: string;
  final_score: number | null;
  status: string;
  scoring_scope: string;
  familiarity: string;
  familiarity_rationale: string;
  strengths: string[];
  weaknesses: string[];
  improvements: string[];
  missing_required_questions: string[];
  grading_note: string;
  assignment: ScoreComponent;
  oral_defense: ScoreComponent;
  reflection: ScoreComponent;
};

export type ScoreComponent = {
  score: number; weight: number; weighted_points: number; rationale: string; evidence: string[];
};
