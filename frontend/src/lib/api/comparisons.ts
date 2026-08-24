import { apiFetch } from "./client";

export interface ComparisonDimension {
  name: string;
  values: string[];
}

export interface ComparisonContent {
  dimensions: ComparisonDimension[];
  overall_summary: string;
  key_differences: string[];
  commonalities: string[];
  research_takeaway: string;
}

export interface Comparison {
  id: string;
  title: string;
  content: ComparisonContent;
  project_id?: string;
  paper_ids: string[];
  created_at: string;
}

export async function generateComparison(title: string, paperIds: string[], projectId?: string): Promise<Comparison> {
  return apiFetch<Comparison>("/comparisons/generate", {
    method: "POST",
    body: JSON.stringify({
      title,
      paper_ids: paperIds,
      project_id: projectId
    }),
  });
}

export async function getComparisons(projectId?: string): Promise<Comparison[]> {
  const params = new URLSearchParams();
  if (projectId) params.append("project_id", projectId);
  
  const query = params.toString();
  return apiFetch<Comparison[]>(`/comparisons${query ? `?${query}` : ""}`);
}

export async function getComparison(id: string): Promise<Comparison> {
  return apiFetch<Comparison>(`/comparisons/${id}`);
}
