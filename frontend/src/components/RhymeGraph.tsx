import { useEffect, useMemo, useState } from "react";
import { rhymeGraphApi } from "../api/rhymeGraph";
import type {
  GraphBuildRequest, GraphDecision, GraphEdge, GraphFeedback, GraphNode,
  GraphSessionSummary, GraphSourceContext, PronunciationOverride, RhymeGraphResponse,
} from "../types/rhymeGraph";

const INITIAL: GraphBuildRequest = {
  text: "", mode: "balanced", min_syllables: 3, max_syllables: 8,
  max_syllable_delta: 1, include_internal: true, min_similarity: 0.67,
  max_nodes: 120, max_edges: 180, overrides: [],
  include_library: false, library_query: "", library_limit: 12,
};
// Deliberately generic, newly written examples. No personal archive material.
const EXAMPLE = "Wir wandern durch die Nacht\nDie andern sind erwacht\nIm Garten warten leise Fragen\nWir starten an den freien Tagen";
const KIND = { clean: "Enger Reim", slant: "Unreiner Reim", flex: "Silbenflex" };
const edgeLabel = (edge: GraphEdge) => edge.basis === "rap_pattern" ? "Mehrsilbiger Rap-Reim" : KIND[edge.kind];
function profileMeasures(edge: GraphEdge): [string, number][] {
  const values: [string, number][] = [
    ["Anker", edge.profile.anchor], ["Schluss", edge.profile.terminal], ["Vokale", edge.profile.vowels],
    ["Konsonanten", edge.profile.consonants], ["Betonung", edge.profile.stress], ["Abdeckung", edge.profile.coverage],
  ];
  if (edge.basis === "rap_pattern") {
    if (typeof edge.profile.rap_anchors === "number") values.push(["Klanganker", edge.profile.rap_anchors]);
    if (typeof edge.profile.consonant_grip === "number") values.push(["Konsonantgriff", edge.profile.consonant_grip]);
  }
  return values;
}
const DECISION: Record<GraphDecision, string> = { accepted: "Angenommen", experiment: "Als Versuch behalten", rejected: "Verworfen" };
type Draft = Omit<GraphFeedback, "edge_id" | "decision"> & { decision: GraphDecision | "" };
const EMPTY_DRAFT: Draft = { decision: "", heard: false, comment: "", performance_note: "", meaning_note: "" };
const errorText = (error: unknown) => error instanceof Error ? error.message : String(error);
const number = (value: number) => Number.isFinite(value) ? value.toFixed(2) : "–";
const clip = (text: string, length = 25) => text.length > length ? `${text.slice(0, length - 1)}…` : text;
const syllable = (node: GraphNode, index: number | null) => index === null ? "∅" : (node.phonetic_syllables[index] ?? []).join(" ");
const sourceLabel = (node: GraphNode) => node.source?.source_title
  ? `${node.source.source_title} · Zeile ${node.source.line_no ?? node.line_index + 1}`
  : `Eingabe · Zeile ${node.line_index + 1}`;

function SourceExcerpt({ graph, node }: { graph: RhymeGraphResponse; node: GraphNode }) {
  const line = graph.lines.find((candidate) => candidate.line_index === node.line_index);
  if (!line) return <p>{node.source?.line_text ?? node.text}</p>;
  const chars = Array.from(line.text);
  const start = Math.max(0, node.char_start - line.char_start);
  const end = Math.max(start, node.char_end - line.char_start);
  return <p className="rwg-source-excerpt">{chars.slice(0, start).join("")}<mark>{chars.slice(start, end).join("")}</mark>{chars.slice(end).join("")}</p>;
}

