// Typed fetch wrappers for the backend routes (SPEC §8).

import type {
  DigestEntry,
  DigestSummary,
  Profile,
  ProfileItemKind,
  SearchHit,
} from "./types";

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init);
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`${res.status} ${text}`);
  }
  return res.json() as Promise<T>;
}

export async function getProfile(): Promise<Profile> {
  return apiFetch<Profile>("/api/profile");
}

export async function search(question: string): Promise<SearchHit[]> {
  return apiFetch<SearchHit[]>("/api/search", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });
}

export async function getDigestHistory(): Promise<DigestSummary[]> {
  return apiFetch<DigestSummary[]>("/api/digest/history");
}

export async function getDigest(date: string): Promise<DigestEntry[]> {
  return apiFetch<DigestEntry[]>(`/api/digest/${date}`);
}

// Stretch: POST /api/profile/memory (SPEC §8).
export async function addMemory(
  kind: ProfileItemKind,
  text: string
): Promise<Profile> {
  return apiFetch<Profile>("/api/profile/memory", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ kind, text }),
  });
}
