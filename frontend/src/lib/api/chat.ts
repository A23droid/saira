import { apiFetch } from "./client";
import { ChatMessage } from "../types";

export interface ChatSession {
  id: string;
  title: string;
  project_id?: string;
  paper_id?: string;
  created_at: string;
  updated_at: string;
  messages?: ChatMessage[];
}

export async function getChatSessions(projectId?: string, paperId?: string): Promise<ChatSession[]> {
  const params = new URLSearchParams();
  if (projectId) params.append("project_id", projectId);
  if (paperId) params.append("paper_id", paperId);
  
  const query = params.toString();
  return apiFetch<ChatSession[]>(`/chat/sessions${query ? `?${query}` : ""}`);
}

export async function createChatSession(data: { title?: string; project_id?: string; paper_id?: string }): Promise<ChatSession> {
  return apiFetch<ChatSession>("/chat/sessions", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function getChatSession(sessionId: string): Promise<ChatSession> {
  return apiFetch<ChatSession>(`/chat/sessions/${sessionId}`);
}

export async function addChatMessage(sessionId: string, question: string): Promise<{ user_message: ChatMessage, ai_message: ChatMessage & { grounded: boolean, model: string } }> {
  return apiFetch(`/chat/sessions/${sessionId}/messages`, {
    method: "POST",
    body: JSON.stringify({ question }),
  });
}

// ── Paper chat mode ──────────────────────────────────────────────────────────
// A paper chat is persistent only while the paper is saved to one of the user's
// projects. The server decides; the panel just renders what it is told.

export type ChatMode = "ephemeral" | "persistent";

export interface PaperChatContext {
  mode: ChatMode;
  session_id: string | null;
  messages: ChatMessage[];
}

export async function getPaperChatContext(paperId: string): Promise<PaperChatContext> {
  return apiFetch<PaperChatContext>(`/chat/papers/${paperId}/context`);
}

export async function askPaperEphemeral(
  paperId: string,
  question: string,
  history: { role: string; content: string }[],
): Promise<{ ai_message: ChatMessage & { grounded: boolean; model: string } }> {
  return apiFetch(`/chat/papers/${paperId}/ephemeral`, {
    method: "POST",
    body: JSON.stringify({ question, history }),
  });
}

export async function promotePaperChat(
  paperId: string,
  messages: { role: string; content: string }[],
): Promise<{ mode: ChatMode; session_id: string; migrated: number }> {
  return apiFetch(`/chat/papers/${paperId}/promote`, {
    method: "POST",
    body: JSON.stringify({ messages }),
  });
}
