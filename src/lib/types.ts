export type PaperSource = "arXiv" | "Semantic Scholar" | "PubMed" | "IEEE" | "ACL Anthology";

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
  name: string;
  description: string;
  createdAt: string;
  updatedAt: string;
  color: "teal" | "brass" | "ink";
  paperIds: string[];
  collaborators: { name: string; avatarInitial: string }[];
  milestones: {
    papersAdded: boolean;
    notesTaken: boolean;
    compared: boolean;
    reviewGenerated: boolean;
  };
}

export interface User {
  name: string;
  email: string;
  role: string;
  institution: string;
  avatarInitial: string;
}
