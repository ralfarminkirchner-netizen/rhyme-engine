import { useCallback, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { api } from "../api/client";
import type {
  UserMeaningResult,
  UserMeaningSearchResponse,
  UserRhymeResult,
  UserRhymeSearchResponse,
  UserTextSummary,
} from "../types";

type Axis = "rhymes" | "meaning";

const BACKEND_URL = "http://localhost:8003";
const RATING_VALUES = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10];

function asNumber(value: unknown, fallback = 0): number {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return fallback;
}

function score(value: unknown): string {
  return asNumber(value).toFixed(3);
}

function compactScore(value: unknown): string {
  return asNumber(value).toFixed(2);
}

function clampLimit(value: number): number {
  return Math.min(100, Math.max(1, Math.round(value || 25)));
}

function clampMinScore(value: number): number {
  return Math.min(1, Math.max(0, Number.isFinite(value) ? value : 0));
}

function backendError(error: unknown): string {
  const raw = error instanceof Error ? error.message : String(error);
  return `Backend nicht erreichbar auf ${BACKEND_URL} — läuft uvicorn auf 8003? ${raw}`;
}

function resultKey(row: Pick<UserRhymeResult, "source_title" | "line_no" | "phrase">): string {
  return `${row.source_title}:${row.line_no}:${row.phrase}`;
}

function ratingTone(value: number): "low" | "mid" | "high" {
  if (value <= 3) return "low";
  if (value <= 7) return "mid";
  return "high";
}

function matchedTerms(row: UserMeaningResult): string[] {
  return Array.isArray(row.matched_terms)
    ? row.matched_terms.map(String).filter(Boolean)
    : [];
}

function HeaderStats({ summary }: { summary: UserTextSummary | null }) {
  return (
    <div className="rw-header-stats">
      <span className="rw-stat-chip"><strong>{summary?.imported_count ?? 0}</strong> Quellen</span>
      <span className="rw-stat-chip"><strong>{summary?.line_count ?? 0}</strong> Zeilen</span>
      <span className="rw-stat-chip"><strong>{summary?.rhyme_unit_count ?? 0}</strong> Units</span>
      <span className="rw-stat-chip"><strong>{summary?.quote_count ?? 0}</strong> Quotes</span>
    </div>
  );
}

function AxisButton({
  active,
  children,
  onClick,
}: {
  active: boolean;
  children: ReactNode;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      className={`rw-axis-button ${active ? "is-active" : ""}`}
      onClick={onClick}
      aria-pressed={active}
    >
      {children}
    </button>
  );
}

function Badge({
  children,
  tone,
}: {
  children: ReactNode;
  tone?: "good" | "warn" | "muted" | "violet";
}) {
  return <span className={`rw-badge ${tone ? `rw-badge-${tone}` : ""}`}>{children}</span>;
}

