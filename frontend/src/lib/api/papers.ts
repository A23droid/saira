import { apiFetch } from "./client";

/** Shape returned by the backend PaperResponse schema */
export interface BackendPaper {
  id: string;
  doi?: string | null;
  arxiv_id?: string | null;
  semantic_scholar_id?: string | null;
  title: string;
  abstract?: string | null;
  publication_year?: number | null;
  venue?: string | null;
  pdf_url?: string | null;
  source?: string | null;
  citation_count?: number | null;
  reference_count?: number | null;
  created_at: string;
}

export async function getPapers(skip = 0, limit = 100): Promise<BackendPaper[]> {
  return apiFetch<BackendPaper[]>(`/papers?skip=${skip}&limit=${limit}`);
}

export async function getPaperById(id: string): Promise<BackendPaper> {
  return apiFetch<BackendPaper>(`/papers/${id}`);
}
