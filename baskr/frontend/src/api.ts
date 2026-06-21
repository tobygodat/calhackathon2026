// Typed fetch wrappers for the backend routes (SPEC §8).
// Bodies are stubs — wire up fetch calls during implementation.

import type {
  DigestEntry,
  DigestSummary,
  Profile,
  ProfileItemKind,
  SearchHit,
} from "./types";

export async function getProfile(): Promise<Profile> {
  throw new Error("not implemented");
}

export async function search(_question: string): Promise<SearchHit[]> {
  throw new Error("not implemented");
}

export async function getDigestHistory(): Promise<DigestSummary[]> {
  throw new Error("not implemented");
}

export async function getDigest(_date: string): Promise<DigestEntry[]> {
  throw new Error("not implemented");
}

// Stretch: POST /api/profile/memory (SPEC §8).
export async function addMemory(
  _kind: ProfileItemKind,
  _text: string
): Promise<Profile> {
  throw new Error("not implemented");
}
