import { apiFetch } from "./client";
import { Project, ProjectPaper } from "../types";
import { BackendPaper } from "./papers";

export interface CitationGraphNode {
  id: string;
  label: string;
  year?: number | null;
  group: number;
}

export interface CitationGraphEdge {
  source: string;
  target: string;
}

export interface CitationGraphData {
  nodes: CitationGraphNode[];
  edges: CitationGraphEdge[];
}

export interface ConceptGraphNode {
  id: string;
  label: string;
  type: string;
}

export interface ConceptGraphEdge {
  source: string;
  target: string;
  label: string;
}

export interface ConceptGraphData {
  nodes: ConceptGraphNode[];
  edges: ConceptGraphEdge[];
}

export async function getProjects(): Promise<Project[]> {
  return apiFetch<Project[]>("/projects");
}

export async function createProject(data: { name: string; description?: string; color?: string }): Promise<Project> {
  return apiFetch<Project>("/projects", {
    method: "POST",
    body: JSON.stringify(data)
  });
}

export async function getProjectById(id: string): Promise<Project> {
  return apiFetch<Project>(`/projects/${id}`);
}

export async function getProjectPapers(id: string): Promise<BackendPaper[]> {
  return apiFetch<BackendPaper[]>(`/projects/${id}/papers`);
}

export async function getProjectStats(id: string): Promise<{ total_papers: number, total_notes: number }> {
  return apiFetch<{ total_papers: number, total_notes: number }>(`/projects/${id}/stats`);
}

export async function updateProject(id: string, data: Partial<Project>): Promise<Project> {
  return apiFetch<Project>(`/projects/${id}`, {
    method: "PATCH",
    body: JSON.stringify(data)
  });
}

export async function deleteProject(id: string): Promise<void> {
  return apiFetch<void>(`/projects/${id}`, {
    method: "DELETE"
  });
}

export async function addPaperToProject(projectId: string, paperId: string, data: Partial<ProjectPaper>): Promise<ProjectPaper> {
  return apiFetch<ProjectPaper>(`/projects/${projectId}/papers`, {
    method: "POST",
    body: JSON.stringify({ paper_id: paperId, ...data })
  });
}

export async function updateProjectPaper(projectId: string, paperId: string, data: Partial<ProjectPaper>): Promise<ProjectPaper> {
  return apiFetch<ProjectPaper>(`/projects/${projectId}/papers/${paperId}`, {
    method: "PATCH",
    body: JSON.stringify(data)
  });
}

export async function removePaperFromProject(projectId: string, paperId: string): Promise<void> {
  return apiFetch<void>(`/projects/${projectId}/papers/${paperId}`, {
    method: "DELETE"
  });
}

import { SavedArtifact } from "../types";

export async function getSavedArtifacts(projectId: string): Promise<SavedArtifact[]> {
  return apiFetch<SavedArtifact[]>(`/projects/${projectId}/artifacts`);
}

export async function createSavedArtifact(projectId: string, data: Partial<SavedArtifact>): Promise<SavedArtifact> {
  return apiFetch<SavedArtifact>(`/projects/${projectId}/artifacts`, {
    method: "POST",
    body: JSON.stringify({
      artifact_type: data.type,
      title: data.title,
      content: data.content,
      paper_id: data.paperId || null,
      cited_paper_ids: data.citedPaperIds || []
    })
  });
}

export async function deleteSavedArtifact(projectId: string, artifactId: string): Promise<void> {
  return apiFetch<void>(`/projects/${projectId}/artifacts/${artifactId}`, {
    method: "DELETE"
  });
}

export async function getProjectCitationGraph(projectId: string): Promise<CitationGraphData> {
  return apiFetch<CitationGraphData>(`/projects/${projectId}/citation-graph`);
}

export async function getProjectConceptGraph(projectId: string): Promise<ConceptGraphData> {
  return apiFetch<ConceptGraphData>(`/projects/${projectId}/concept-graph`);
}
