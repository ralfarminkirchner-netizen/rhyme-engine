// ── Spiegelt app/schemas/rhyme.py 1:1 ────────────────────────────────────────

export type Mode =
  | "strict"
  | "balanced"
  | "dirty"
  | "multisyllabic"
  | "komposita"
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
