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