function GraphCanvas({ graph, selected, onSelect }: {
  graph: RhymeGraphResponse; selected: string; onSelect: (id: string) => void;
}) {
  const [limit, setLimit] = useState(12);
  const visibleEdges = useMemo(() => {
    const result = graph.edges.slice(0, limit);
    const active = graph.edges.find((edge) => edge.id === selected);
    if (active && !result.some((edge) => edge.id === selected)) result.push(active);
    return result;
  }, [graph.edges, selected, limit]);
  const ids = new Set(visibleEdges.flatMap((edge) => [edge.source, edge.target]));
  const nodes = graph.nodes.filter((node) => ids.has(node.id));
  const lineIndices = [...new Set(nodes.map((node) => node.line_index))].sort((a, b) => a - b);
  const compact = nodes.length <= 12 && nodes.length === lineIndices.length;
  const compactColumns = Math.min(3, Math.max(1, nodes.length));
  const compactRows = Math.ceil(nodes.length / compactColumns);
  const positions = new Map<string, { x: number; y: number }>();
  let maxRows = 1;
  for (const [column, lineIndex] of lineIndices.entries()) {
    const group = nodes.filter((node) => node.line_index === lineIndex);
    maxRows = Math.max(maxRows, group.length);
    group.forEach((node, row) => positions.set(node.id, compact
      ? { x: (column % compactColumns + .5) * (780 / compactColumns), y: 110 + Math.floor(column / compactColumns) * 190 }
      : { x: 135 + column * 260, y: 78 + row * 72 }));
  }
  const canvasWidth = compact ? 780 : Math.max(780, lineIndices.length * 260 + 20);
  const canvasHeight = compact ? Math.max(300, compactRows * 190 + 40) : Math.max(300, maxRows * 72 + 65);
  const active = graph.edges.find((edge) => edge.id === selected);
  return <section className="rwg-map-section" aria-label="Berechneter Reimgraph">
    <div className="rwg-section-top">
      <div><h2>Klangverbindungen</h2><p>{visibleEdges.length} von {graph.edges.length} Beziehungen im Bild · alle darunter auswählbar</p></div>
      <label className="rwg-inline-label">Im Bild <select value={limit} onChange={(event) => setLimit(Number(event.target.value))}>
        <option value={12}>12 Beziehungen</option><option value={24}>24 Beziehungen</option><option value={180}>Alle Beziehungen</option>
      </select></label>
    </div>
    <div className="rwg-map-scroll" tabIndex={0} aria-label="Graph, bei Bedarf horizontal und vertikal verschiebbar">
      <svg width={canvasWidth} height={canvasHeight} role="group" aria-label={compact ? "Kompakter Reimgraph; jeder Knoten nennt seine Quellzeile, gekrümmte Linien zeigen berechnete Beziehungen" : "Reimsegmente nach Quellzeile; Linien zeigen berechnete Beziehungen"}>
        {!compact && lineIndices.map((lineIndex, column) => <g key={lineIndex}>
          <rect className="rwg-lane" x={15 + column * 260} y={8} width={240} height={Math.max(280, maxRows * 72 + 45)} rx={12} />
          <text className="rwg-lane-label" x={135 + column * 260} y={35} textAnchor="middle">Zeile {lineIndex + 1}</text>
        </g>)}
        {visibleEdges.map((edge, edgeIndex) => {
          const left = positions.get(edge.source); const right = positions.get(edge.target);
          if (!left || !right) return null;
          const distance = Math.hypot(right.x - left.x, right.y - left.y) || 1;
          // Clear the middle node when an arc spans a complete three-node row.
          const bend = (100 + (edgeIndex % 4) * 24) * (edgeIndex % 2 === 0 ? -1 : 1);
          const controlX = (left.x + right.x) / 2 - (right.y - left.y) / distance * bend;
          const controlY = (left.y + right.y) / 2 + (right.x - left.x) / distance * bend;
          const path = compact
            ? `M${left.x},${left.y} Q${controlX},${controlY} ${right.x},${right.y}`
            : left.x === right.x
            ? `M${left.x},${left.y} C${left.x + 145},${left.y} ${right.x + 145},${right.y} ${right.x},${right.y}`
            : `M${left.x},${left.y} C${(left.x + right.x) / 2},${left.y} ${(left.x + right.x) / 2},${right.y} ${right.x},${right.y}`;
          const label = `${edgeLabel(edge)}: ${graph.nodes.find((node) => node.id === edge.source)?.text} – ${graph.nodes.find((node) => node.id === edge.target)?.text}`;
          return <g key={edge.id} className={`rwg-link rwg-link-${edge.kind} ${edge.id === selected ? "is-selected" : ""}`} role="button" tabIndex={0} aria-label={label} aria-pressed={edge.id === selected}
            onClick={() => onSelect(edge.id)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); onSelect(edge.id); } }}>
            <title>{label}</title><path className="rwg-link-hit" d={path} /><path className="rwg-link-line" d={path} />
          </g>;
        })}
        {nodes.map((node) => {
          const point = positions.get(node.id)!;
          const chosen = active?.source === node.id || active?.target === node.id;
          const edge = visibleEdges.find((candidate) => candidate.source === node.id || candidate.target === node.id);
          return <g key={node.id} className={`rwg-node ${chosen ? "is-selected" : ""}`} transform={`translate(${point.x},${point.y})`} role="button" tabIndex={0}
            aria-label={`${node.text}, ${sourceLabel(node)}, ${node.phonetic_syllables.length} Silben; Beziehung öffnen`}
            onClick={() => edge && onSelect(edge.id)} onKeyDown={(event) => { if (edge && (event.key === "Enter" || event.key === " ")) { event.preventDefault(); onSelect(edge.id); } }}>
            <title>{node.text} · {sourceLabel(node)}</title>{compact && <text className="rwg-lane-label" textAnchor="middle" y={-38}>Zeile {node.line_index + 1}</text>}<rect x={-108} y={-24} width={216} height={49} rx={8} />
            <text textAnchor="middle" y={-3}>{clip(node.text)}</text><text className="rwg-node-meta" textAnchor="middle" y={14}>{node.phonetic_syllables.length} Silben · {node.kind === "terminal" ? "Ende" : "Binnen"}{node.origin === "manual" ? " · korrigiert" : ""}</text>
          </g>;
        })}
      </svg>
    </div>
    <div className="rwg-legend"><span className="rwg-dot-clean">Enger Reim</span><span className="rwg-dot-slant">Unreiner Reim</span><span className="rwg-dot-flex">Silbenflex</span></div>
  </section>;
}

