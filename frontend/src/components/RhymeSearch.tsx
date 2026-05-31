import { useState, useCallback, useEffect } from "react";
import { api } from "../api/client";
import type {
  HighlightSegment,
  Mode,
  PhoneticFeatures,
  PhraseRankResponse,
  PhraseRankResult,
  RankedCandidate,
  RhymeHighlightResponse,
  RawWeights,
  SearchResponse,
  UserRhymeResult,
  UserRhymeSearchResponse,
  UserTextSummary,
} from "../types";

// ── Helpers ──────────────────────────────────────────────────────────────────

const MODE_LABELS: Record<Mode, string> = {
  strict:        "🎯 Strikt",
  balanced:      "⚖️  Balanced",
  dirty:         "〰️ Dirty",
  multisyllabic: "🔗 Multi",
  hardcore:      "💎 Hardcore",
  endRhyme:      "🏁 Endreim",
};

function stressBar(pat: number[]): string {
  return pat.map((s) => (s === 1 ? "█" : "░")).join("");
}

function scoreColor(s: number): string {
  if (s >= 0.85) return "#5fca5f";
  if (s >= 0.70) return "#f0c040";
  return "#ca6f5f";
}

// ── Query-Info-Box ────────────────────────────────────────────────────────────

function QueryInfo({
  feat,
  target,
}: {
  feat: PhoneticFeatures;
  target: "rhyme" | "terminal";
}) {
  // KERNUNTERSCHIED: Bei endRhyme zeigen wir terminal*, sonst rhyme*
  const isTerminal = target === "terminal";

  const activeVowels = isTerminal ? feat.terminalVowelSpine : feat.vowelSpine;
  const activeTail   = isTerminal ? feat.terminalTail       : feat.tail;
  const activeSpan   = isTerminal ? feat.terminalSpan       : feat.rhymeSpan;

  return (
    <div style={s.infoBox}>
      <span style={s.label}>Phonetik:</span>
      <span style={s.val}>[{feat.phonetic.join(" ")}]</span>
      <span style={s.label}>Silben:</span>
      <span style={s.val}>{feat.syllableCount}</span>
      <span style={s.label}>Stress:</span>
      <span style={s.val}>{stressBar(feat.stressPattern)}</span>
      <br />
      {isTerminal ? (
        <>
          <span style={s.dimLabel}>terminalSpan:</span>
          <span style={s.val}>[{activeSpan.join(",")}]</span>
          <span style={s.dimLabel}>terminalVowelSpine:</span>
          <span style={s.val}>[{activeVowels.join(",")}]</span>
          <span style={s.dimLabel}>terminalTail:</span>
          <span style={s.val}>[{activeTail.join(",")}]</span>
        </>
      ) : (
        <>
          <span style={s.dimLabel}>rhymeSpan:</span>
          <span style={s.val}>[{activeSpan.join(",")}]</span>
          <span style={s.dimLabel}>vowelSpine:</span>
          <span style={s.val}>[{activeVowels.join(",")}]</span>
          <span style={s.dimLabel}>tail:</span>
          <span style={s.val}>[{activeTail.join(",")}]</span>
        </>
      )}
    </div>
  );
}

// ── Ergebnis-Zeile ────────────────────────────────────────────────────────────

function CandidateRow({
  c,
  i,
  isTerminal,
}: {
  c: RankedCandidate;
  i: number;
  isTerminal: boolean;
}) {
  const vowels = isTerminal ? c.terminalVowelSpine : c.vowelSpine;
  const tail   = isTerminal ? c.terminalTail       : c.tail;

  return (
    <tr style={{ background: i % 2 === 0 ? "#0f0f0f" : "#121212" }}>
      <td style={s.td}>{i + 1}</td>
      <td style={{ ...s.td, fontWeight: 700, color: "#fff" }}>{c.text}</td>
      <td style={s.td}>{c.syllableCount}</td>
      <td style={{ ...s.td, fontFamily: "monospace", color: "#888" }}>
        {stressBar(c.stressPattern)}
      </td>
      <td style={s.td}>
        {vowels.length > 0 ? vowels.join(" · ") : "–"}
      </td>
      <td style={s.td}>
        {tail.length > 0 ? tail.join("") : "–"}
      </td>
      <td style={s.td}>
        <span style={{ color: scoreColor(c.score), fontWeight: 700 }}>
          {c.score.toFixed(3)}
        </span>
      </td>
      <td style={{ ...s.td, fontSize: "0.75rem", color: "#555" }}>
        v{c.breakdown.vowelCore.toFixed(2)}
        {" "}t{c.breakdown.tail.toFixed(2)}
        {" "}s{c.breakdown.stress.toFixed(2)}
      </td>
    </tr>
  );
}

