import { apiFetch } from "./client";
import { ProjectPaper } from "../types";
import { BackendPaper } from "./papers";

export type SearchSource = "openalex" | "arxiv" | "semantic_scholar" | "all";

/**
 * Shape returned by GET /search.
 * Normalized from whichever source was queried — safe to pass to ingestPaper().
 */
export interface OpenAlexSearchResult {
  // Source routing IDs — exactly one will be non-null
  openalex_id?: string | null;
  arxiv_id?: string | null;
  semantic_scholar_id?: string | null;
  // Paper metadata
  doi?: string | null;
  title?: string;
  abstract?: string | null;
  publication_year?: number | null;
  venue?: string | null;
  pdf_url?: string | null;
  source?: string | null;
  citation_count?: number | null;
  reference_count?: number | null;
}

export async function searchPapersExternal(
  query: string,
  limit: number = 20,
  page: number = 1,
  source: SearchSource = "openalex",
): Promise<OpenAlexSearchResult[]> {
  return apiFetch<OpenAlexSearchResult[]>(
    `/search?q=${encodeURIComponent(query)}&limit=${limit}&page=${page}&source=${source}`,
  );
}

export async function ingestPaper(
  ids: {
    openalex_id?: string;
    arxiv_id?: string;
    semantic_scholar_id?: string;
  },
  projectId?: string,
): Promise<{ paper: BackendPaper; project_paper?: ProjectPaper }> {
  return apiFetch<{ paper: BackendPaper; project_paper?: ProjectPaper }>(
    "/search/ingest",
    {
      method: "POST",
      body: JSON.stringify({ ...ids, project_id: projectId }),
    },
  );
}
