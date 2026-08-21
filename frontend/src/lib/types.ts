export type PaperSource = "arXiv" | "Semantic Scholar" | "PubMed" | "IEEE" | "ACL Anthology" | "OpenAlex";

export interface Author {
  name: string;
  affiliation?: string;
}

export interface Paper {
  id: string;
  title: string;
  authors: Author[];
  year: number;
  venue: string;
  source: PaperSource;
  abstract: string;
  citationCount: number;
  tags: string[];
  pdfUrl?: string;
  savedToProjectIds: string[];
  readingStatus: "unread" | "reading" | "read";
  aiSummary: {
    tldr: string;
    keyFindings: string[];
    methodology: string;
    limitations: string[];
  };
  extracted: {
    problem: string;
    dataset: string[];
    method: string;
    metrics: { name: string; value: string }[];
    codeAvailable: boolean;
  };
}

export interface Note {
  id: string;
  paperId: string;
  content: string;
  createdAt: string;
  highlight?: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  citedPaperIds?: string[];
  createdAt: string;
}

export interface Project {
  id: string;
  user_id: string;
  name: string;
  description: string | null;
  color: string;
  created_at: string;
  updated_at: string;
}

export interface ProjectPaper {
  id: string;
  project_id: string;
  paper_id: string;
  status?: string | null;
  favorite: boolean;
  priority?: number | null;
  added_at: string;
}


/* ---------- v2 additions ---------- */

export type CollectionIcon = "star" | "clock" | "flame" | "layers";

export interface Collection {
  id: string;
  name: string;
  description: string;
  icon: CollectionIcon;
  color: "teal" | "brass" | "ink";
  paperIds: string[];
  /** Smart collections are auto-populated by SAIRA rather than curated by hand. */
  smart: boolean;
  createdAt: string;
  updatedAt: string;
}

export type HistoryEventType =
  | "search"
  | "view_paper"
  | "view_project"
  | "chat"
  | "compare"
  | "review_generated"
  | "note_added";

export interface HistoryEvent {
  id: string;
  type: HistoryEventType;
  title: string;
  detail?: string;
  href?: string;
  timestamp: string;
}

export interface TrendingEntry {
  paperId: string;
  weeklyCitationDelta: number;
  /** 0-100 */
  trendScore: number;
  reason: string;
}

export interface AnalyticsSnapshot {
  papersReadByMonth: { month: string; count: number }[];
  topicBreakdown: { tag: string; count: number }[];
  totalPapersSaved: number;
  totalNotes: number;
  totalReviews: number;
  totalChatQuestions: number;
  currentStreakDays: number;
  weeklyGoal: { target: number; completed: number };
}

export type SavedArtifactType = "chat_answer" | "review_snippet";

export interface SavedArtifact {
  id: string;
  projectId?: string;
  paperId?: string;
  type: SavedArtifactType;
  title: string;
  content: string;
  citedPaperIds?: string[];
  createdAt: string;
}

export interface RelatedPaperLink {
  paperId: string;
  relation: "supports" | "contradicts";
  note: string;
}
