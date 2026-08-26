import { apiFetch } from "./client";
import { BackendPaper } from "./papers";
import { HistoryEventType } from "../types";

export interface TrendingPaper {
  paper: BackendPaper;
  entry: {
    weeklyCitationDelta: number;
    trendScore: number;
    reason: string;
  };
}

export async function getTrendingPapers(): Promise<TrendingPaper[]> {
  return apiFetch("/trending");
}

export interface AnalyticsData {
  totalPapersSaved: number;
  totalNotes: number;
  totalReviews: number;
  totalChatQuestions: number;
  currentStreakDays: number;
  weeklyGoal: { completed: number; target: number };
  papersReadByMonth: { month: string; count: number }[];
  topicBreakdown: { tag: string; count: number }[];
}

export async function getAnalytics(): Promise<AnalyticsData> {
  return apiFetch("/analytics");
}

export interface HistoryEvent {
  id: string;
  type: string;
  timestamp: string;
  title: string;
  description?: string;
  url?: string;
}

export async function getHistory(): Promise<HistoryEvent[]> {
  return apiFetch("/history");
}

export async function logHistoryEvent(data: {
  event_type: string;
  reference_id?: string;
  title?: string;
  url?: string;
  description?: string;
  metadata_json?: Record<string, any>;
}): Promise<HistoryEvent> {
  return apiFetch("/history", {
    method: "POST",
    body: JSON.stringify(data),
  });
}
