import { apiFetch } from "./client";
import { Paper } from "../types";

export interface Collection {
  id: string;
  name: string;
  description: string | null;
  color: string | null;
  created_at: string;
  updated_at: string;
}

export async function getCollections(): Promise<Collection[]> {
  return apiFetch("/collections/");
}

export async function getCollection(id: string): Promise<Collection> {
  return apiFetch(`/collections/${id}`);
}

export async function createCollection(data: { name: string; description?: string; color?: string }): Promise<Collection> {
  return apiFetch("/collections/", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export async function updateCollection(id: string, data: { name?: string; description?: string; color?: string }): Promise<Collection> {
  return apiFetch(`/collections/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export async function deleteCollection(id: string): Promise<void> {
  await apiFetch(`/collections/${id}`, { method: "DELETE" });
}

export async function getCollectionPapers(id: string): Promise<Paper[]> {
  return apiFetch(`/collections/${id}/papers`);
}

export async function addPaperToCollection(collectionId: string, paperId: string): Promise<void> {
  await apiFetch(`/collections/${collectionId}/papers/${paperId}`, { method: "POST" });
}

export async function removePaperFromCollection(collectionId: string, paperId: string): Promise<void> {
  await apiFetch(`/collections/${collectionId}/papers/${paperId}`, { method: "DELETE" });
}