function PhraseRow({ r, i }: { r: PhraseRankResult; i: number }) {
  return (
    <tr style={{ background: i % 2 === 0 ? "#0f0f0f" : "#121212" }}>
      <td style={s.td}>{i + 1}</td>
      <td style={{ ...s.td, fontWeight: 700, color: "#fff" }}>{r.phrase}</td>
      <td style={s.td}>
        <span style={{ color: scoreColor(r.score), fontWeight: 700 }}>
          {r.score.toFixed(3)}
        </span>
      </td>
      <td style={s.td}>a{r.anchor.toFixed(2)}</td>
      <td style={s.td}>t{r.tail.toFixed(2)}</td>
      <td style={s.td}>v{r.vowel.toFixed(2)}</td>
      <td style={s.td}>c{r.cadence.toFixed(2)}</td>
      <td style={{ ...s.td, color: r.anchor_gated ? "#ca6f5f" : "#5fca5f" }}>
        {r.anchor_gated ? "Gate" : "OK"}
      </td>
      <td style={{ ...s.td, color: "#777", fontSize: "0.75rem" }}>{r.reason}</td>
    </tr>
  );
}

function UserRhymeRow({ r, i }: { r: UserRhymeResult; i: number }) {
  return (
    <tr style={{ background: i % 2 === 0 ? "#0f0f0f" : "#121212" }}>
      <td style={s.td}>{i + 1}</td>
      <td style={{ ...s.td, fontWeight: 700, color: "#fff" }}>{r.phrase}</td>
      <td style={s.td}>
        <span style={{ color: scoreColor(r.score), fontWeight: 700 }}>
          {r.score.toFixed(3)}
        </span>
      </td>
      <td style={s.td}>{r.syllable_count}</td>
      <td style={s.td}>{r.source_title}</td>
      <td style={s.td}>{r.line_no}</td>
      <td style={{ ...s.td, color: "#777", fontSize: "0.75rem" }}>{r.line_text}</td>
    </tr>
  );
}

function alpha(hex: string, value: string): string {
  return `${hex}${value}`;
}

function HighlightedSegment({ segment }: { segment: HighlightSegment }) {
  if (segment.kind !== "syllable") {
    return <span>{segment.text}</span>;
  }

  const hasColor = Boolean(segment.color);
  return (
    <span
      title={[
        segment.word ? `Wort: ${segment.word}` : null,
        segment.phonetic?.length ? `Phonetik: ${segment.phonetic.join(" ")}` : null,
        segment.rhyme_group ? `Gruppe: ${segment.rhyme_group}` : null,
        segment.accented ? "betont" : null,
        segment.terminal ? "terminal" : null,
      ].filter(Boolean).join(" · ")}
      style={{
        ...s.syllable,
        background: hasColor ? alpha(segment.color!, "33") : "transparent",
        color: hasColor ? "#fff" : segment.accented ? "#d7d7d7" : "#777",
        borderBottomColor: hasColor ? segment.color! : segment.accented ? "#555" : "transparent",
        boxShadow: hasColor ? `inset 0 -2px 0 ${segment.color}` : "none",
      }}
    >
      {segment.text}
    </span>
  );
}

