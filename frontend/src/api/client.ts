import type {
  ModesResponse,
  PhoneticFeatures,
  PhraseRankRequest,
  PhraseRankResponse,
  RhymeHighlightResponse,
  SearchRequest,
  SearchResponse,
  UserFullLibraryResponse,
  UserLocalModelTrainResponse,
  UserPipelineResponse,
  UserQuoteSearchResponse,
  UserTrainingBuildResponse,
  UserTextLineSearchResponse,
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
  searchUserRhymes: (req: {
    query: string;
    limit?: number;
    min_score?: number;
    rerank?: boolean;
    rerank_candidate_count?: number;
    include_context_in_rerank?: boolean;
  }) =>
    post<UserRhymeSearchResponse>("/api/rhymes/user-texts/search", req),
  searchUserTextLines: (req: { query: string; limit?: number }) =>
    post<UserTextLineSearchResponse>("/api/rhymes/user-texts/search-lines", req),
  searchUserQuotes: (req: { query: string; limit?: number; min_score?: number }) =>
    post<UserQuoteSearchResponse>("/api/rhymes/user-texts/search-quotes", req),
  loadUserLibrary: (req: { limit?: number }) =>
    post<UserFullLibraryResponse>("/api/rhymes/user-texts/library", req),
  buildUserTraining: (req: { max_examples?: number; include_text_lines?: boolean }) =>
    post<UserTrainingBuildResponse>("/api/rhymes/user-texts/build-training", req),
  trainLocalModel: (req: { min_pair_score?: number }) =>
    post<UserLocalModelTrainResponse>("/api/rhymes/user-texts/train-local-model", req),
  runUserPipeline: (req: {
    query?: string;
    prefer_pages_export?: boolean;
    context_radius?: number;
    max_examples?: number;
    min_pair_score?: number;
    limit?: number;
    min_score?: number;
  }) =>
    post<UserPipelineResponse>("/api/rhymes/user-texts/pipeline", req),
};
