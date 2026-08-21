import { apiFetch } from "./client";

export interface NoteResponse {
  id: string;
  project_paper_id: string;
  title?: string;
  content: string;
  created_at: string;
  updated_at: string;
}

export interface HighlightResponse {
  id: string;
  project_paper_id: string;
  page?: number;
  selected_text: string;
  ai_note?: string;
  created_at: string;
}

export interface ReadingProgressResponse {
  id: string;
  project_paper_id: string;
  progress_percent: number;
  last_page?: number;
  started_at?: string;
  last_opened?: string;
  completed_at?: string;
}

export interface ProjectPaperReadingData {
  project_paper_id: string;
  status?: string;
  favorite: boolean;
  priority?: number;
  added_at: string;
  notes: NoteResponse[];
  highlights: HighlightResponse[];
  reading_progress?: ReadingProgressResponse;
}

// ── Reading Data ──

export async function getReadingData(projectId: string, paperId: string): Promise<ProjectPaperReadingData> {
  return apiFetch<ProjectPaperReadingData>(`/projects/${projectId}/papers/${paperId}/reading-data`);
}

// ── Notes ──

export async function createNote(
  projectId: string,
  paperId: string,
  content: string,
  title?: string,
): Promise<NoteResponse> {
  return apiFetch<NoteResponse>(`/projects/${projectId}/papers/${paperId}/notes`, {
    method: "POST",
    body: JSON.stringify({ content, title }),
  });
}

export async function updateNote(
  projectId: string,
  paperId: string,
  noteId: string,
  content: string,
): Promise<NoteResponse> {
  return apiFetch<NoteResponse>(`/projects/${projectId}/papers/${paperId}/notes/${noteId}`, {
    method: "PATCH",
    body: JSON.stringify({ content }),
  });
}

export async function deleteNote(projectId: string, paperId: string, noteId: string): Promise<void> {
  await apiFetch(`/projects/${projectId}/papers/${paperId}/notes/${noteId}`, {
    method: "DELETE",
  });
}

// ── Highlights ──

export async function createHighlight(
  projectId: string,
  paperId: string,
  selected_text: string,
  ai_note?: string,
  page?: number,
): Promise<HighlightResponse> {
  return apiFetch<HighlightResponse>(`/projects/${projectId}/papers/${paperId}/highlights`, {
    method: "POST",
    body: JSON.stringify({ selected_text, ai_note, page }),
  });
}

export async function deleteHighlight(
  projectId: string,
  paperId: string,
  highlightId: string,
): Promise<void> {
  await apiFetch(`/projects/${projectId}/papers/${paperId}/highlights/${highlightId}`, {
    method: "DELETE",
  });
}

// ── Reading Progress ──

export async function updateReadingProgress(
  projectId: string,
  paperId: string,
  progress_percent: number,
  last_page?: number,
): Promise<ReadingProgressResponse> {
  return apiFetch<ReadingProgressResponse>(`/projects/${projectId}/papers/${paperId}/progress`, {
    method: "PATCH",
    body: JSON.stringify({ progress_percent, last_page }),
  });
}