function RhymeHeatmap({ analysis }: { analysis: RhymeHighlightResponse }) {
  return (
    <div>
      <div style={s.meta}>
        {analysis.colored_syllable_count} farbige Silben ·{" "}
        {analysis.accented_syllable_count} betonte Silben ·{" "}
        {analysis.rhyme_groups.length} Reimgruppen
      </div>
      <div style={s.legend}>
        {analysis.rhyme_groups.slice(0, 18).map((group) => (
          <span key={group.key} style={s.legendItem}>
            <span style={{ ...s.legendSwatch, background: group.color }} />
            {group.key} ({group.count})
          </span>
        ))}
      </div>
      <div style={s.heatmap}>
        {analysis.lines.map((line) => (
          <div
            key={line.raw_index}
            style={{
              ...s.highlightLine,
              opacity: line.is_lyric || line.raw.trim() === "" ? 1 : 0.55,
              color: line.is_lyric ? "#ddd" : "#777",
            }}
          >
            <span style={s.lineNo}>{line.lyric_index ?? ""}</span>
            <span>
              {line.segments.map((segment, i) => (
                <HighlightedSegment key={`${line.raw_index}-${i}`} segment={segment} />
              ))}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Haupt-Komponente ──────────────────────────────────────────────────────────

export default function RhymeSearch() {
  const [query, setQuery]           = useState("Schattentanz");
  const [mode, setMode]             = useState<Mode>("balanced");
  const [response, setResponse]     = useState<SearchResponse | null>(null);
  const [loading, setLoading]       = useState(false);
  const [error, setError]           = useState<string | null>(null);
  const [weights, setWeights]       = useState<Partial<RawWeights>>({});
  const [phraseQuery, setPhraseQuery] = useState("wach lieg im Bett");
  const [phraseCandidates, setPhraseCandidates] = useState(
    [
      "Wackelndes Brett",
      "Wachstum verlässt",
      "Aktienregress",
      "Plastikbesteck",
      "Schattengewächs",
      "straff wie ein Netz",
      "schattungsgesetz",
      "aktienkapitals",
    ].join("\n")
  );
  const [phraseResponse, setPhraseResponse] = useState<PhraseRankResponse | null>(null);
  const [phraseLoading, setPhraseLoading] = useState(false);
  const [phraseError, setPhraseError] = useState<string | null>(null);
  const [highlightText, setHighlightText] = useState("");
  const [highlightResponse, setHighlightResponse] = useState<RhymeHighlightResponse | null>(null);
  const [highlightLoading, setHighlightLoading] = useState(false);
  const [highlightError, setHighlightError] = useState<string | null>(null);
  const [contextRadius, setContextRadius] = useState(6);
  const [userSummary, setUserSummary] = useState<UserTextSummary | null>(null);
  const [userImporting, setUserImporting] = useState(false);
  const [userTextError, setUserTextError] = useState<string | null>(null);
  const [userRhymeQuery, setUserRhymeQuery] = useState("wach lieg im Bett");
  const [userRhymeResponse, setUserRhymeResponse] = useState<UserRhymeSearchResponse | null>(null);
  const [userRhymeLoading, setUserRhymeLoading] = useState(false);

  const isTerminal = response?.target === "terminal";

  const search = useCallback(async () => {
    if (!query.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const res = await api.search({
        query,
        mode,
        weights: Object.keys(weights).length ? weights : undefined,
        limit: 30,
      });
      setResponse(res);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, [query, mode, weights]);

  const highlightRhymes = useCallback(async (textOverride?: string) => {
    const text = textOverride ?? highlightText;
    if (!text.trim()) return;
    setHighlightLoading(true);
    setHighlightError(null);
    try {
      const res = await api.highlightRhymes({ text, context_radius: contextRadius });
      setHighlightResponse(res);
    } catch (e) {
      setHighlightError(String(e));
    } finally {
      setHighlightLoading(false);
    }
  }, [highlightText, contextRadius]);

  useEffect(() => {
    let alive = true;
    api.rakiText()
      .then(async ({ text }) => {
        if (!alive) return;
        setHighlightText(text);
        const res = await api.highlightRhymes({ text, context_radius: 6 });
        if (!alive) return;
        setHighlightResponse(res);
      })
      .catch((e) => {
        if (alive) setHighlightError(String(e));
      });
    return () => { alive = false; };
  }, []);

  useEffect(() => {
    let alive = true;
    api.userTextSummary()
      .then((summary) => {
        if (alive) setUserSummary(summary);
      })
      .catch((e) => {
        if (alive) setUserTextError(String(e));
      });
    return () => { alive = false; };
  }, []);

  const importUserTexts = useCallback(async () => {
    setUserImporting(true);
    setUserTextError(null);
    try {
      const summary = await api.importUserTexts({
        prefer_pages_export: true,
        context_radius: 12,
      });
      setUserSummary(summary);
    } catch (e) {
      setUserTextError(String(e));
    } finally {
      setUserImporting(false);
    }
  }, []);

  const searchUserRhymes = useCallback(async () => {
    if (!userRhymeQuery.trim()) return;
    setUserRhymeLoading(true);
    setUserTextError(null);
    try {
      const res = await api.searchUserRhymes({
        query: userRhymeQuery,
        limit: 25,
        min_score: 0.45,
      });
      setUserRhymeResponse(res);
    } catch (e) {
      setUserTextError(String(e));
    } finally {
      setUserRhymeLoading(false);
    }
  }, [userRhymeQuery]);

  const rankPhrases = useCallback(async () => {
    const candidates = phraseCandidates
      .split(/\n|,/)
      .map((c) => c.trim())
      .filter(Boolean);
    if (!phraseQuery.trim() || candidates.length === 0) return;
    setPhraseLoading(true);
    setPhraseError(null);
    try {
      const res = await api.rankPhrases({ query: phraseQuery, candidates });
      setPhraseResponse(res);
    } catch (e) {
      setPhraseError(String(e));
    } finally {
      setPhraseLoading(false);
    }
  }, [phraseQuery, phraseCandidates]);

  return (
    <div style={s.root}>
      <h1 style={s.title}>🎵 Reim-Engine</h1>
      <p style={s.sub}>German Phonological Rhyme Search · Python Backend Port 8003</p>

      <section style={s.panelFirst}>
        <h2 style={s.sectionTitle}>Silben-Reimkarte</h2>
        <div style={s.mapControls}>
          <button style={s.searchBtn} onClick={() => highlightRhymes()}>
            {highlightLoading ? "⏳" : "Reime markieren"}
          </button>
          <label style={s.compactLabel}>
            Umgebung
            <input
              type="range"
              min={1}
              max={16}
              step={1}
              value={contextRadius}
              onChange={(e) => setContextRadius(parseInt(e.target.value, 10))}
            />
            <span style={s.wVal}>{contextRadius}</span>
          </label>
        </div>
        <textarea
          style={s.textarea}
          value={highlightText}
          onChange={(e) => setHighlightText(e.target.value)}
          rows={8}
        />
        {highlightError && <div style={s.errorBox}>⚠️ {highlightError}</div>}
        {highlightResponse && <RhymeHeatmap analysis={highlightResponse} />}
      </section>

      <section style={s.panel}>
        <h2 style={s.sectionTitle}>Deine Reimdatenbank</h2>
        <div style={s.mapControls}>
          <button style={s.searchBtn} onClick={importUserTexts}>
            {userImporting ? "Import läuft" : "Inbox importieren"}
          </button>
          <input
            style={s.input}
            value={userRhymeQuery}
            onChange={(e) => setUserRhymeQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && searchUserRhymes()}
          />
          <button style={s.searchBtn} onClick={searchUserRhymes}>
            {userRhymeLoading ? "Suche" : "DB suchen"}
          </button>
        </div>
        {userTextError && <div style={s.errorBox}>⚠️ {userTextError}</div>}
        {userSummary && (
          <>
            <div style={s.statGrid}>
              <div style={s.statBox}><b>{userSummary.imported_count}</b><span>Importe</span></div>
              <div style={s.statBox}><b>{userSummary.line_count}</b><span>Zeilen</span></div>
              <div style={s.statBox}><b>{userSummary.rhyme_unit_count}</b><span>3-8-Silben-Units</span></div>
              <div style={s.statBox}><b>{userSummary.rhyme_pair_count}</b><span>lokale Reimpaare</span></div>
            </div>
            {userSummary.documents.length > 0 && (
              <div style={s.docList}>
                {userSummary.documents.slice(0, 18).map((doc) => (
                  <span key={doc.source_id} style={s.docPill}>
                    {doc.title}: {doc.line_count}/{doc.rhyme_unit_count}
                  </span>
                ))}
              </div>
            )}
            {userSummary.sample_pairs.length > 0 && (
              <div style={s.samplePairs}>
                {userSummary.sample_pairs.slice(0, 8).map((pair, i) => (
                  <div key={`${pair.source_title}-${pair.left_line_no}-${pair.right_line_no}-${i}`} style={s.samplePair}>
                    <b>{pair.left_phrase}</b> / <b>{pair.right_phrase}</b>
                    <span>{pair.score.toFixed(3)} · {pair.source_title}</span>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
        {userRhymeResponse && (
          <>
            <div style={s.meta}>
              {userRhymeResponse.results.length} Treffer aus {userRhymeResponse.total_candidates} Units · Query:{" "}
              <b>{userRhymeResponse.query}</b>
            </div>
            <table style={s.table}>
              <thead>
                <tr>
                  {["#","Phrase","Score","Sil.","Quelle","Zeile","Kontext"].map((h) => (
                    <th key={h} style={s.th}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {userRhymeResponse.results.map((r, i) => (
                  <UserRhymeRow key={`${r.source_title}-${r.line_no}-${r.phrase}-${i}`} r={r} i={i} />
                ))}
              </tbody>
            </table>
          </>
        )}
      </section>

      {/* ── Eingabe ── */}
      <h2 style={s.sectionTitle}>Wortsuche</h2>
      <div style={s.row}>
        <input
          style={s.input}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && search()}
          placeholder="Wort eingeben … z.B. Täterintrojekte"
          autoFocus
        />
        <button style={s.searchBtn} onClick={search}>
          {loading ? "⏳" : "🔍 Suchen"}
        </button>
      </div>

      {/* ── Modus-Auswahl ── */}
      <div style={s.modeRow}>
        {(Object.keys(MODE_LABELS) as Mode[]).map((m) => (
          <button
            key={m}
            style={s.modeBtn(m === mode)}
            onClick={() => setMode(m)}
          >
            {MODE_LABELS[m]}
          </button>
        ))}
      </div>

      {/* ── Gewichte (kompakt) ── */}
      <details style={s.details}>
        <summary style={s.summary}>🎚️ Gewichte anpassen</summary>
        <div style={s.weightRow}>
          {(["stress","vowelCore","tail","syllableFlex"] as const).map((k) => (
            <label key={k} style={s.weightLabel}>
              <span style={s.wKey}>{k}</span>
              <input
                type="range" min={0} max={1} step={0.05}
                value={weights[k] ?? 0}
                onChange={(e) =>
                  setWeights((w) => ({ ...w, [k]: parseFloat(e.target.value) }))
                }
                style={{ width: 90 }}
              />
              <span style={s.wVal}>{(weights[k] ?? 0).toFixed(2)}</span>
            </label>
          ))}
          <button style={s.resetBtn} onClick={() => setWeights({})}>Reset</button>
        </div>
      </details>

      {/* ── Fehler ── */}
      {error && <div style={s.errorBox}>⚠️ {error}</div>}

      {/* ── Analyse-Info ── */}
      {response && (
        <>
          <QueryInfo feat={response.query} target={response.target} />

          <div style={s.meta}>
            {response.results.length} Treffer ·
            Modus: <b>{response.mode}</b> ·
            Target: <b style={{ color: isTerminal ? "#f0c040" : "#5fca5f" }}>
              {response.target}
            </b>
          </div>

          {/* ── Ergebnis-Tabelle ── */}
          {response.results.length > 0 ? (
            <table style={s.table}>
              <thead>
                <tr>
                  {["#","Wort","Sil.","Stress",
                    isTerminal ? "terminalVowelSpine" : "vowelSpine",
                    isTerminal ? "terminalTail"       : "tail",
                    "Score","Detail"
                  ].map((h) => (
                    <th key={h} style={s.th}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {response.results.map((c, i) => (
                  <CandidateRow key={c.text} c={c} i={i} isTerminal={isTerminal} />
                ))}
              </tbody>
            </table>
          ) : (
            <div style={s.noResults}>
              Keine Treffer für diesen Modus. Versuche "Dirty" oder "Balanced".
            </div>
          )}
        </>
      )}

      <section style={s.panel}>
        <h2 style={s.sectionTitle}>Phrase-Ranker</h2>
        <div style={s.phraseGrid}>
          <label style={s.fieldLabel}>
            Query
            <input
              style={s.input}
              value={phraseQuery}
              onChange={(e) => setPhraseQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && rankPhrases()}
            />
          </label>
          <label style={s.fieldLabel}>
            Kandidaten
            <textarea
              style={s.textarea}
              value={phraseCandidates}
              onChange={(e) => setPhraseCandidates(e.target.value)}
              rows={8}
            />
          </label>
        </div>
        <button style={s.searchBtn} onClick={rankPhrases}>
          {phraseLoading ? "⏳" : "Phrasen ranken"}
        </button>

        {phraseError && <div style={s.errorBox}>⚠️ {phraseError}</div>}

        {phraseResponse && (
          <>
            <div style={s.meta}>
              {phraseResponse.ranked.length} Kandidaten · Query:{" "}
              <b>{phraseResponse.query}</b>
            </div>
            <table style={s.table}>
              <thead>
                <tr>
                  {["#","Phrase","Score","Anchor","Tail","Vowel","Cadence","Gate","Grund"].map((h) => (
                    <th key={h} style={s.th}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {phraseResponse.ranked.map((r, i) => (
                  <PhraseRow key={`${r.phrase}-${i}`} r={r} i={i} />
                ))}
              </tbody>
            </table>
          </>
        )}
      </section>
    </div>
  );
}

// ── Styles ────────────────────────────────────────────────────────────────────

const s = {
  root: {
    fontFamily: "'JetBrains Mono','Fira Code',monospace",
    maxWidth: 960,
    margin: "0 auto",
    padding: "2rem 1rem",
    background: "#0d0d0d",
    color: "#e8e8e8",
    minHeight: "100vh",
  } as React.CSSProperties,
  title: { fontSize: "1.8rem", color: "#f0c040", marginBottom: 4 } as React.CSSProperties,
  sub: { color: "#555", fontSize: "0.8rem", marginBottom: "1.5rem" } as React.CSSProperties,
  sectionTitle: {
    color: "#ddd", fontSize: "1rem", margin: "0 0 0.6rem 0",
  } as React.CSSProperties,
  row: { display: "flex", gap: "0.5rem", marginBottom: "0.75rem" } as React.CSSProperties,
  input: {
    flex: 1, padding: "0.7rem 1rem", fontSize: "1.1rem",
    background: "#1a1a1a", border: "1px solid #444",
    borderRadius: 6, color: "#fff", outline: "none",
  } as React.CSSProperties,
  searchBtn: {
    padding: "0.7rem 1.4rem", background: "#f0c040",
    color: "#0d0d0d", border: "none", borderRadius: 6,
    cursor: "pointer", fontWeight: 700,
  } as React.CSSProperties,
  modeRow: { display: "flex", flexWrap: "wrap" as const, gap: "0.4rem", marginBottom: "0.75rem" },
  modeBtn: (active: boolean) => ({
    padding: "0.3rem 0.8rem",
    background: active ? "#f0c040" : "#1a1a1a",
    color: active ? "#0d0d0d" : "#888",
    border: `1px solid ${active ? "#f0c040" : "#333"}`,
    borderRadius: 4, cursor: "pointer", fontSize: "0.82rem",
    fontWeight: active ? 700 : 400,
  }) as React.CSSProperties,
  details: { marginBottom: "0.75rem" } as React.CSSProperties,
  summary: { color: "#666", cursor: "pointer", fontSize: "0.85rem" } as React.CSSProperties,
  weightRow: { display: "flex", flexWrap: "wrap" as const, gap: "0.5rem", marginTop: "0.5rem" },
  weightLabel: { display: "flex", alignItems: "center", gap: "0.3rem", fontSize: "0.8rem" } as React.CSSProperties,
  wKey: { color: "#888", minWidth: 90 } as React.CSSProperties,
  wVal: { color: "#f0c040", minWidth: 32, textAlign: "right" as const },
  resetBtn: {
    padding: "0.2rem 0.6rem", background: "#1a1a1a",
    color: "#888", border: "1px solid #333", borderRadius: 4,
    cursor: "pointer", fontSize: "0.8rem",
  } as React.CSSProperties,
  errorBox: {
    color: "#ca5f5f", background: "#1a0000",
    border: "1px solid #5a1a1a", borderRadius: 6,
    padding: "0.75rem 1rem", marginBottom: "0.75rem",
  } as React.CSSProperties,
  infoBox: {
    background: "#111", border: "1px solid #2a2a2a",
    borderRadius: 6, padding: "0.6rem 1rem",
    marginBottom: "0.75rem", fontSize: "0.82rem", lineHeight: 1.8,
  } as React.CSSProperties,
  label: { color: "#888", marginRight: "0.3rem" } as React.CSSProperties,
  dimLabel: { color: "#555", marginRight: "0.3rem", fontSize: "0.78rem" } as React.CSSProperties,
  val: { color: "#e0c060", marginRight: "1.2rem" } as React.CSSProperties,
  meta: { color: "#555", fontSize: "0.8rem", marginBottom: "0.5rem" } as React.CSSProperties,
  table: { width: "100%", borderCollapse: "collapse" as const, fontSize: "0.83rem" },
  th: {
    textAlign: "left" as const, padding: "0.35rem 0.6rem",
    borderBottom: "1px solid #2a2a2a", color: "#888", fontWeight: 500,
  },
  td: { padding: "0.35rem 0.6rem", borderBottom: "1px solid #1a1a1a", color: "#ccc" },
  noResults: { color: "#555", padding: "1rem" } as React.CSSProperties,
  panelFirst: {
    marginBottom: "2rem", paddingBottom: "1rem",
    borderBottom: "1px solid #242424",
  } as React.CSSProperties,
  panel: {
    marginTop: "2rem", paddingTop: "1rem",
    borderTop: "1px solid #242424",
  } as React.CSSProperties,
  mapControls: {
    display: "flex",
    alignItems: "center",
    gap: "0.75rem",
    marginBottom: "0.75rem",
    flexWrap: "wrap" as const,
  } as React.CSSProperties,
  statGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(135px, 1fr))",
    gap: "0.5rem",
    marginBottom: "0.75rem",
  } as React.CSSProperties,
  statBox: {
    display: "flex",
    flexDirection: "column" as const,
    gap: "0.15rem",
    background: "#111",
    border: "1px solid #2a2a2a",
    borderRadius: 6,
    padding: "0.6rem 0.75rem",
    color: "#777",
    fontSize: "0.76rem",
  } as React.CSSProperties,
  docList: {
    display: "flex",
    flexWrap: "wrap" as const,
    gap: "0.4rem",
    marginBottom: "0.75rem",
  } as React.CSSProperties,
  docPill: {
    border: "1px solid #333",
    borderRadius: 4,
    padding: "0.25rem 0.45rem",
    color: "#888",
    background: "#111",
    fontSize: "0.72rem",
  } as React.CSSProperties,
  samplePairs: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
    gap: "0.45rem",
    marginBottom: "0.75rem",
  } as React.CSSProperties,
  samplePair: {
    display: "flex",
    flexDirection: "column" as const,
    gap: "0.2rem",
    background: "#111",
    border: "1px solid #2a2a2a",
    borderRadius: 6,
    padding: "0.55rem 0.65rem",
    color: "#ccc",
    fontSize: "0.75rem",
  } as React.CSSProperties,
  compactLabel: {
    display: "flex",
    alignItems: "center",
    gap: "0.45rem",
    color: "#888",
    fontSize: "0.8rem",
  } as React.CSSProperties,
  heatmap: {
    marginTop: "0.75rem",
    background: "#111",
    border: "1px solid #2a2a2a",
    borderRadius: 6,
    padding: "0.75rem 0",
    overflowX: "auto" as const,
  } as React.CSSProperties,
  highlightLine: {
    display: "flex",
    gap: "0.75rem",
    minHeight: "1.55rem",
    lineHeight: 1.65,
    whiteSpace: "pre-wrap" as const,
    padding: "0 0.85rem",
  } as React.CSSProperties,
  lineNo: {
    flex: "0 0 2.2rem",
    color: "#555",
    textAlign: "right" as const,
    userSelect: "none" as const,
  } as React.CSSProperties,
  syllable: {
    borderBottom: "2px solid transparent",
    borderRadius: 3,
    padding: "0 1px",
  } as React.CSSProperties,
  legend: {
    display: "flex",
    flexWrap: "wrap" as const,
    gap: "0.45rem 0.7rem",
    margin: "0.5rem 0",
  } as React.CSSProperties,
  legendItem: {
    display: "inline-flex",
    alignItems: "center",
    gap: "0.3rem",
    color: "#777",
    fontSize: "0.74rem",
  } as React.CSSProperties,
  legendSwatch: {
    width: 10,
    height: 10,
    borderRadius: 2,
    display: "inline-block",
  } as React.CSSProperties,
  phraseGrid: {
    display: "grid",
    gridTemplateColumns: "minmax(220px, 0.7fr) minmax(260px, 1.3fr)",
    gap: "0.75rem",
    marginBottom: "0.75rem",
  } as React.CSSProperties,
  fieldLabel: {
    display: "flex",
    flexDirection: "column" as const,
    gap: "0.35rem",
    color: "#888",
    fontSize: "0.8rem",
  } as React.CSSProperties,
  textarea: {
    width: "100%", boxSizing: "border-box" as const,
    padding: "0.7rem 1rem", fontSize: "0.95rem",
    background: "#1a1a1a", border: "1px solid #444",
    borderRadius: 6, color: "#fff", outline: "none",
    fontFamily: "'JetBrains Mono','Fira Code',monospace",
    resize: "vertical" as const,
  } as React.CSSProperties,
};