function RhymeCard({
  row,
  query,
  pending,
  saved,
  error,
  draftComment,
  onCommentChange,
  onFeedback,
}: {
  row: UserRhymeResult;
  query: string;
  pending: boolean;
  saved: boolean;
  error?: string;
  draftComment: string;
  onCommentChange: (comment: string) => void;
  onFeedback: (row: UserRhymeResult, rating: number, comment: string) => void;
}) {
  const currentRating = row.feedback_rating ?? null;
  const displayFeedbackScore = row.feedback_score ?? row.score;
  const occurrenceCount = asNumber(row.occurrence_count, 1);
  const hasPattern = asNumber(row.feedback_pattern_count) > 0;

  return (
    <article className={`rw-result-card rw-rhyme-card ${currentRating != null || saved ? "is-rated" : ""}`}>
      <div className="rw-card-topline">
        <div>
          <h2 className="rw-result-title">{row.phrase || "Unbenannter Treffer"}</h2>
          {row.line_text && <p className="rw-line-context">{row.line_text}</p>}
        </div>
        <div className="rw-card-rank" title={`Feedback-Score für "${query}"`}>
          {score(displayFeedbackScore)}
        </div>
      </div>

      <div className="rw-badge-row">
        <Badge>Engine {score(row.score)}</Badge>
        <Badge tone="good">nach Feedback {score(displayFeedbackScore)}</Badge>
        <Badge>Anker {compactScore(row.anchor)}</Badge>
        <Badge>Tail {compactScore(row.tail)}</Badge>
        <Badge>Vokal {compactScore(row.vowel)}</Badge>
        <Badge>Kadenz {compactScore(row.cadence)}</Badge>
        <Badge>{asNumber(row.syllable_count)} Silben</Badge>
        <Badge tone="muted">
          {row.source_title || "Quelle unbekannt"}
          {occurrenceCount > 1 ? ` · ${occurrenceCount}x` : ""}
          {row.line_no ? ` · Zeile ${row.line_no}` : ""}
        </Badge>
        {hasPattern && (
          <Badge tone="warn">
            Muster {asNumber(row.feedback_pattern_count)}x
            {row.feedback_pattern_average != null ? ` (Ø ${compactScore(row.feedback_pattern_average)})` : ""}
          </Badge>
        )}
        {currentRating != null && <Badge tone="good">deine Note {currentRating}</Badge>}
      </div>

      {row.reason && <p className="rw-reason">{row.reason}</p>}

      <div className="rw-rating-block">
        <div className="rw-rating-copy">
          <strong>Note 0-10</strong>
          <span>0-3 schlecht/kein Reim · 4-7 ok · 8-10 stark</span>
        </div>
        <div className="rw-rating-scale" aria-label={`Bewertung für ${row.phrase}`}>
          {RATING_VALUES.map((rating) => {
            const selected = currentRating === rating;
            return (
              <button
                key={rating}
                type="button"
                className={[
                  "rw-rating-button",
                  `rw-rating-${ratingTone(rating)}`,
                  selected ? "is-selected" : "",
                ].filter(Boolean).join(" ")}
                disabled={pending}
                onClick={() => onFeedback(row, rating, draftComment)}
                title={`${rating}/10 speichern`}
              >
                {rating}
              </button>
            );
          })}
        </div>
      </div>

      <div className="rw-comment-row">
        <textarea
          className="rw-comment-field"
          value={draftComment}
          maxLength={2000}
          rows={2}
          onChange={(event) => onCommentChange(event.target.value)}
          placeholder="Kommentar optional, bleibt lokal im Feedback-Speicher"
        />
        <button
          type="button"
          className="rw-quiet-button"
          disabled={pending || currentRating == null}
          onClick={() => {
            if (currentRating != null) onFeedback(row, currentRating, draftComment);
          }}
        >
          Kommentar speichern
        </button>
      </div>

      <div className="rw-card-foot">
        <span>Feedback wirkt exakt auf diesen Treffer und ab 2 Muster-Noten auch auf ähnliche Endreim-/Flow-Muster.</span>
        {pending && <strong>speichert...</strong>}
        {saved && <strong className="rw-learned">gelernt ✓</strong>}
        {error && <strong className="rw-card-error">{error}</strong>}
      </div>
    </article>
  );
}

function MeaningCard({ row }: { row: UserMeaningResult }) {
  const terms = matchedTerms(row);

  return (
    <article className="rw-result-card rw-meaning-card">
      <div className="rw-card-topline">
        <h2 className="rw-result-title">{row.text || "Leere Zeile"}</h2>
        <div className="rw-card-rank rw-card-rank-violet">{score(row.score)}</div>
      </div>
      <div className="rw-badge-row">
        <Badge tone="violet">Relevanz {score(row.score)}</Badge>
        <Badge tone="muted">
          {row.source_title || "Quelle unbekannt"}
          {row.line_no ? ` · Zeile ${row.line_no}` : ""}
        </Badge>
        {terms.length > 0 && <Badge>Treffer: {terms.join(", ")}</Badge>}
      </div>
    </article>
  );
}

