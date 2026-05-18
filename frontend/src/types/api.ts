export type AnalysisStatus = "pending" | "processing" | "completed" | "failed";

export type SessionSummary = {
  id: string;
  course_id?: string | null;
  student_name: string;
  course_name: string;
  assignment_name: string;
  assignment_requirements: string;
  original_filename: string;
  created_at: string;
  status: AnalysisStatus;
  error?: string | null;
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
};

export type ConfigCheck = {
  configured: boolean;
  message: string;
};

export type CourseSummary = {
  id: string;
  name: string;
  teacher_name: string;
  assignment_name: string;
  assignment_requirements: string;
  created_at: string;
  submission_count: number;
};

export type CourseDetail = {
  course: CourseSummary;
  submissions: SessionSummary[];
};
