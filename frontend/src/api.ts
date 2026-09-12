import axios from "axios";
const defaultApiUrl = `${window.location.protocol}//${window.location.hostname}:8000`;
export const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || defaultApiUrl,
});
const savedToken = localStorage.getItem("loanlens_access_token");
if (savedToken)
  api.defaults.headers.common.Authorization = `Bearer ${savedToken}`;
export const setAccessToken = (token: string | null) => {
  if (token) {
    localStorage.setItem("loanlens_access_token", token);
    api.defaults.headers.common.Authorization = `Bearer ${token}`;
  } else {
    localStorage.removeItem("loanlens_access_token");
    delete api.defaults.headers.common.Authorization;
  }
};
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (
      error.response?.status === 401 &&
      window.location.pathname !== "/login"
    ) {
      setAccessToken(null);
      window.location.assign("/login");
    }
    return Promise.reject(error);
  },
);
export type Application = {
  id: string;
  applicant_name: string;
  email: string;
  loan_type: string;
  loan_amount: number;
  income: number;
  credit_score: number;
  dti: number;
  employment_years: number;
  existing_loans: number;
  comments: string;
  status: "APPROVE" | "REVIEW" | "REJECT";
  risk_score: number;
  fraud_score: number;
  sentiment: string;
  sentiment_confidence: number;
  explanation: string;
  ai_summary: string;
  source_file: string;
  processing_log: string[];
  created_at: string;
};
export type ApplicationPage = {
  items: Application[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
};
export type AgentRun = {
  run_id: string;
  application_id: string;
  query: string;
  intent?: string;
  status?: string;
  answer: string;
  decision: {
    recommendation: string;
    risk_score: number;
    fraud_score: number;
    human_review_required: boolean;
  };
  fraud_assessment: {
    score: number;
    risk_level: string;
    signals: Array<{
      code: string;
      severity: string;
      description: string;
      evidence_ids: string[];
    }>;
  };
  verification: {
    verified: boolean;
    groundedness: number;
    citation_coverage: number;
  };
  retrieved_evidence: Array<{
    id: string;
    source: string;
    document_type: string;
    text: string;
    score: number;
  }>;
  trace: Array<{
    agent: string;
    status: string;
    output: Record<string, unknown>;
  }>;
  created_at?: string;
};
