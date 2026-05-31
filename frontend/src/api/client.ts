import type {
  ModesResponse,
  PhoneticFeatures,
  PhraseRankRequest,
  PhraseRankResponse,
  RhymeHighlightResponse,
  SearchRequest,
  SearchResponse,
  UserRhymeSearchResponse,
  UserTextSummary,
} from "../types";

// Same-origin: im Prod liefert FastAPI das Frontend selbst aus, API liegt unter
// derselben Domain. Im Dev proxyt Vite /api → localhost:8003 (siehe vite.config.ts).
const BASE = "";

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const txt = await res.text().catch(() => res.statusText);
    throw new Error(`${res.status} ${path}: ${txt}`);
  }
  return res.json();
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`${res.status} ${path}`);
  return res.json();
}

export const api = {
  health: () => get<{ status: string; words_loaded: number }>("/api/rhymes/health"),
  modes:  () => get<ModesResponse>("/api/rhymes/modes"),
  analyze: (word: string) =>
    post<PhoneticFeatures>("/api/rhymes/analyze", { word }),
  search: (req: SearchRequest) =>
    post<SearchResponse>("/api/rhymes/search", req),
  rankPhrases: (req: PhraseRankRequest) =>
    post<PhraseRankResponse>("/api/rhymes/rank-phrases", req),
  highlightRhymes: (req: { text: string; context_radius?: number }) =>
    post<RhymeHighlightResponse>("/api/rhymes/highlight-rhymes", req),
  rakiText: () => get<{ text: string }>("/api/rhymes/training/raki-dich"),
  userTextSummary: () => get<UserTextSummary>("/api/rhymes/user-texts/summary"),
  importUserTexts: (req: { prefer_pages_export?: boolean; context_radius?: number }) =>
    post<UserTextSummary>("/api/rhymes/user-texts/import", req),
  searchUserRhymes: (req: { query: string; limit?: number; min_score?: number }) =>
    post<UserRhymeSearchResponse>("/api/rhymes/user-texts/search", req),
};
