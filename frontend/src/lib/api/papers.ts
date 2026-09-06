import { apiFetch } from "./client";
import { Project } from "../types";

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
  indexing_status?: string | null;
  indexing_error?: string | null;
  created_at: string;
}

export interface IndexingStatus {
  paper_id: string;
  indexing_status: string;
  indexing_error?: string | null;
  ask_ai_ready: boolean;
  can_retry: boolean;
}

/** Poll target while a paper's PDF is being fetched/indexed. `retry` restarts a failed run. */
export async function getIndexingStatus(id: string, retry = false): Promise<IndexingStatus> {
  return apiFetch<IndexingStatus>(`/papers/${id}/indexing-status${retry ? "?retry=true" : ""}`);
}

export async function getPapers(skip = 0, limit = 100): Promise<BackendPaper[]> {
  return apiFetch<BackendPaper[]>(`/papers?skip=${skip}&limit=${limit}`);
}

export async function getPaperById(id: string): Promise<BackendPaper> {
  return apiFetch<BackendPaper>(`/papers/${id}`);
}

/** Returns the projects (belonging to current user) that contain this paper. */
export async function getPaperProjects(paperId: string): Promise<Project[]> {
  return apiFetch<Project[]>(`/papers/${paperId}/projects`);
}

export async function deletePaper(id: string): Promise<void> {
  return apiFetch<void>(`/papers/${id}`, { method: "DELETE" });
}

export async function getSimilarPapers(paperId: string): Promise<BackendPaper[]> {
  return apiFetch<BackendPaper[]>(`/papers/${paperId}/similar`);
}

export interface CitationNode {
  id: string;
  title: string;
  year?: number | null;
  doi?: string | null;
  arxiv_id?: string | null;
  semantic_scholar_id?: string | null;
  has_pdf?: boolean | null;
}

export interface GraphCitationsResponse {
  citations: CitationNode[];
  references: CitationNode[];
}

export async function getPaperCitations(paperId: string): Promise<GraphCitationsResponse> {
  return apiFetch<GraphCitationsResponse>(`/papers/${paperId}/citations`);
}

export interface DependencyNode {
  id: string;
  name: string;
  type: string;
  rel_props?: Record<string, any>;
}

/**
 * Concept-graph payload from `GET /papers/{id}/concepts`.
 *
 * The backend returns a node/edge graph, not a flat concept list. This
 * interface previously declared `{ concepts: DependencyNode[] }` while the
 * component read `data.nodes` / `data.edges` — the types and the runtime
 * disagreed, so the compiler could not catch a graph-shape regression here.
 */
export interface ConceptGraphNode {
  id: string;
  label: string;
  /** "Paper" for the root node, "Concept" for extracted concepts. */
  type: string;
}

export interface ConceptGraphEdge {
  source: string;
  target: string;
  /** "HAS_CONCEPT" for paper→concept, or a relation type such as "USES". */
  label: string;
}

export interface GraphConceptsResponse {
  nodes: ConceptGraphNode[];
  edges: ConceptGraphEdge[];
}

export async function getPaperConcepts(paperId: string): Promise<GraphConceptsResponse> {
  return apiFetch<GraphConceptsResponse>(`/papers/${paperId}/concepts`);
}