function PronunciationEditor({ graph, disabled, onApply }: {
  graph: RhymeGraphResponse; disabled: boolean; onApply: (override: PronunciationOverride) => Promise<void>;
}) {
  const words = graph.lines.flatMap((line) => line.words.map((word) => ({ line, word, key: `${line.line_index}:${word.word_index}` })));
  const [key, setKey] = useState("");
  const [sounds, setSounds] = useState(""); const [stress, setStress] = useState(""); const [error, setError] = useState("");
  const chosen = words.find((entry) => entry.key === key) ?? words[0];
  useEffect(() => {
    if (chosen) { setSounds(chosen.word.phonetic_syllables.map((tokens) => tokens.join(" ")).join(" | ")); setStress(chosen.word.stress.join(" ")); }
    setError("");
  }, [key, graph]);
  async function apply() {
    if (!chosen) return;
    const parts = sounds.split("|").map((part) => part.trim());
    const accents = stress.trim().split(/[\s,]+/u).map(Number);
    if (parts.some((part) => !part) || !sounds.trim()) { setError("Jede Silbe braucht mindestens einen Laut. Silben mit | trennen."); return; }
    if (accents.length !== parts.length || accents.some((value) => value !== 0 && value !== 1)) { setError("Für jede Silbe genau eine Betonung angeben: 0 oder 1."); return; }
    setError("");
    await onApply({ line_index: chosen.line.line_index, word_index: chosen.word.word_index, word_text: chosen.word.text, syllables: parts.map((part) => part.split(/\s+/u)), stress: accents });
  }
  return <details className="rwg-pronunciation"><summary>Aussprache korrigieren <span>Wörter, Laute und Betonung</span></summary>
    <div className="rwg-pronunciation-body">
      <p>Die Lautanalyse ist ein regelbasierter Vorschlag. Trenne Lauttokens mit Leerzeichen und Silben mit <code>|</code>. Die Korrektur erzeugt eine neue Analyse.</p>
      <label>Wort <select value={chosen?.key ?? ""} disabled={disabled} onChange={(event) => setKey(event.target.value)}>{words.map((entry) => <option key={entry.key} value={entry.key}>Zeile {entry.line.line_index + 1} · Wort {entry.word.word_index + 1}: {entry.word.text}</option>)}</select></label>
      <div className="rwg-form-grid"><label>Laute je Silbe <input value={sounds} disabled={disabled} onChange={(event) => setSounds(event.target.value)} placeholder="n aː | z ə" /></label>
        <label>Betonung je Silbe <input value={stress} disabled={disabled} onChange={(event) => setStress(event.target.value)} placeholder="1 0" /></label></div>
      <button className="rw-secondary-button" type="button" disabled={disabled || !chosen} onClick={() => void apply()}>Korrektur übernehmen & neu berechnen</button>
      {error && <p className="rwg-error" role="alert">{error}</p>}
    </div>
  </details>;
}

