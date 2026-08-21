import { apiFetch } from "./client";
import { Paper, ProjectPaper } from "../types";

export interface OpenAlexSearchResult extends Partial<Paper> {
  openalex_id?: string;
}

export async function searchPapersExternal(query: string, limit: number = 20): Promise<OpenAlexSearchResult[]> {
  return apiFetch<OpenAlexSearchResult[]>(`/search?q=${encodeURIComponent(query)}&limit=${limit}`);
}

export async function ingestPaper(openalexId: string, projectId?: string): Promise<{ paper: Paper, project_paper?: ProjectPaper }> {
  return apiFetch<{ paper: Paper, project_paper?: ProjectPaper }>("/search/ingest", {
    method: "POST",
    body: JSON.stringify({ openalex_id: openalexId, project_id: projectId })
  });
}