function SummaryPanel({
  summary,
  loading,
  error,
  onRefresh,
  onImport,
}: {
  summary: UserTextSummary | null;
  loading: boolean;
  error: string | null;
  onRefresh: () => void;
  onImport: () => void;
}) {
  return (
    <section className="rw-side-panel">
      <h2 className="rw-side-title">Bibliothek</h2>
      <div className="rw-count-grid">
        <div className="rw-count"><strong>{summary?.source_count ?? 0}</strong><span>Quellen gesamt</span></div>
        <div className="rw-count"><strong>{summary?.line_count ?? 0}</strong><span>Zeilen</span></div>
        <div className="rw-count"><strong>{summary?.rhyme_unit_count ?? 0}</strong><span>Reim-Units</span></div>
        <div className="rw-count"><strong>{summary?.rhyme_pair_count ?? 0}</strong><span>Reimpaare</span></div>
      </div>
      <div className="rw-side-actions" style={{ marginTop: "0.75rem" }}>
        <button className="rw-primary-button" type="button" onClick={onImport} disabled={loading}>
          {loading ? "Lädt" : "Importieren"}
        </button>
        <button className="rw-quiet-button" type="button" onClick={onRefresh} disabled={loading}>
          Status
        </button>
      </div>
      {error && <div className="rw-inline-error">{error}</div>}
      {summary?.warnings?.length ? (
        <div className="rw-warning-list">
          {summary.warnings.slice(0, 3).map((warning, index) => (
            <span key={`${warning}-${index}`}>{warning}</span>
          ))}
        </div>
      ) : null}
    </section>
  );
}

function SourcePanel({ summary }: { summary: UserTextSummary | null }) {
  if (!summary?.documents?.length) return null;

  return (
    <section className="rw-side-panel">
      <h2 className="rw-side-title">Quellen</h2>
      <div className="rw-pill-list">
        {summary.documents.slice(0, 18).map((doc) => (
          <span key={doc.source_id} className="rw-pill">
            {doc.title}: {doc.line_count}/{doc.rhyme_unit_count}
          </span>
        ))}
      </div>
    </section>
  );
}

