import { apiFetch } from "./client";

// ── Types ─────────────────────────────────────────────────────────────────────

export interface ChatCitation {
  paper_id: string;
  title: string;
  year?: number | null;
  reason: string;
}

export interface ProjectChatResponse {
  answer: string;
  citations: ChatCitation[];
  grounded: boolean;
  model?: string | null;
  session_id?: string | null;
}

export interface LitReviewTheme {
  title: string;
  summary: string;
  paper_ids: string[];
}

export interface LitReviewReference {
  paper_id: string;
  title: string;
  year?: number | null;
  authors?: string | null;
}

export interface LiteratureReviewContent {
  title: string;
  overview: string;
  themes: LitReviewTheme[];
  methodological_trends: string[];
  datasets: string[];
  models: string[];
  key_findings: string[];
  contradictions: string[];
  research_gaps: string[];
  future_directions: string[];
  references: LitReviewReference[];
}

export interface LiteratureReviewResponse {
  id?: string | null;
  project_id: string;
  content: LiteratureReviewContent;
  paper_count: number;
  is_stale: boolean;
  created_at?: string | null;
  model?: string | null;
}

// ── Project Chat ──────────────────────────────────────────────────────────────

export async function projectChat(
  projectId: string,
  message: string,
  sessionId?: string | null,
): Promise<ProjectChatResponse> {
  return apiFetch<ProjectChatResponse>(`/projects/${projectId}/ai/chat`, {
    method: "POST",
    body: JSON.stringify({
      message,
      session_id: sessionId ?? null,
    }),
  });
}

// ── Literature Review ─────────────────────────────────────────────────────────

export async function generateLitReview(
  projectId: string,
): Promise<LiteratureReviewResponse> {
  return apiFetch<LiteratureReviewResponse>(
    `/projects/${projectId}/ai/review/generate`,
    { method: "POST" },
  );
}

export async function regenerateLitReview(
  projectId: string,
): Promise<LiteratureReviewResponse> {
  return apiFetch<LiteratureReviewResponse>(
    `/projects/${projectId}/ai/review/regenerate`,
    { method: "POST" },
  );
}

export async function getLitReview(
  projectId: string,
): Promise<LiteratureReviewResponse | null> {
  try {
    return await apiFetch<LiteratureReviewResponse>(
      `/projects/${projectId}/ai/review`,
    );
  } catch (err: any) {
    if (err?.status === 404) return null;
    throw err;
  }
}

export async function deleteLitReview(projectId: string): Promise<void> {
  await apiFetch(`/projects/${projectId}/ai/review`, { method: "DELETE" });
}
