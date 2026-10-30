export type GraphMode = "strict" | "balanced" | "dirty";
export type GraphDecision = "accepted" | "experiment" | "rejected";

export interface PronunciationOverride {
  line_index: number;
  word_index: number;
  syllables: string[][];
  stress: number[];
  word_text?: string;
}

export interface GraphBuildRequest {
  text: string;
  mode: GraphMode;
  min_syllables: number;
  max_syllables: number;
  max_syllable_delta: number;
  include_internal: boolean;
  min_similarity: number;
  max_nodes: number;
  max_edges: number;
  overrides: PronunciationOverride[];
  include_library: boolean;
  library_query: string;
  library_limit: number;
}

export interface GraphWord {
  word_index: number;
  text: string;
  char_start: number;
  char_end: number;
  start_syllable: number;
  end_syllable: number;
  phonetic_syllables: string[][];
  stress: number[];
  origin: "rule_based" | "manual";
}

export interface GraphLine {
  line_index: number;
  text: string;
  char_start: number;
  char_end: number;
  words: GraphWord[];
  phonetic_syllables: string[][];
  stress: number[];
}

export interface GraphSource {
  kind?: string;
  source_id?: string;
  source_title?: string;
  line_no?: number;
  line_text?: string;
  line_hash?: string;
  unit_id?: string | number;
}

export interface GraphNode {
  id: string;
  line_index: number;
  char_start: number;
  char_end: number;
  start_syllable: number;
  end_syllable: number;
  start_word: number;
  end_word: number;
  text: string;
  phonetic_syllables: string[][];
  stress: number[];
  kind: "terminal" | "internal";
  origin: "rule_based" | "manual";
  source?: GraphSource;
}

export interface GraphProfile {
  anchor: number;
  terminal: number;
  vowels: number;
  consonants: number;
  stress: number;
  coverage: number;
  rap_anchors?: number;
  consonant_grip?: number;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  kind: "clean" | "slant" | "flex";
  basis?: "exact" | "segment" | "rap_pattern";
  evidence?: string[];
  score: number;
  profile: GraphProfile;
  alignment: {
    left_index: number | null;
    right_index: number | null;
    vowel_similarity: number;
    coda_similarity: number;
    stress_match: boolean;
  }[];
  deviations: string[];
  required_operations: string[];
  status: "proposed";
}

export interface RhymeGraphResponse {
  version: string;
  fingerprint?: string;
  text: string;
  mode: GraphMode;
  lines: GraphLine[];
  nodes: GraphNode[];
  edges: GraphEdge[];
  warnings: string[];
  analysis_notes?: string[];
  truncated: boolean;
}

export interface GraphFeedback {
  edge_id: string;
  decision: GraphDecision;
  heard: boolean;
  comment: string;
  performance_note: string;
  meaning_note: string;
  updated_at?: string | number;
}

export interface GraphSessionSummary {
  id: string;
  title: string;
  created_at: string | number;
  updated_at: string | number;
  node_count: number;
  edge_count: number;
}

export interface GraphSession {
  id: string;
  title: string;
  created_at: string | number;
  updated_at: string | number;
  request: GraphBuildRequest;
  graph: RhymeGraphResponse;
  feedback: GraphFeedback[];
  feedback_history?: GraphFeedback[];
}

export interface GraphSourceContext {
  source_id: string;
  title: string;
  path: string;
  extraction_method: string;
  line_no: number;
  lines: { line_no: number; text: string }[];
  status: string;
  matches_snapshot?: boolean | null;
  line_hash?: string;
}
