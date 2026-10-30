export type AtlasKind = "all" | "word" | "compound" | "phrase";
export type AtlasMode = "strict" | "balanced" | "dirty";
export type AtlasOriginFilter = "all" | "attested" | "constructed";

export interface AtlasSource {
  id: string;
  name: string;
  url?: string;
  license?: string;
  entry_count?: number;
  pronunciation_count?: number;
  sentence_count?: number;
  author?: string;
  sentence_id?: string | number;
}

export interface AtlasSourceReference {
  pronunciation_basis?: string;
  context?: string;
  construction?: string;
  original_entry?: string;
  url?: string;
  author?: string;
  sentence_id?: string | number;
  variant_index?: number;
  parts?: { text: string; source_id?: string; source_ref?: AtlasSourceReference }[];
}

export interface AtlasStatus {
  status: "ready" | "empty" | "building";
  revision: string;
  counts: {
    entries: number; pronunciations: number; words: number; phrases: number;
    compounds: number; sources: number; syllable_nodes: number; sound_edges: number; chains: number;
  };
  syllable_layers: { syllables: number; count: number; words: number; phrases: number; compounds: number }[];
  sources: AtlasSource[];
  build?: Record<string, unknown>;
}

export interface AtlasRegion {
  id: string;
  syllables: number;
  first_family: string;
  last_family: string;
  count: number;
  x: number;
  y: number;
  samples: string[];
  signature?: string;
}

export interface AtlasMap {
  regions: AtlasRegion[];
  total_entries: number;
  layout: string;
  min_syllables?: number;
  max_syllables?: number;
}

export interface AtlasNeighborhood {
  region: Pick<AtlasRegion, "syllables" | "first_family" | "last_family">;
  signatures: {
    signature: string;
    /** Ordered vowel families; exact IPA nuclei remain on individual entries. */
    nuclei: string[];
    count: number;
    samples: string[];
  }[];
}

export interface AtlasAnchor {
  text: string;
  ipa: string;
  syllable_count: number;
  nuclei: string[];
  families?: string[];
  signature?: string;
  entry_id?: string | number;
}

export interface AtlasCandidate extends AtlasAnchor {
  id: string | number;
  language: string;
  kind: string;
  origin: "dictionary" | "dictionary_phrase" | "attested_phrase" | "constructed" | "user";
  source: AtlasSource;
  score: number;
  matched_anchor: string;
  reason: string;
  notes?: string[];
  source_ref?: AtlasSourceReference;
}

export interface AtlasFilters {
  mode: AtlasMode;
  kind: AtlasKind;
  languages: string[];
  min_syllables: number;
  max_syllables: number;
  origin: AtlasOriginFilter;
  include_combinations: boolean;
  limit: number;
}

export interface AtlasSearchRequest extends AtlasFilters {
  query: string;
  region?: Pick<AtlasRegion, "syllables" | "first_family" | "last_family" | "signature">;
}

export interface AtlasSearchResponse {
  query: string;
  anchors: AtlasAnchor[];
  results: AtlasCandidate[];
  searched_candidates: number;
  total_matches: number;
  warnings: string[];
}

export interface AtlasChainMember extends AtlasAnchor {
  position: number;
  entry_id?: string | number;
}

export interface AtlasChain {
  id: string;
  title: string;
  members: AtlasChainMember[];
  created_at: string;
}

export type AtlasChainInputMember = string | { text: string; entry_id?: string | number };
