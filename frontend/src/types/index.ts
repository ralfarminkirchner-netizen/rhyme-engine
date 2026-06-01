// ── Spiegelt app/schemas/rhyme.py 1:1 ────────────────────────────────────────

export type Mode =
  | "strict"
  | "balanced"
  | "dirty"
  | "multisyllabic"
  | "hardcore"
  | "endRhyme";

export type FeatureTarget = "rhyme" | "terminal";

export interface RawWeights {
  stress: number;
  vowelCore: number;
  tail: number;
  syllableFlex: number;
}

export interface Thresholds {
  maxSyllableDelta: number;
  maxStressDistance: number;
  maxVowelDistance: number;
  minTailSimilarity: number;
}

export interface ModePreset {
  description: string;
  target: FeatureTarget;
  thresholds: Thresholds;
  defaultWeights: RawWeights;
}

export interface ModesResponse {
  modes: Record<Mode, ModePreset>;
}

/** Phonetisches API-DTO (camelCase, aus PhoneticFeatures) */
export interface PhoneticFeatures {
  text: string;
  phonetic: string[];
  syllableCount: number;
  stressPattern: number[];
  // Betonter Reimspan (mehrsilbig)
  rhymeSpan: string[];
  vowelSpine: string[];
  tail: string[];
  // Terminaler Span (letzter Vokal bis Wortende)
  terminalSpan: string[];
  terminalVowelSpine: string[];
  terminalTail: string[];
}

export interface ScoreBreakdown {
  stress: number;
  vowelCore: number;
  tail: number;
  syllableFlex: number;
}

export interface ValidationMetrics {
  syllableDelta: number;
  stressDistance: number;
  vowelDistance: number;
  tailSimilarity: number;
}

export interface ValidationResult {
  valid: boolean;
  reasons: string[];
  metrics: ValidationMetrics;
}

export interface RankedCandidate extends PhoneticFeatures {
  score: number;
  breakdown: ScoreBreakdown;
  validation: ValidationResult;
  activeVowels: string[];
  activeTail: string[];
}

export interface RejectedCandidate extends PhoneticFeatures {
  validation: ValidationResult;
  activeVowels: string[];
  activeTail: string[];
}

export interface SearchResponse {
  query: PhoneticFeatures;
  mode: Mode;
  target: FeatureTarget;
  thresholds: Thresholds;
  weights: RawWeights;
  results: RankedCandidate[];
  rejected?: RejectedCandidate[];
}

export interface SearchRequest {
  query: string;
  mode: Mode;
  weights?: Partial<RawWeights>;
  limit?: number;
  debug?: boolean;
}

export interface PhraseRankRequest {
  query: string;
  candidates: string[];
}

export interface PhraseRankResult {
  phrase: string;
  score: number;
  anchor: number;
  tail: number;
  vowel: number;
  cadence: number;
  anchor_gated: boolean;
  suffix_penalized: boolean;
  reason: string;
}

export interface PhraseRankResponse {
  query: string;
  ranked: PhraseRankResult[];
}

export interface HighlightSegment {
  text: string;
  kind: "text" | "space" | "punct" | "syllable";
  word?: string | null;
  syllable_index?: number | null;
  accented: boolean;
  terminal: boolean;
  rhyme_group?: string | null;
  color?: string | null;
  phonetic: string[];
}

export interface HighlightLine {
  raw_index: number;
  lyric_index?: number | null;
  raw: string;
  is_lyric: boolean;
  segments: HighlightSegment[];
}

export interface RhymeGroup {
  key: string;
  color: string;
  count: number;
  line_indices: number[];
  examples: string[];
}

export interface RhymeHighlightResponse {
  lines: HighlightLine[];
  rhyme_groups: RhymeGroup[];
  colored_syllable_count: number;
  accented_syllable_count: number;
}

export interface UserTextDocument {
  source_id: string;
  title: string;
  path: string;
  kind: string;
  extraction_method: string;
  status: string;
  line_count: number;
  rhyme_unit_count: number;
  warning: string;
}

export interface UserTextPairSample {
  left_phrase: string;
  right_phrase: string;
  score: number;
  source_title: string;
  left_line_no: number;
  right_line_no: number;
}

export interface UserQuoteSample {
  id: number;
  source_id: string;
  source_title: string;
  line_no: number;
  text: string;
  phrase: string;
  syllable_count: number;
  quote_score: number;
  terminal_anchor: string;
  reason: string;
}

export interface UserTextSummary {
  inbox_dir: string;
  extracted_dir: string;
  database_path: string;
  source_count: number;
  imported_count: number;
  skipped_count: number;
  line_count: number;
  rhyme_unit_count: number;
  rhyme_pair_count: number;
  quote_count: number;
  documents: UserTextDocument[];
  sample_pairs: UserTextPairSample[];
  sample_quotes: UserQuoteSample[];
  warnings: string[];
}

export interface UserRhymeResult {
  phrase: string;
  score: number;
  raw_score?: number;
  llm_score?: number;
  llm_reason?: string;
  learned_score?: number;
  learned_reason?: string;
  anchor: number;
  tail: number;
  vowel: number;
  cadence: number;
  source_title: string;
  line_no: number;
  line_text: string;
  syllable_count: number;
  reason: string;
}

export interface UserRhymeRerankInfo {
  enabled: boolean;
  provider: string;
  warning?: string;
  candidate_count?: number;
  model_pair_count?: number;
  weights?: Record<string, number>;
}

export interface UserRhymeSearchResponse {
  query: string;
  results: UserRhymeResult[];
  total_candidates: number;
  retrieved_candidates?: number;
  rerank?: UserRhymeRerankInfo;
  warning?: string;
}

export interface UserTextLineResult {
  source_title: string;
  line_no: number;
  text: string;
  word_count: number;
  char_count: number;
  score: number;
  matched_terms: number;
}

export interface UserTextLineSearchResponse {
  query: string;
  results: UserTextLineResult[];
  total_candidates: number;
  retrieved_candidates?: number;
  warning?: string;
}

export interface UserQuoteResult {
  source_title: string;
  line_no: number;
  text: string;
  phrase: string;
  syllable_count: number;
  quote_score: number;
  rhyme_score: number;
  score: number;
  terminal_anchor: string;
  reason: string;
  rhyme_reason?: string;
}

export interface UserQuoteSearchResponse {
  query: string;
  results: UserQuoteResult[];
  total_candidates: number;
  retrieved_candidates?: number;
  warning?: string;
}

export interface UserTrainingBuildResponse {
  status: string;
  output_path: string;
  example_count: number;
  rhyme_pair_count: number;
  quote_count: number;
  text_line_count: number;
  warning: string;
}

export interface UserLocalModelTrainResponse {
  status: string;
  model_path: string;
  pair_count: number;
  weights?: Record<string, number>;
  ideal_syllables?: number;
  warning: string;
}

export interface UserPipelineResponse {
  status: string;
  query: string;
  import: UserTextSummary;
  training: UserTrainingBuildResponse;
  model: UserLocalModelTrainResponse;
  search: {
    total_candidates: number;
    retrieved_candidates: number;
    rerank: UserRhymeRerankInfo;
    results: UserRhymeResult[];
  };
}
