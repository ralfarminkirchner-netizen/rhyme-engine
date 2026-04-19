import { useState, useCallback } from "react";
import { api } from "../api/client";
import type {
  Mode,
  PhoneticFeatures,
  RankedCandidate,
  RawWeights,
  SearchResponse,
} from "../types";

// ── Helpers ──────────────────────────────────────────────────────────────────

const MODE_LABELS: Record<Mode, string> = {
  strict:        "🎯 Strikt",
  balanced:      "⚖️  Balanced",
  dirty:         "〰️ Dirty",
  multisyllabic: "🔗 Multi",
  komposita:     "🧩 Komposita",
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

// ── Haupt-Komponente ──────────────────────────────────────────────────────────

export default function RhymeSearch() {
  const [query, setQuery]           = useState("Schattentanz");
  const [mode, setMode]             = useState<Mode>("balanced");
  const [response, setResponse]     = useState<SearchResponse | null>(null);
  const [loading, setLoading]       = useState(false);
  const [error, setError]           = useState<string | null>(null);
  const [weights, setWeights]       = useState<Partial<RawWeights>>({});

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

  return (
    <div style={s.root}>
      <h1 style={s.title}>🎵 Reim-Engine</h1>
      <p style={s.sub}>German Phonological Rhyme Search · Python Backend Port 8000</p>

      {/* ── Eingabe ── */}
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
};