export default function RhymeGraph() {
  const [request, setRequest] = useState<GraphBuildRequest>(INITIAL);
  const [analyzedRequest, setAnalyzedRequest] = useState<GraphBuildRequest | null>(null);
  const [graph, setGraph] = useState<RhymeGraphResponse | null>(null);
  const [selected, setSelected] = useState(""); const [busy, setBusy] = useState(false);
  const [error, setError] = useState(""); const [notice, setNotice] = useState("");
  const [sessions, setSessions] = useState<GraphSessionSummary[]>([]); const [sessionId, setSessionId] = useState("");
  const [sessionChoice, setSessionChoice] = useState(""); const [sessionError, setSessionError] = useState("");
  const [title, setTitle] = useState(""); const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [feedback, setFeedback] = useState<Record<string, GraphFeedback>>({});
  const [feedbackHistory, setFeedbackHistory] = useState<GraphFeedback[]>([]);
  const [sourceContext, setSourceContext] = useState<GraphSourceContext | null>(null);
  const [sourceSnapshot, setSourceSnapshot] = useState("");
  const [edgeFilter, setEdgeFilter] = useState("all");
  const stale = Boolean(graph && analyzedRequest && JSON.stringify(request) !== JSON.stringify(analyzedRequest));
  const edge = graph?.edges.find((candidate) => candidate.id === selected);
  const left = graph?.nodes.find((node) => node.id === edge?.source); const right = graph?.nodes.find((node) => node.id === edge?.target);
  const draft = drafts[selected] ?? feedback[selected] ?? EMPTY_DRAFT;
  const visibleEdges = graph?.edges.filter((candidate) => edgeFilter === "all" || (edgeFilter === "rap_pattern" ? candidate.basis === "rap_pattern" : candidate.kind === edgeFilter)) ?? [];
  const analysisNotes = graph?.analysis_notes ?? [];
  const operationalWarnings = graph?.warnings.filter((warning) => !analysisNotes.includes(warning)) ?? [];

  async function refreshSessions() {
    try { setSessions((await rhymeGraphApi.sessions()).sessions); setSessionError(""); }
    catch (caught) { setSessionError(errorText(caught)); }
  }
  useEffect(() => { void refreshSessions(); }, []);
  useEffect(() => { setSourceContext(null); }, [selected]);
  function update<K extends keyof GraphBuildRequest>(key: K, value: GraphBuildRequest[K]) {
    setRequest((current) => ({ ...current, [key]: value })); setNotice("");
  }
  function updateDraft<K extends keyof Draft>(key: K, value: Draft[K]) {
    setDrafts((current) => ({ ...current, [selected]: { ...(current[selected] ?? feedback[selected] ?? EMPTY_DRAFT), [key]: value } })); setNotice("");
  }
  async function build(next = request) {
    setBusy(true); setError(""); setNotice("");
    try {
      const response = await rhymeGraphApi.build(next);
      setRequest(next); setGraph(response); setAnalyzedRequest(next); setSelected(response.edges[0]?.id ?? "");
      setSessionId(""); setFeedback({}); setFeedbackHistory([]); setDrafts({}); setEdgeFilter("all"); setSourceContext(null);
    } catch (caught) { setError(errorText(caught)); }
    finally { setBusy(false); }
  }
  async function saveSession() {
    if (!analyzedRequest || stale) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const result = await rhymeGraphApi.saveSession(title.trim() || "Reimgraph", analyzedRequest, graph?.fingerprint);
      setSessionId(result.id); setSessionChoice(result.id); setTitle(result.title);
      setGraph(result.graph); setFeedback(Object.fromEntries(result.feedback.map((item) => [item.edge_id, item])));
      setFeedbackHistory(result.feedback_history ?? result.feedback);
      setNotice("Session lokal gespeichert. Du kannst sie später wieder öffnen."); await refreshSessions();
    } catch (caught) { setError(errorText(caught)); }
    finally { setBusy(false); }
  }
  async function openSession() {
    if (!sessionChoice) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const result = await rhymeGraphApi.session(sessionChoice);
      const next = { ...INITIAL, ...result.request };
      setRequest(next); setAnalyzedRequest(next); setGraph(result.graph); setSessionId(result.id); setTitle(result.title);
      setFeedback(Object.fromEntries(result.feedback.map((item) => [item.edge_id, item]))); setDrafts({});
      setFeedbackHistory(result.feedback_history ?? result.feedback); setSourceContext(null);
      setSelected(result.graph.edges[0]?.id ?? ""); setEdgeFilter("all"); setNotice("Gespeicherte Analyse und persönliche Entscheidungen wieder geöffnet.");
    } catch (caught) { setError(errorText(caught)); }
    finally { setBusy(false); }
  }
  async function saveFeedback() {
    if (!sessionId || !edge || !draft.decision) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const result = await rhymeGraphApi.feedback(sessionId, { edge_id: edge.id, decision: draft.decision, heard: draft.heard, comment: draft.comment, performance_note: draft.performance_note, meaning_note: draft.meaning_note });
      setFeedback((current) => ({ ...current, [edge.id]: result })); setDrafts((current) => ({ ...current, [edge.id]: result }));
      setFeedbackHistory((current) => [...current, result]);
      setNotice("Deine Entscheidung wurde lokal gespeichert. Die technische Analyse bleibt getrennt.");
    } catch (caught) { setError(errorText(caught)); }
    finally { setBusy(false); }
  }
  async function jumpToSource(node: GraphNode) {
    if (node.source?.source_id && node.source.kind === "library") {
      setBusy(true); setError("");
      try {
        setSourceContext(await rhymeGraphApi.source(node.source.source_id, node.source.line_no ?? 1, node.source.line_hash));
        setSourceSnapshot(node.source.line_text ?? "");
      }
      catch (caught) { setError(errorText(caught)); }
      finally { setBusy(false); }
      return;
    }
    const target = document.getElementById(`rwg-source-${node.line_index}`);
    target?.scrollIntoView({ behavior: "smooth", block: "center" }); target?.focus({ preventScroll: true });
  }

  return <section className="rwg-workbench" aria-labelledby="rwg-title">
    <div className="rwg-hero"><div><span className="rwg-eyebrow">REiMWERK · Klang, Schrift & Vortrag</span><h1 id="rwg-title">Reime verbinden.</h1><p>Mehrsilbige Lautfolgen untersuchen, Abweichungen verstehen und deine Entscheidungen bewahren.</p></div><span className="rwg-local-badge">Lokal · ohne KI-Aufruf</span></div>
    <section className="rw-panel rwg-input-panel" aria-label="Text und Analysebedingungen">
      <div className="rwg-section-top"><div><h2>Deine Zeilen</h2><p>Originaltext bleibt erhalten. Aussprache und Beziehungen sind prüfbare Vorschläge.</p></div><button className="rw-quiet-button" type="button" disabled={busy} onClick={() => { update("text", EXAMPLE); update("overrides", []); }}>Beispiel laden</button></div>
      <label className="rwg-text-label" htmlFor="rwg-text">Mehrere Zeilen vergleichen</label>
      <textarea id="rwg-text" className="rwg-text" rows={6} value={request.text} maxLength={16000} disabled={busy} onChange={(event) => setRequest((current) => ({ ...current, text: event.target.value, overrides: [] }))} placeholder={"Gib eigene Zeilen ein.\nJede neue Zeile eröffnet einen weiteren Vergleich."} />
      <div className="rwg-mode-row" role="group" aria-label="Reimspielraum">{([
        ["strict", "Eng", "Enge Lautübereinstimmung"], ["balanced", "Beweglich", "Nähe und Abweichungen vergleichen"], ["dirty", "Dreckig", "Mehr klanglichen Spielraum zulassen"],
      ] as const).map(([mode, label, hint]) => <button key={mode} type="button" className={`rwg-mode ${request.mode === mode ? "is-active" : ""}`} aria-pressed={request.mode === mode} disabled={busy} onClick={() => update("mode", mode)}><strong>{label}</strong><span>{hint}</span></button>)}</div>
      <div className="rwg-controls"><label>Mindestens <input type="number" min={2} max={8} value={request.min_syllables} disabled={busy} onChange={(event) => { const value = Math.min(8, Math.max(2, Number(event.target.value))); setRequest((current) => ({ ...current, min_syllables: value, max_syllables: Math.max(value, current.max_syllables) })); }} /><span>Silben</span></label>
        <label>Höchstens <input type="number" min={request.min_syllables} max={12} value={request.max_syllables} disabled={busy} onChange={(event) => update("max_syllables", Math.min(12, Math.max(request.min_syllables, Number(event.target.value))))} /><span>Silben</span></label>
        <label>Silbenflex <select value={request.max_syllable_delta} disabled={busy} onChange={(event) => update("max_syllable_delta", Number(event.target.value))}><option value={0}>Gleiche Anzahl</option><option value={1}>± 1 Silbe</option><option value={2}>± 2 Silben</option></select></label>
        <label className="rwg-check"><input type="checkbox" checked={request.include_internal} disabled={busy} onChange={(event) => update("include_internal", event.target.checked)} />Binnenreime einbeziehen</label>
      </div>
      <details className="rwg-library-options"><summary>Persönliche Bibliothek einbeziehen</summary><div>
        <label className="rwg-check"><input type="checkbox" checked={request.include_library} disabled={busy} onChange={(event) => update("include_library", event.target.checked)} />Passende Archivstellen zusätzlich analysieren</label>
        <label>Bibliothekssuche <input value={request.library_query} disabled={busy || !request.include_library} onChange={(event) => update("library_query", event.target.value)} placeholder="Suchphrase, sonst erste Eingabezeile" /></label>
        <p>Es werden nur lokal vorhandene Bibliotheksstellen verwendet. Eine leere Bibliothek wird als solche ausgewiesen.</p>
      </div></details>
      <div className="rwg-build-row"><button className="rw-primary-button" type="button" disabled={busy || !request.text.trim()} onClick={() => void build()}>{busy ? "Arbeite …" : "Reimgraph berechnen"}<span aria-hidden="true"> ↗</span></button><span>Endreime immer · Binnenreime nach Auswahl · {request.overrides.length} Aussprachekorrekturen</span></div>
    </section>
    <section className="rw-panel rwg-session-panel" aria-label="Lokale Sessions"><div className="rwg-session-fields"><label>Gespeicherte Session <select aria-label="Gespeicherte Session" value={sessionChoice} disabled={busy} onChange={(event) => setSessionChoice(event.target.value)}><option value="">{sessions.length ? "Session auswählen" : "Noch keine gespeicherte Session"}</option>{sessions.map((session) => <option key={session.id} value={session.id}>{session.title} · {session.edge_count} Beziehungen</option>)}</select></label><button className="rw-quiet-button" type="button" disabled={busy || !sessionChoice} onClick={() => void openSession()}>Wieder öffnen</button><button className="rw-quiet-button" type="button" disabled={busy} onClick={() => void refreshSessions()} aria-label="Sessionliste aktualisieren">↻</button></div>
      {graph && <div className="rwg-session-fields"><label>Name für diese Analyse <input value={title} maxLength={120} disabled={busy} onChange={(event) => setTitle(event.target.value)} placeholder="Zum Beispiel: Strophe · erster Versuch" /></label><button className="rw-secondary-button" type="button" disabled={busy || stale} onClick={() => void saveSession()}>{sessionId ? "Als neue Session speichern" : "Session lokal speichern"}</button></div>}
      {sessionError && <p className="rwg-error" role="alert">{sessionError}</p>}
    </section>
    <div className="rwg-announcements" aria-live="polite">{notice && <p className="rwg-notice">{notice}</p>}{error && <p className="rwg-error" role="alert">{error}</p>}{stale && <p className="rwg-warning">Die Eingabe oder die Bedingungen wurden geändert. Der sichtbare Graph gehört noch zur vorherigen Analyse. Vor dem Speichern neu berechnen.</p>}</div>
    {!graph && <div className="rwg-start"><div className="rwg-start-symbol" aria-hidden="true">◌—◉—◌</div><h2>Vom Wort zum hörbaren Zusammenhang.</h2><p>Eine Verbindung zeigt, welche Laute tragen, wo Silben abweichen und welche Vortragsidee du selbst erproben kannst.</p><p>Beginne mit zwei oder mehr Zeilen oder lade das unverfängliche Beispiel.</p></div>}
    {graph && <>
      <div className="rwg-analysis-status"><strong>{graph.nodes.length} Segmente · {graph.edges.length} Beziehungen</strong><span>Regelbasierte Lautanalyse · {graph.version} · {sessionId ? "Session gespeichert" : "Noch nicht gespeichert"}</span></div>
      <p className="rwg-small">Aussprache und Betonung sind korrigierbare Vorschläge. Wie die Verbindung im Vortrag wirkt, entscheidest du beim Sprechen.</p>
      {Boolean(graph.analysis_notes?.length) && <details className="rwg-analysis-notes"><summary>Analysegrundlage und Grenzen</summary><div className="rwg-warnings">{graph.analysis_notes!.map((note, index) => <p key={index}>{note}</p>)}</div></details>}
      {operationalWarnings.length > 0 && <div className="rwg-warnings" role="status">{operationalWarnings.map((warning, index) => <p key={index}>{warning}</p>)}</div>}
      {graph.truncated && <p className="rwg-warning">Die Analyse ist begrenzt. Kürzere Ausschnitte können weitere Beziehungen sichtbar machen.</p>}
      {graph.edges.length > 0 ? <>
        <GraphCanvas graph={graph} selected={selected} onSelect={setSelected} />
        <div className="rwg-review-grid"><section className="rw-panel rwg-edge-list" aria-label="Alle berechneten Beziehungen"><div className="rwg-section-top"><h2>Beziehungen</h2><label className="rwg-inline-label">Ansicht <select value={edgeFilter} onChange={(event) => setEdgeFilter(event.target.value)}><option value="all">Alle</option><option value="rap_pattern">Mehrsilbiger Rap-Reim</option><option value="clean">Eng</option><option value="slant">Unrein</option><option value="flex">Silbenflex</option></select></label></div>
          <p className="rwg-small">Technisch vorgeschlagen. Deine Entscheidung bleibt unabhängig davon.</p>
          <div className="rwg-edge-buttons">{visibleEdges.map((candidate) => {
            const first = graph.nodes.find((node) => node.id === candidate.source); const second = graph.nodes.find((node) => node.id === candidate.target);
            return <button key={candidate.id} type="button" className={`rwg-edge-button ${candidate.id === selected ? "is-selected" : ""}`} aria-pressed={candidate.id === selected} onClick={() => setSelected(candidate.id)}><span className={`rwg-edge-kind rwg-dot-${candidate.kind}`}>{edgeLabel(candidate)}</span><strong>{first?.text} <span aria-hidden="true">↔</span> {second?.text}</strong><span>{first ? sourceLabel(first) : ""} / {second ? sourceLabel(second) : ""}</span>{feedback[candidate.id] && <em>{DECISION[feedback[candidate.id].decision]}{feedback[candidate.id].heard ? " · gehört" : ""}</em>}</button>;
          })}{visibleEdges.length === 0 && <p>Keine Beziehungen in dieser Ansicht.</p>}</div>
        </section>
        {edge && left && right && <section className="rw-panel rwg-edge-detail" aria-labelledby="rwg-edge-title"><span className={`rwg-edge-kind rwg-dot-${edge.kind}`}>{edgeLabel(edge)} · Vorschlag</span><h2 id="rwg-edge-title">{left.text}<span className="rwg-detail-arrow" aria-hidden="true">↕</span>{right.text}</h2>
          {edge.basis === "rap_pattern" && <p className="rwg-rap-explanation">Diese Verbindung wird als mehrsilbiges Rap-Muster geprüft. Welche Klanganker sie tragen und welche Laute abweichen, wird getrennt ausgewiesen.</p>}
          <div className="rwg-profile">{profileMeasures(edge).map(([label, value]) => <div key={label}><span>{label}</span><strong>{number(value)}</strong><meter min={0} max={1} value={value} aria-label={`${label}: ${number(value)}`} /></div>)}</div>
          <p className="rwg-small">Unabhängige Vergleichswerte von 0 bis 1. Sie bewerten weder die Aussage noch deine musikalische Gesamtwirkung.</p>
          <div className="rwg-alignment-scroll"><table className="rwg-alignment"><caption>Silbe für Silbe · ∅ bezeichnet eine Lücke</caption><thead><tr><th>Links</th><th>Rechts</th><th>Vokal</th><th>Auslaut</th><th>Akzent</th></tr></thead><tbody>{edge.alignment.map((pair, index) => <tr key={index} className={pair.left_index === null || pair.right_index === null ? "has-gap" : ""}><td><b>{pair.left_index === null ? "–" : pair.left_index + 1}</b> {syllable(left, pair.left_index)}</td><td><b>{pair.right_index === null ? "–" : pair.right_index + 1}</b> {syllable(right, pair.right_index)}</td><td>{number(pair.vowel_similarity)}</td><td>{number(pair.coda_similarity)}</td><td>{pair.stress_match ? "gleich" : "abweichend"}</td></tr>)}</tbody></table></div>
          {Boolean(edge.evidence?.length) && <section className="rwg-evidence" aria-label="Was die Verbindung trägt"><h3>Was die Verbindung trägt</h3><ul>{edge.evidence!.map((item, index) => <li key={index}>{item}</li>)}</ul></section>}
          {edge.deviations.length > 0 && <div className="rwg-deviations"><h3>Abweichungen</h3><ul>{edge.deviations.map((item, index) => <li key={index}>{item}</li>)}</ul></div>}
          <div className="rwg-performance"><h3>Im Vortrag erproben</h3>{edge.required_operations.length > 0 ? <ul>{edge.required_operations.map((item, index) => <li key={index}>{item}</li>)}</ul> : <p>Keine zusätzliche Vortragsoperation aus dieser Analyse abgeleitet.</p>}<p className="rwg-small">Vorschläge aus der Ausrichtung. Sprechbarkeit und Flow sind damit noch nicht bestätigt.</p></div>
          <div className="rwg-pair-sources">{[left, right].map((node, index) => <article key={`${node.id}-${index}`}><button className="rwg-source-link" type="button" disabled={busy} onClick={() => void jumpToSource(node)}>{sourceLabel(node)} ↗</button><SourceExcerpt graph={graph} node={node} /><span className="rwg-small">Silben {node.start_syllable + 1}–{node.end_syllable} · {node.origin === "manual" ? "Aussprache manuell korrigiert" : "Aussprache automatisch vorgeschlagen"}</span></article>)}</div>
          {sourceContext && <aside className="rwg-original-context" aria-label="Rückgelesener Originalkontext"><h3>{sourceContext.title}</h3>{sourceContext.matches_snapshot === false && <><p className="rwg-warning">Bibliotheksstelle inzwischen geändert. Der aktuelle Kontext entspricht nicht mehr dem gespeicherten Quellausschnitt.</p><p className="rwg-small">Gespeicherter Quellausschnitt:</p><p className="rwg-source-excerpt">{sourceSnapshot}</p></>}<p className="rwg-small">{sourceContext.matches_snapshot === false ? "Aktueller Bibliothekskontext" : "Rückgelesener Quellkontext"} · {sourceContext.extraction_method} · {sourceContext.status}</p><ol>{sourceContext.lines.map((line) => <li key={line.line_no} className={line.line_no === sourceContext.line_no ? "is-source-line" : ""}><span>{line.line_no}</span><p>{line.text}</p></li>)}</ol><details><summary>Quellenherkunft</summary><p className="rwg-small">{sourceContext.path}</p><p className="rwg-small">Quelle: {sourceContext.source_id}</p></details></aside>}
          <form className="rwg-feedback" onSubmit={(event) => { event.preventDefault(); void saveFeedback(); }}><h3>Deine Entscheidung</h3><label>Für diese Beziehung <select aria-label="Für diese Beziehung" value={draft.decision} disabled={busy || stale} onChange={(event) => updateDraft("decision", event.target.value as Draft["decision"])}><option value="">Noch nicht entschieden</option><option value="accepted">Angenommen</option><option value="experiment">Als Versuch behalten</option><option value="rejected">Verworfen</option></select></label><label className="rwg-check"><input type="checkbox" checked={draft.heard} disabled={busy || stale} onChange={(event) => updateDraft("heard", event.target.checked)} />Selbst gesprochen oder gehört</label><label>Kommentar <textarea aria-label="Kommentar" rows={2} maxLength={4000} value={draft.comment} disabled={busy || stale} onChange={(event) => updateDraft("comment", event.target.value)} placeholder="Was trägt, was wirkt erzwungen?" /></label><label>Vortragsnotiz <textarea aria-label="Vortragsnotiz" rows={2} maxLength={4000} value={draft.performance_note} disabled={busy || stale} onChange={(event) => updateDraft("performance_note", event.target.value)} placeholder="Zum Beispiel: zweite Silbe kürzer, danach Luft lassen" /></label><label>Bedeutungsbrücke <textarea aria-label="Bedeutungsbrücke" rows={2} maxLength={4000} value={draft.meaning_note} disabled={busy || stale} onChange={(event) => updateDraft("meaning_note", event.target.value)} placeholder="Welche Lesarten verbindet die Passage? Ist der Weg verständlich?" /></label><button className="rw-primary-button" type="submit" disabled={busy || stale || !sessionId || !draft.decision}>Entscheidung lokal speichern</button>{!sessionId && <p className="rwg-small">Speichere zuerst die Session, damit Entscheidung und konkrete Analyse verbunden bleiben.</p>}{feedback[edge.id] && <p className="rwg-notice">Gespeichert: {DECISION[feedback[edge.id].decision]} · {feedback[edge.id].heard ? "gehört" : "noch nicht als gehört markiert"}</p>}</form>
          {feedbackHistory.some((item) => item.edge_id === edge.id) && <details className="rwg-feedback-history"><summary>Frühere Entscheidungen zu dieser Beziehung</summary><ol>{feedbackHistory.filter((item) => item.edge_id === edge.id).map((item, index) => <li key={index}><strong>{DECISION[item.decision]}</strong><span>{item.heard ? " · gehört" : " · nicht als gehört markiert"}</span>{item.comment && <p>{item.comment}</p>}{item.performance_note && <p>Vortrag: {item.performance_note}</p>}{item.meaning_note && <p>Bedeutung: {item.meaning_note}</p>}</li>)}</ol></details>}
        </section>}
        </div>
      </> : <div className="rwg-start"><h2>Keine Beziehung unter diesen Bedingungen.</h2><p>Prüfe die Aussprache, ergänze passende Zeilen oder erlaube kürzere Segmente und mehr klanglichen Spielraum.</p></div>}
      <PronunciationEditor graph={graph} disabled={busy || stale} onApply={async (override) => { const next = { ...request, overrides: [...request.overrides.filter((item) => item.line_index !== override.line_index || item.word_index !== override.word_index), override] }; await build(next); }} />
      <section className="rw-panel rwg-sources" aria-label="Quellzeilen"><h2>Zurück zur Quelle</h2><p className="rwg-small">Die markierte Wortspanne enthält das Reimsegment. Bei Teilwörtern bestimmen die Silbenindizes oben den genauen Ausschnitt.</p><ol>{graph.lines.map((line) => { const node = graph.nodes.find((candidate) => candidate.line_index === line.line_index); return <li key={line.line_index} id={`rwg-source-${line.line_index}`} tabIndex={-1}><span>{node ? sourceLabel(node) : `Eingabe · Zeile ${line.line_index + 1}`}</span><p>{line.text || "(Leere Zeile)"}</p></li>; })}</ol></section>
    </>}
  </section>;
}
