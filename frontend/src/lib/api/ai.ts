/**
 * Frontend API client for SAIRA's AI features.
 *
 * All requests go through the existing apiFetch pattern (SAIRA backend API).
 * The Groq API key never touches the browser — it stays server-side.
 *
 * Architecture:
 *   Frontend → this module → apiFetch → Backend /api/v1/ai/* → AI Router → Groq
 */

import { apiFetch } from "./client";

// ── Types ─────────────────────────────────────────────────────────────────────

export interface AISummaryResponse {
  tldr: string | null;
  key_findings: string[];
  methodology: string | null;
  contributions: string[];
  limitations: string[];
  /** Groq model identifier actually used (e.g. "openai/gpt-oss-120b") */
  model?: string;
}

export interface AIExtractionResponse {
  datasets: string[];
  models: string[];
  algorithms: string[];
  metrics: string[];
  limitations: string[];
  future_work: string[];
}

export interface AIQAResponse {
  answer: string;
  grounded: boolean;
  /** Groq model identifier actually used (e.g. "openai/gpt-oss-120b") */
  model?: string;
}

export interface AIStatusResponse {
  configured: boolean;
  primary_model: string;
  extraction_model: string;
  message: string;
}

export interface PRDResponse {
  prd_score: number;
  semantic_delta: number;
  method_delta: number;
  dataset_delta: number;
  gap_resolution: number;
  explanation: string;
  model?: string;
}

/**
 * Map an internal Groq model identifier to a human-readable display label.
 * Add entries here as new models are introduced — never hardcode labels in components.
 */
export function modelLabel(modelId?: string | null): string {
  if (!modelId) return "";
  const MAP: Record<string, string> = {
    "openai/gpt-oss-120b":  "GPT-OSS 120B",
    "qwen/qwen3.6-27b":     "Qwen 3.6 27B",
    "groq/compound":        "Groq Compound",
    "groq/compound-mini":   "Groq Compound Mini",
    "llama-3.3-70b-versatile": "Llama 3.3 70B",
  };
  return MAP[modelId] ?? modelId;
}

// ── API Functions ─────────────────────────────────────────────────────────────

/**
 * Check whether Groq AI is configured on the backend.
 */
export async function getAIStatus(): Promise<AIStatusResponse> {
  return apiFetch<AIStatusResponse>("/ai/status");
}

/**
 * Generate a structured AI summary of a paper using the primary model.
 * Context comes from the paper's stored metadata — no PDF needed.
 */
export async function fetchPaperSummary(
  paperId: string
): Promise<AISummaryResponse> {
  return apiFetch<AISummaryResponse>("/ai/summary", {
    method: "POST",
    body: JSON.stringify({ paper_id: paperId }),
  });
}

/**
 * Extract structured research info from a paper using GPT-OSS 120B.
 * Returns datasets, models, algorithms, metrics, limitations, future work.
 */
export async function fetchPaperExtraction(
  paperId: string
): Promise<AIExtractionResponse> {
  return apiFetch<AIExtractionResponse>("/ai/extract", {
    method: "POST",
    body: JSON.stringify({ paper_id: paperId }),
  });
}

/**
 * Ask a question about a paper using the primary AI model.
 * The model answers only from available paper context.
 */
export async function askPaperQA(
  paperId: string,
  question: string
): Promise<AIQAResponse> {
  return apiFetch<AIQAResponse>("/ai/qa", {
    method: "POST",
    body: JSON.stringify({ paper_id: paperId, question }),
  });
}

/**
 * Calculate the Personalized Research Delta (PRD) for a candidate paper 
 * against a user's specific project workspace.
 */
export async function calculatePRD(
  projectId: string,
  paperId: string
): Promise<PRDResponse> {
  return apiFetch<PRDResponse>("/ai/prd", {
    method: "POST",
    body: JSON.stringify({ project_id: projectId, paper_id: paperId }),
  });
}