export default function RhymeSearch() {
  const [axis, setAxis] = useState<Axis>("rhymes");
  const [query, setQuery] = useState("einfach machen");
  const [limit, setLimit] = useState(25);
  const [minScore, setMinScore] = useState(0.4);
  const [rhymeResponse, setRhymeResponse] = useState<UserRhymeSearchResponse | null>(null);
  const [meaningResponse, setMeaningResponse] = useState<UserMeaningSearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [summary, setSummary] = useState<UserTextSummary | null>(null);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [summaryError, setSummaryError] = useState<string | null>(null);
  const [comments, setComments] = useState<Record<string, string>>({});
  const [pendingFeedback, setPendingFeedback] = useState<Record<string, boolean>>({});
  const [savedFeedback, setSavedFeedback] = useState<Record<string, boolean>>({});
  const [feedbackErrors, setFeedbackErrors] = useState<Record<string, string>>({});

  const activeResponse = axis === "rhymes" ? rhymeResponse : meaningResponse;
  const activeCount = activeResponse?.results?.length ?? 0;
  const activeTotal = activeResponse?.total_candidates ?? 0;

  const modeHint = useMemo(() => {
    if (axis === "rhymes") {
      return "Modus: Reime - klanglich, mit Bewertung und Lernen.";
    }
    return "Modus: Bedeutung - thematisch verwandte Zeilen, getrennt vom Reim-Ranking und read-only.";
  }, [axis]);

  const loadSummary = useCallback(async () => {
    setSummaryLoading(true);
    setSummaryError(null);
    try {
      setSummary(await api.userTextSummary());
    } catch (caught) {
      setSummaryError(backendError(caught));
    } finally {
      setSummaryLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadSummary();
  }, [loadSummary]);

  const importUserTexts = useCallback(async () => {
    setSummaryLoading(true);
    setSummaryError(null);
    try {
      setSummary(await api.importUserTexts({ prefer_pages_export: true, context_radius: 12 }));
    } catch (caught) {
      setSummaryError(backendError(caught));
    } finally {
      setSummaryLoading(false);
    }
  }, []);

  const searchRhymes = useCallback(async () => {
    const trimmed = query.trim();
    if (!trimmed) return;
    setLoading(true);
    setError(null);
    try {
      const response = await api.searchUserRhymes({
        query: trimmed,
        limit: clampLimit(limit),
        min_score: clampMinScore(minScore),
        rerank: false,
      });
      setRhymeResponse(response);
      setComments((current) => {
        const next = { ...current };
        for (const row of response.results ?? []) {
          const key = resultKey(row);
          if (next[key] == null) next[key] = row.feedback_comment ?? "";
        }
        return next;
      });
    } catch (caught) {
      setError(backendError(caught));
    } finally {
      setLoading(false);
    }
  }, [limit, minScore, query]);

  const searchMeaning = useCallback(async () => {
    const trimmed = query.trim();
    if (!trimmed) return;
    setLoading(true);
    setError(null);
    try {
      setMeaningResponse(await api.searchMeaning({
        query: trimmed,
        limit: clampLimit(limit),
        min_score: clampMinScore(minScore),
      }));
    } catch (caught) {
      setError(backendError(caught));
    } finally {
      setLoading(false);
    }
  }, [limit, minScore, query]);

  const runSearch = useCallback(() => {
    if (axis === "rhymes") {
      void searchRhymes();
      return;
    }
    void searchMeaning();
  }, [axis, searchMeaning, searchRhymes]);

  const saveFeedback = useCallback(async (
    row: UserRhymeResult,
    rating: number,
    comment: string,
  ) => {
    const key = resultKey(row);
    const queryForFeedback = rhymeResponse?.query || query.trim();
    setPendingFeedback((current) => ({ ...current, [key]: true }));
    setSavedFeedback((current) => ({ ...current, [key]: false }));
    setFeedbackErrors((current) => ({ ...current, [key]: "" }));

    try {
      const response = await api.saveRhymeFeedback({
        query: queryForFeedback,
        source_title: row.source_title,
        line_no: row.line_no,
        phrase: row.phrase,
        rating,
        comment,
      });

      setRhymeResponse((current) => {
        if (!current) return current;
        return {
          ...current,
          results: current.results.map((candidate) => {
            if (resultKey(candidate) !== key) return candidate;
            return {
              ...candidate,
              feedback_rating: response.feedback.rating,
              feedback_comment: response.feedback.comment,
              feedback_count: Math.max(asNumber(candidate.feedback_count), 1),
              feedback_average: response.feedback.rating,
            };
          }),
        };
      });
      setComments((current) => ({ ...current, [key]: response.feedback.comment }));
      setSavedFeedback((current) => ({ ...current, [key]: true }));
    } catch (caught) {
      setFeedbackErrors((current) => ({ ...current, [key]: backendError(caught) }));
    } finally {
      setPendingFeedback((current) => ({ ...current, [key]: false }));
    }
  }, [query, rhymeResponse?.query]);

  return (
    <div className="rw-app">
      <header className="rw-header">
        <div className="rw-brand">
          <div className="rw-logo">REiMWERKER</div>
          <div className="rw-subline">Persönliche Rap-Reim-Bibliothek</div>
        </div>
        <HeaderStats summary={summary} />
      </header>

      <main className="rw-shell">
        <div className="rw-workspace">
          <section className="rw-panel rw-search-panel">
            <div className="rw-panel-head">
              <div className="rw-title-group">
                <div className="rw-axis-switch" role="tablist" aria-label="Suchachse">
                  <AxisButton active={axis === "rhymes"} onClick={() => setAxis("rhymes")}>🎤 Reime</AxisButton>
                  <AxisButton active={axis === "meaning"} onClick={() => setAxis("meaning")}>💡 Bedeutung</AxisButton>
                </div>
                <h1 className="rw-title">{axis === "rhymes" ? "Reime trainieren" : "Bedeutung browsen"}</h1>
              </div>
              <div className="rw-status-line">
                {activeResponse ? `${activeCount} Treffer · ${activeTotal} Kandidaten` : "Bereit"}
              </div>
            </div>

            <div className="rw-mode-hint">{modeHint}</div>

            <div className="rw-main-searchbar">
              <input
                className="rw-query-input"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") runSearch();
                }}
                placeholder="z.B. einfach machen, schattenkabinett, bewusstsein"
                autoFocus
              />
              <button className="rw-primary-button" type="button" onClick={runSearch} disabled={loading}>
                {loading ? "Suche..." : "Suchen"}
              </button>
              {axis === "rhymes" && (
                <button className="rw-secondary-button" type="button" onClick={() => void searchRhymes()} disabled={loading || !rhymeResponse}>
                  Erneut ranken ↻
                </button>
              )}
            </div>

            <div className="rw-options-row">
              <label className="rw-number-option">
                <span>min. Score</span>
                <input
                  type="number"
                  min={0}
                  max={1}
                  step={0.05}
                  value={minScore}
                  onChange={(event) => setMinScore(clampMinScore(Number(event.target.value)))}
                />
              </label>
              <label className="rw-number-option">
                <span>Anzahl</span>
                <input
                  type="number"
                  min={1}
                  max={100}
                  step={1}
                  value={limit}
                  onChange={(event) => setLimit(clampLimit(Number(event.target.value)))}
                />
              </label>
              <span className="rw-local-note">Kommentare bleiben lokal. Keine externen APIs.</span>
            </div>

            {axis === "rhymes" && (
              <div className="rw-learning-note">
                0-3 = schlecht/kein Reim · 4-7 = ok · 8-10 = stark. Bewertungen ziehen ähnliche Muster mit; "Erneut ranken" zeigt den Lerneffekt.
              </div>
            )}

            {error && <div className="rw-error-box">{error}</div>}

            {axis === "rhymes" && rhymeResponse && (
              <>
                <div className="rw-meta-row">
                  <span>{rhymeResponse.results.length} Reim-Treffer für <b>{rhymeResponse.query}</b></span>
                  <span>
                    {rhymeResponse.retrieved_candidates ?? 0} geprüft
                    {rhymeResponse.rerank?.enabled ? ` · Rerank ${rhymeResponse.rerank.provider}` : ""}
                  </span>
                </div>
                <div className="rw-result-grid">
                  {rhymeResponse.results.length > 0 ? (
                    rhymeResponse.results.map((row, index) => {
                      const key = resultKey(row);
                      return (
                        <RhymeCard
                          key={`${key}:${index}`}
                          row={row}
                          query={rhymeResponse.query}
                          pending={Boolean(pendingFeedback[key])}
                          saved={Boolean(savedFeedback[key])}
                          error={feedbackErrors[key]}
                          draftComment={comments[key] ?? row.feedback_comment ?? ""}
                          onCommentChange={(comment) => setComments((current) => ({ ...current, [key]: comment }))}
                          onFeedback={saveFeedback}
                        />
                      );
                    })
                  ) : (
                    <div className="rw-empty">Keine Reim-Treffer für diese Suche.</div>
                  )}
                </div>
              </>
            )}

            {axis === "meaning" && meaningResponse && (
              <>
                <div className="rw-meta-row">
                  <span>{meaningResponse.results.length} Bedeutungs-Treffer für <b>{meaningResponse.query}</b></span>
                  <span>Achse {meaningResponse.axis ?? "meaning"} · read-only</span>
                </div>
                <div className="rw-result-grid">
                  {meaningResponse.results.length > 0 ? (
                    meaningResponse.results.map((row, index) => (
                      <MeaningCard key={`${row.source_title}-${row.line_no}-${index}`} row={row} />
                    ))
                  ) : (
                    <div className="rw-empty">Keine thematischen Treffer für diese Suche.</div>
                  )}
                </div>
              </>
            )}

            {!activeResponse && !error && (
              <div className="rw-empty">Gib eine Phrase ein und starte die Suche.</div>
            )}
          </section>
        </div>

        <aside className="rw-side">
          <SummaryPanel
            summary={summary}
            loading={summaryLoading}
            error={summaryError}
            onRefresh={() => void loadSummary()}
            onImport={() => void importUserTexts()}
          />
          <section className="rw-side-panel">
            <h2 className="rw-side-title">API</h2>
            <div className="rw-api-stack">
              <span>{BACKEND_URL}</span>
              <span>Reime: /api/rhymes/user-texts/search</span>
              <span>Bedeutung: /api/rhymes/user-texts/search-meaning</span>
              <span>Feedback: /api/rhymes/user-texts/feedback</span>
            </div>
          </section>
          <SourcePanel summary={summary} />
        </aside>
      </main>
    </div>
  );
}
