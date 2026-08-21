import { apiFetch } from "./client";
import { Project, ProjectPaper, Paper } from "../types"; // I might need to adjust imports

export async function getProjects(): Promise<Project[]> {
  return apiFetch<Project[]>("/projects");
}

export async function createProject(data: Partial<Project>): Promise<Project> {
  return apiFetch<Project>("/projects", {
    method: "POST",
    body: JSON.stringify(data)
  });
}

export async function getProjectById(id: string): Promise<Project> {
  return apiFetch<Project>(`/projects/${id}`);
}

export async function getProjectPapers(id: string): Promise<Paper[]> {
  return apiFetch<Paper[]>(`/projects/${id}/papers`);
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
