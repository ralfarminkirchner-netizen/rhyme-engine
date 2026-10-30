import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { PointerEvent } from "react";
import { rhymeAtlasApi } from "../api/rhymeAtlas";
import type {
  AtlasCandidate, AtlasChain, AtlasChainMember, AtlasFilters, AtlasMap, AtlasNeighborhood,
  AtlasRegion, AtlasSearchResponse, AtlasStatus,
} from "../types/rhymeAtlas";

const INITIAL_FILTERS: AtlasFilters = {
  mode: "dirty", kind: "all", languages: ["de", "en"], min_syllables: 1,
  max_syllables: 32, origin: "all", include_combinations: true, limit: 40,
};
const FAMILY_COLORS: Record<string, string> = {
  a: "#e9b96c", e: "#c7d890", i: "#83cfb8", o: "#8ebde4", u: "#ab9ddd",
  oe: "#e5a1c5", ue: "#bc9ce1", ai: "#e3a875", au: "#b3c779", oi: "#82c9d3", ei: "#c2d8a0", ou: "#9aafe3", schwa: "#a7afa0",
};
const MAP_FAMILIES = ["a", "e", "i", "o", "u", "oe", "ue", "ai", "au", "oi", "ei", "ou", "schwa"];
const familyNames: Record<string, string> = { schwa: "ə", oe: "ö", ue: "ü", ai: "aɪ", au: "aʊ", oi: "ɔɪ", ei: "eɪ", ou: "oʊ" };
const count = (value: number | undefined) => new Intl.NumberFormat("de-DE").format(value ?? 0);
const errorText = (error: unknown) => error instanceof Error ? error.message : String(error);
const kindName = (kind: string) => ({ word: "Wort", compound: "Kompositum", phrase: "Wortfolge" }[kind] ?? kind);
const originName = (origin: string) => ({ dictionary: "Aussprachewörterbuch", dictionary_phrase: "Belegter Ausdruck", attested_phrase: "Belegte Wortfolge", constructed: "Neu zusammengesetzt", user: "Eigene Reimfolge" }[origin] ?? origin);
const labelFamily = (family: string) => familyNames[family] ?? family;
const color = (family: string) => FAMILY_COLORS[family] ?? "#c3b782";
const safeUrl = (url?: string) => url && /^https?:\/\//u.test(url) ? url : undefined;
const clamp = (value: number, min: number, max: number) => Math.max(min, Math.min(max, value));
const shorten = (text: string, length = 26) => text.length <= length ? text : `${text.slice(0, length - 1)}…`;
type DraftMember = { text: string; entry_id?: string | number };

function draftMembers(text: string, references: DraftMember[]): DraftMember[] {
  const remaining = [...references];
  return text.split("\n").map((line) => line.trim()).filter(Boolean).map((text) => {
    const index = remaining.findIndex((member) => member.text === text);
    const reference = index < 0 ? undefined : remaining.splice(index, 1)[0];
    return reference?.entry_id != null ? { text, entry_id: reference.entry_id } : { text };
  });
}

function familyOf(nucleus = ""): string {
  if (/eɪ/u.test(nucleus)) return "ei";
  if (/oʊ|əʊ/u.test(nucleus)) return "ou";
  if (/aɪ|aɪ̯/u.test(nucleus)) return "ai";
  if (/aʊ|aʊ̯/u.test(nucleus)) return "au";
  if (/ɔʏ|ɔɪ/u.test(nucleus)) return "oi";
  if (/[əɐɚɝ]/u.test(nucleus)) return "schwa";
  if (/[œø]/u.test(nucleus)) return "oe";
  if (/[ʏy]/u.test(nucleus)) return "ue";
  if (/[aɑɒæʌ]/u.test(nucleus)) return "a";
  if (/[eɛɜ]/u.test(nucleus)) return "e";
  if (/[iɪ]/u.test(nucleus)) return "i";
  if (/[oɔ]/u.test(nucleus)) return "o";
  if (/[uʊ]/u.test(nucleus)) return "u";
  return nucleus;
}

function AtlasLandscape({ map, filters, emptyMessage, selectedRegion, chain, selectedMember, highlighted, onRegion, onMember }: {
  map: AtlasMap | null; selectedRegion: string; chain: AtlasChain | null;
  filters: AtlasFilters; emptyMessage: string; selectedMember: number | null; highlighted: AtlasCandidate | null;
  onRegion: (region: AtlasRegion) => void; onMember: (member: AtlasChainMember, index: number) => void;
}) {
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [hovered, setHovered] = useState<string | null>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const drag = useRef<{ id: number; x: number; y: number; panX: number; panY: number } | null>(null);
  const moved = useRef(false);
  const regions = map?.regions ?? [];
  const maxPopulation = Math.max(1, ...regions.map((region) => region.count));
  const minSyllables = map?.min_syllables ?? filters.min_syllables;
  const maxSyllables = map?.max_syllables ?? filters.max_syllables;
  const singleLayer = minSyllables === maxSyllables;

  useEffect(() => { setZoom(1); setPan({ x: 0, y: 0 }); setHovered(null); }, [minSyllables, maxSyllables]);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && isFullscreen) {
        setIsFullscreen(false);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isFullscreen]);

  const level = (syllables: number) => (syllables - minSyllables) / Math.max(maxSyllables - minSyllables, 1);
  const point = (region: AtlasRegion) => ({ x: 85 + clamp(region.x, 0, 1) * 1110, y: 82 + clamp(region.y, 0, 1) * 570 });
  function locate(member: AtlasChainMember | AtlasCandidate) {
    const families = member.families ?? member.nuclei.map(familyOf);
    const region = regions.find((candidate) => candidate.syllables === member.syllable_count && candidate.first_family === families[0] && candidate.last_family === families[families.length - 1]);
    const familyPosition = (family: string) => Math.max(0, MAP_FAMILIES.indexOf(family)) / MAP_FAMILIES.length;
    const center = region ? point(region) : {
      x: 85 + (singleLayer ? .06 + .88 * familyPosition(families[0]) * MAP_FAMILIES.length / (MAP_FAMILIES.length - 1) : .04 + .70 * level(member.syllable_count) + .22 * familyPosition(families[0])) * 1110,
      y: 82 + (singleLayer ? .06 + .88 * familyPosition(families[families.length - 1]) * MAP_FAMILIES.length / (MAP_FAMILIES.length - 1) : .04 + .70 * level(member.syllable_count) + .22 * familyPosition(families[families.length - 1])) * 570,
    };
    const inner = member.nuclei.map((nucleus, index) => {
      const family = familyPosition(families[index] ?? familyOf(nucleus));
      const fine = [...nucleus].reduce((value, phone) => value + (phone.codePointAt(0) ?? 0), 0) % 19 / 19;
      return family * .8 + fine * .2;
    });
    const denominator = Math.sqrt(Math.max(1, inner.length));
    const dx = inner.reduce((sum, value, index) => sum + (value - .5) * Math.cos((index + 1) * 1.7), 0) / denominator * 60;
    const dy = inner.reduce((sum, value, index) => sum + (value - .5) * Math.sin((index + 1) * 1.7), 0) / denominator * 60;
    return { x: center.x + dx, y: center.y + dy, center };
  }
  const chainPoints: { x: number; y: number; center: { x: number; y: number }; member: AtlasChainMember; order: number }[] = [];
  chain?.members.forEach((member, order) => {
    if (member.syllable_count < minSyllables || member.syllable_count > maxSyllables) return;
    const p = locate(member);
    for (let attempt = 0; attempt < 90; attempt += 1) {
      if (!chainPoints.some((other) => Math.hypot(p.x - other.x, p.y - other.y) < 31)) break;
      const angle = attempt * 2.399 + order * .7;
      const radius = 31 + Math.sqrt(attempt) * 13;
      p.x = p.center.x + Math.cos(angle) * radius;
      p.y = p.center.y + Math.sin(angle) * radius;
    }
    chainPoints.push({ ...p, member, order });
  });
  const hiddenMembers = (chain?.members.length ?? 0) - chainPoints.length;
  const highlightedPoint = highlighted && highlighted.syllable_count >= minSyllables && highlighted.syllable_count <= maxSyllables ? locate(highlighted) : null;
  const selected = regions.find((region) => region.id === (hovered ?? selectedRegion));
  const layerMarks = [...new Set([minSyllables, 2, 4, 8, 12, 16, 24, 32, 48, maxSyllables].filter((value) => value >= minSyllables && value <= maxSyllables))].sort((a, b) => a - b);

  // Berechne klangliche Resonanzverbindungen (Reim-Kanten) zum ausgewählten Knoten
  const resonanceEdges = useMemo(() => {
    if (!selected) return [];
    return regions
      .filter((other) => other.id !== selected.id && other.last_family === selected.last_family)
      .sort((a, b) => {
        const diffA = Math.abs(a.syllables - selected.syllables);
        const diffB = Math.abs(b.syllables - selected.syllables);
        if (diffA !== diffB) return diffA - diffB;
        return b.count - a.count;
      })
      .slice(0, 16);
  }, [selected, regions]);

  function beginDrag(event: PointerEvent<SVGSVGElement>) {
    if (event.button !== 0) return;
    moved.current = false;
    if ((event.target as Element).closest("[data-rwa-region], [data-rwa-member]")) { drag.current = null; return; }
    drag.current = { id: event.pointerId, x: event.clientX, y: event.clientY, panX: pan.x, panY: pan.y };
    event.currentTarget.setPointerCapture(event.pointerId);
  }
  function moveDrag(event: PointerEvent<SVGSVGElement>) {
    if (!drag.current || drag.current.id !== event.pointerId) return;
    const bounds = event.currentTarget.getBoundingClientRect();
    const dx = (event.clientX - drag.current.x) * 1300 / Math.max(bounds.width, 1);
    const dy = (event.clientY - drag.current.y) * 760 / Math.max(bounds.height, 1);
    if (Math.abs(dx) + Math.abs(dy) > 5) moved.current = true;
    setPan({ x: clamp(drag.current.panX + dx, -2400, 2400), y: clamp(drag.current.panY + dy, -1600, 1600) });
  }
  function changeZoom(factor: number) {
    const next = clamp(zoom * factor, .45, 8);
    const anchor = selected ? point(selected) : { x: (650 - pan.x) / zoom, y: (380 - pan.y) / zoom };
    setPan({ x: clamp(pan.x + anchor.x * (zoom - next), -2400, 2400), y: clamp(pan.y + anchor.y * (zoom - next), -1600, 1600) });
    setZoom(next);
  }

  // Sanftes Mausrad-Zoomen am Mauszeiger
  function handleWheel(event: React.WheelEvent<SVGSVGElement>) {
    event.preventDefault();
    const bounds = event.currentTarget.getBoundingClientRect();
    const clientX = event.clientX - bounds.left;
    const clientY = event.clientY - bounds.top;
    const svgX = (clientX / Math.max(bounds.width, 1)) * 1300;
    const svgY = (clientY / Math.max(bounds.height, 1)) * 760;

    const factor = event.deltaY < 0 ? 1.15 : 1 / 1.15;
    const nextZoom = clamp(zoom * factor, 0.45, 8);

    const worldX = (svgX - pan.x) / zoom;
    const worldY = (svgY - pan.y) / zoom;
    const nextPanX = clamp(svgX - worldX * nextZoom, -2600, 2600);
    const nextPanY = clamp(svgY - worldY * nextZoom, -1800, 1800);

    setZoom(nextZoom);
    setPan({ x: nextPanX, y: nextPanY });
  }

  return <section className={`rwa-landscape ${isFullscreen ? "is-fullscreen" : ""}`} aria-labelledby="rwa-map-title">
    <div className="rwa-map-head">
      <div>
        <span className="rwa-overline">Klanglandkarte & Klangleiter</span>
        <h2 id="rwa-map-title">{singleLayer ? `${minSyllables} ${minSyllables === 1 ? "Silbe" : "Silben"} · Anfangs- und Endklänge.` : "Von einem Laut zu ganzen Reimfolgen."}</h2>
        <p>{singleLayer ? "Waagerecht: erste Vokalfamilie · senkrecht: letzte Vokalfamilie · Klick verbindet Reim-Partner" : "Diagonale Klangleiter: kurz (oben links) nach lang (unten rechts). Klick zeigt Resonanznetz."}</p>
      </div>
      <div className="rwa-map-tools" aria-label="Kartenansicht">
        <button type="button" className="rwa-tool-highlight" onClick={() => setIsFullscreen(!isFullscreen)} title="Vollbild umschalten (Esc zum Beenden)">
          {isFullscreen ? "🗗 Normal" : "⛶ Vollbild"}
        </button>
        <button type="button" aria-label="Karte verkleinern" onClick={() => changeZoom(1 / 1.35)}>−</button>
        <span>{Math.round(zoom * 100)} %</span>
        <button type="button" aria-label="Karte vergrößern" onClick={() => changeZoom(1.35)}>+</button>
        <button type="button" onClick={() => { setZoom(1); setPan({ x: 0, y: 0 }); }}>Zentrieren</button>
      </div>
    </div>
    <div className="rwa-map-viewport">
      <svg viewBox="0 0 1300 760" role="group" aria-label="Reimatlas nach Silbenlänge und Klangfamilien. Klangregionen sind einzeln auswählbar."
        onPointerDown={beginDrag} onPointerMove={moveDrag} onPointerUp={() => { drag.current = null; }} onPointerCancel={() => { drag.current = null; }}
        onWheel={handleWheel}>
        <defs>
          <radialGradient id="rwa-map-glow"><stop offset="0" stopColor="#d8bd73" stopOpacity=".12" /><stop offset="1" stopColor="#d8bd73" stopOpacity="0" /></radialGradient>
          <marker id="rwa-chain-arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0 0 L8 4 L0 8" fill="#fff3bd" /></marker>
        </defs>
        <rect x="0" y="0" width="1300" height="760" fill="url(#rwa-map-glow)" />
        <g transform={`translate(${pan.x} ${pan.y}) scale(${zoom})`}>
          {!singleLayer && <path className="rwa-progress-axis" d="M70 60 L1210 675" />}
          {singleLayer && MAP_FAMILIES.map((family, index) => {
            const t = .06 + .88 * index / (MAP_FAMILIES.length - 1); const x = 85 + t * 1110; const y = 82 + t * 570;
            return <g className="rwa-family-grid" key={family}><path d={`M${x} 92 L${x} 655 M140 ${y} L1160 ${y}`} /><text x={x} y="75" textAnchor="middle">{labelFamily(family)}</text><text x="115" y={y + 4} textAnchor="end">{labelFamily(family)}</text></g>;
          })}
          {!singleLayer && layerMarks.map((syllables) => {
            const t = level(syllables);
            const x = 85 + (.15 + .70 * t) * 1110; const y = 82 + (.15 + .70 * t) * 570;
            return <g key={syllables} className="rwa-layer-guide"><path d={`M${Math.max(20, x - 170)} ${y + 100} L${Math.min(1280, x + 170)} ${y - 100}`} /><text x={clamp(x - 155, 20, 1130)} y={clamp(y + 115, 30, 735)}>{syllables} {syllables === 1 ? "Silbe" : "Silben"}</text></g>;
          })}

          {/* DYNAMISCHE RESONANZ-VERBINDUNGEN BEIM ANKLICKEN */}
          {selected && resonanceEdges.map((partner) => {
            const p1 = point(selected);
            const p2 = point(partner);
            const midX = (p1.x + p2.x) / 2;
            const midY = (p1.y + p2.y) / 2;
            const dx = p2.x - p1.x;
            const dy = p2.y - p1.y;
            const cx = midX - dy * 0.12;
            const cy = midY + dx * 0.12;
            const strokeColor = color(selected.last_family);
            return (
              <g key={`res-${partner.id}`}>
                <path className="rwa-resonance-arc" d={`M${p1.x} ${p1.y} Q${cx} ${cy} ${p2.x} ${p2.y}`} stroke={strokeColor} strokeWidth={partner.syllables === selected.syllables ? 2.5 : 1.4} />
                <circle className="rwa-partner-halo" cx={p2.x} cy={p2.y} r={16 / Math.sqrt(zoom)} fill={strokeColor} />
              </g>
            );
          })}

          {/* REGIONEN (KNOTEN) */}
          {regions.map((region) => {
            const p = point(region); const active = selectedRegion === region.id;
            const isPartner = selected && resonanceEdges.some((edge) => edge.id === region.id);
            const radius = (4 + Math.pow(Math.log1p(region.count) / Math.log1p(maxPopulation), 2) * 12) / Math.sqrt(zoom);
            return <g key={region.id} data-rwa-region={region.id} className={`rwa-region ${active ? "is-selected" : ""} ${isPartner ? "is-resonance-partner" : ""}`} role="button" tabIndex={0}
              aria-label={`${region.syllables} Silben, ${labelFamily(region.first_family)} bis ${labelFamily(region.last_family)}, ${count(region.count)} Ausspracheeinträge; Klangregion öffnen`}
              onPointerEnter={() => setHovered(region.id)} onPointerLeave={() => setHovered(null)} onClick={() => { if (!moved.current) onRegion(region); }} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); onRegion(region); } }}>
              <title>{`${region.syllables} Silben · ${region.first_family} → ${region.last_family} · ${count(region.count)} Ausspracheeinträge${region.samples?.length ? ` · ${region.samples.slice(0, 3).join(" / ")}` : ""}`}</title>
              <circle className="rwa-region-halo" cx={p.x} cy={p.y} r={radius + (isPartner ? 8 : 5)} fill={color(region.last_family)} />
              <circle cx={p.x} cy={p.y} r={radius} fill={color(region.last_family)} />
              {(active || hovered === region.id || isPartner || region.count >= maxPopulation * .7) && <text x={p.x + radius + 8} y={p.y + 4}>{region.syllables} · {labelFamily(region.first_family)} / {labelFamily(region.last_family)}</text>}
            </g>;
          })}

          {/* KETTEN-VERLAUF */}
          {chainPoints.length > 1 && <path className="rwa-chain-path" d={chainPoints.map((p, index) => `${index && p.order === chainPoints[index - 1].order + 1 ? "L" : "M"}${p.x} ${p.y}`).join(" ")} markerEnd="url(#rwa-chain-arrow)" />}
          {chainPoints.map((p) => <g key={`${p.member.position}-${p.order}`} data-rwa-member={p.order} className={`rwa-chain-node ${selectedMember === p.order ? "is-selected" : ""}`} role="button" tabIndex={0} aria-label={`${p.order + 1}. ${p.member.text}; ${p.member.nuclei.join(" · ")}; neue Nachbarn finden`} onClick={() => onMember(p.member, p.order)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); onMember(p.member, p.order); } }}><title>{`${p.order + 1}. ${p.member.text} · ${p.member.syllable_count} Silben · ${p.member.nuclei.join(" · ")}`}</title><path className="rwa-chain-tether" d={`M${p.center.x} ${p.center.y} L${p.x} ${p.y}`} /><circle className="rwa-chain-region-pin" cx={p.center.x} cy={p.center.y} r="3" /><circle className="rwa-chain-marker" cx={p.x} cy={p.y} r={selectedMember === p.order ? "15" : "12"} /><text x={p.x} y={p.y + 4} textAnchor="middle">{p.order + 1}</text></g>)}
          {highlightedPoint && <g className="rwa-current-location"><circle cx={highlightedPoint.x} cy={highlightedPoint.y} r="35" /><text x={highlightedPoint.x + 40} y={highlightedPoint.y - 15}>{shorten(highlighted!.text, 35)}</text></g>}
          {!regions.length && <text className="rwa-map-empty" x="650" y="355" textAnchor="middle">{emptyMessage}</text>}
        </g>
      </svg>
    </div>
    <div className="rwa-map-foot">
      <p>
        {selected ? (
          <>
            <strong>{selected.syllables} Silben · {labelFamily(selected.first_family)} → {labelFamily(selected.last_family)}</strong> 
            {count(selected.count)} Aussprachen
            {selected.samples?.length ? <> · <em>Beispiele: {selected.samples.slice(0, 4).join(" / ")}</em></> : ""}
            {resonanceEdges.length > 0 && <span style={{ color: "#fff3bd", marginLeft: "0.5rem" }}>⚡ {resonanceEdges.length} Reim-Verbindungen aktiv</span>}
          </>
        ) : (
          "Klangregion anklicken, um vollständige Resonanzlinien zu sehen. Mausrad zoomt · Ziehen verschiebt · Vollbild oben rechts."
        )}
      </p>
      <span>{map ? count(regions.length) : "…"} Regionen angezeigt · {map ? count(map.total_entries) : "…"} Aussprachen im Filter</span>
    </div>
    {chain && <div className="rwa-map-chain-note"><span className="rwa-chain-line" />„{chain.title}“ · Helle Nummern zeigen die Reihenfolge. Punktierte Linien verankern die lesbaren Detailpunkte in ihrer Klangregion. Klick findet neue Nachbarn.{hiddenMembers > 0 && <strong> {hiddenMembers} Reime liegen außerhalb des gewählten Silbenbereichs.</strong>}</div>}
  </section>;
}

function Neighborhood({ region, data, selectedSignature, busy, error, onSignature }: {
  region: AtlasRegion; data: AtlasNeighborhood | null; selectedSignature: string;
  busy: boolean; error: string; onSignature: (signature: string) => void;
}) {
  return <section className="rwa-neighborhood" aria-labelledby="rwa-neighborhood-title">
    <div className="rwa-neighborhood-head"><div><span className="rwa-overline">In der Klangregion</span><h3 id="rwa-neighborhood-title">{region.syllables} Silben · jede Position zählt.</h3><p>Die Übersicht bündelt die erste und letzte Vokalfamilie. Hier unterscheidet sich die ganze geordnete Klangfamilienfolge; jeder Treffer zeigt zusätzlich seine genaue Aussprache.</p></div><button type="button" aria-pressed={!selectedSignature} onClick={() => onSignature("")}>Ganze Region</button></div>
    {busy && <p className="rwa-neighborhood-state" role="status">Vollständige Klangfolgen werden geladen …</p>}
    {error && <p className="rwa-error" role="alert">{error}</p>}
    {data && !busy && data.signatures.length === 0 && <p className="rwa-neighborhood-state">In dieser Region sind für die gewählte Ansicht noch keine vollständigen Klangfolgen belegt.</p>}
    <div className="rwa-signature-list">{data?.signatures.map((sequence) => <button key={sequence.signature} type="button" className={selectedSignature === sequence.signature ? "is-selected" : ""} aria-pressed={selectedSignature === sequence.signature} onClick={() => onSignature(sequence.signature)}><span className="rwa-signature-vowels" aria-label={`Klangfamilien in Reihenfolge: ${sequence.nuclei.map(labelFamily).join(" · ")}`}>{sequence.nuclei.map((family, index) => <i key={index} style={{ color: color(family) }} title={`Position ${index + 1}: ${labelFamily(family)}`}>{labelFamily(family)}</i>)}</span><strong>{count(sequence.count)} Aussprachen</strong><small>{sequence.samples.slice(0, 3).join(" / ")}</small></button>)}</div>
    {data && data.signatures.length > 0 && <p className="rwa-neighborhood-state">{count(data.signatures.length)} häufige Klangfolgen angezeigt. Eine Folge anklicken, um passende Wörter und Wortfolgen zu finden.</p>}
  </section>;
}

function ResultCard({ result, selected, busy, onExpand, onAdd }: {
  result: AtlasCandidate; selected: boolean; busy: boolean; onExpand: () => void; onAdd: () => void;
}) {
  const url = safeUrl(result.source?.url);
  const reference = result.source_ref;
  const basis = reference?.pronunciation_basis || (result.origin === "dictionary" ? "IPA aus dem Aussprachewörterbuch." : "Aussprache für diese Wortfolge erschlossen.");
  return <article className={`rwa-result ${selected ? "is-selected" : ""}`}>
    <div className="rwa-result-heading"><div><span className="rwa-result-kind">{kindName(result.kind)} · {result.syllable_count} {result.syllable_count === 1 ? "Silbe" : "Silben"} · {result.language.toUpperCase()}</span><h3>{result.text}</h3></div><button className="rwa-add-button" type="button" disabled={busy} aria-label={`„${result.text}“ zur Reimfolge hinzufügen`} onClick={onAdd}>＋</button></div>
    <div className="rwa-result-sound"><span className="rwa-ipa">{result.ipa}</span><span className="rwa-sound-label">Vokalkerne in ihrer Reihenfolge</span><span className="rwa-nuclei" aria-label={`Vokalkerne: ${result.nuclei.join(" · ")}`}>{result.nuclei.map((nucleus, index) => <i key={index} title={`Position ${index + 1}`} style={{ color: color(familyOf(nucleus)) }}>{nucleus}</i>)}</span></div>
    {result.reason && <p className="rwa-result-reason">{result.reason}</p>}
    {result.matched_anchor && <p className="rwa-matched-anchor">Gefunden zu: {result.matched_anchor}</p>}
    <div className="rwa-result-bottom"><div><span className={result.origin === "constructed" ? "rwa-constructed" : "rwa-attested"}>{originName(result.origin)}</span>{result.source?.name && (url ? <a href={url} target="_blank" rel="noreferrer noopener">{result.source.name} ↗</a> : <span>{result.source.name}</span>)}</div><button type="button" disabled={busy} onClick={onExpand}>Nachbarn erkunden ↗</button></div>
    <details className="rwa-source-details"><summary>Aussprache & Herkunft</summary><p>{basis}{reference?.variant_index != null && <> · Aussprachevariante {reference.variant_index + 1}</>}</p>
      {result.notes?.length ? <ul className="rwa-pronunciation-notes">{result.notes.map((note, index) => <li key={index}>{note}</li>)}</ul> : null}
      <p>{result.source.author && <>Autor: {result.source.author} · </>}{result.source.license}{result.source.sentence_id && <> · Beleg {result.source.sentence_id}</>}</p>
      {reference?.context && <blockquote><span>Satzbeleg</span>{reference.context}</blockquote>}
      {reference?.construction && <p>{reference.construction}</p>}
      {reference?.parts?.length ? <div className="rwa-construction-parts"><span>Verwendete Textspannen</span>{reference.parts.map((part, index) => <article key={index}><strong>{part.text}</strong>{part.source_ref?.context && <p>{part.source_ref.context}</p>}<small>{part.source_ref?.author && <>Autor: {part.source_ref.author} · </>}{part.source_ref?.sentence_id && <>Beleg {part.source_ref.sentence_id} · </>}{part.source_id}</small>{safeUrl(part.source_ref?.url) && <a href={part.source_ref!.url} target="_blank" rel="noreferrer noopener">Textspanne an der Quelle öffnen ↗</a>}</article>)}</div> : null}
    </details>
  </article>;
}

export default function RhymeAtlas() {
  const [status, setStatus] = useState<AtlasStatus | null>(null);
  const [statusError, setStatusError] = useState("");
  const [filters, setFilters] = useState<AtlasFilters>(INITIAL_FILTERS);
  const [map, setMap] = useState<AtlasMap | null>(null);
  const [mapBusy, setMapBusy] = useState(false); const [mapError, setMapError] = useState("");
  const [query, setQuery] = useState(""); const [response, setResponse] = useState<AtlasSearchResponse | null>(null);
  const [resultFilters, setResultFilters] = useState("");
  const [searchBusy, setSearchBusy] = useState(false); const [searchError, setSearchError] = useState("");
  const [selectedRegion, setSelectedRegion] = useState("");
  const [focusedRegion, setFocusedRegion] = useState<AtlasRegion | null>(null);
  const [selectedSignature, setSelectedSignature] = useState("");
  const [neighborhood, setNeighborhood] = useState<AtlasNeighborhood | null>(null);
  const [neighborhoodBusy, setNeighborhoodBusy] = useState(false);
  const [neighborhoodError, setNeighborhoodError] = useState("");
  const [highlighted, setHighlighted] = useState<AtlasCandidate | null>(null);
  const [chains, setChains] = useState<AtlasChain[]>([]); const [chainId, setChainId] = useState("");
  const [chainDraft, setChainDraft] = useState(""); const [chainTitle, setChainTitle] = useState("");
  const [chainDraftReferences, setChainDraftReferences] = useState<DraftMember[]>([]);
  const [chainBusy, setChainBusy] = useState(false); const [chainMessage, setChainMessage] = useState("");
  const [chainError, setChainError] = useState("");
  const [selectedChainMember, setSelectedChainMember] = useState<number | null>(null);
  const searchSequence = useRef(0);
  const resultsRef = useRef<HTMLElement>(null);
  const selectedChain = chains.find((chain) => chain.id === chainId) ?? null;
  const resultsStale = Boolean(response && resultFilters !== JSON.stringify(filters));
  const mapKey = JSON.stringify({ kind: filters.kind, languages: filters.languages, min: filters.min_syllables, max: filters.max_syllables, origin: filters.origin });
  const loadStatus = useCallback(async () => {
    try { setStatus(await rhymeAtlasApi.status()); setStatusError(""); }
    catch (error) { setStatusError(errorText(error)); }
  }, []);
  useEffect(() => { void loadStatus(); void rhymeAtlasApi.chains().then((data) => setChains(data.chains)).catch((error) => setChainError(errorText(error))); }, [loadStatus]);
  useEffect(() => {
    if (status?.status !== "building") return;
    const interval = window.setInterval(() => void loadStatus(), 5000);
    return () => window.clearInterval(interval);
  }, [status?.status, loadStatus]);
  useEffect(() => {
    let active = true;
    setMapBusy(true); setMapError("");
    const timer = window.setTimeout(() => {
      void rhymeAtlasApi.map(filters).then((data) => { if (active) setMap({ ...data, min_syllables: filters.min_syllables, max_syllables: filters.max_syllables }); }).catch((error) => { if (active) setMapError(errorText(error)); }).finally(() => { if (active) setMapBusy(false); });
    }, 180);
    return () => { active = false; window.clearTimeout(timer); };
  }, [mapKey, status?.revision, status?.status]);
  useEffect(() => {
    if (!focusedRegion) { setNeighborhood(null); setNeighborhoodBusy(false); return; }
    let active = true;
    setNeighborhood(null); setNeighborhoodBusy(true); setNeighborhoodError("");
    void rhymeAtlasApi.neighborhood(focusedRegion, filters).then((data) => { if (active) setNeighborhood(data); }).catch((error) => { if (active) setNeighborhoodError(errorText(error)); }).finally(() => { if (active) setNeighborhoodBusy(false); });
    return () => { active = false; };
  }, [focusedRegion?.id, mapKey, status?.revision]);
  useEffect(() => { setFocusedRegion(null); setSelectedRegion(""); setSelectedSignature(""); }, [mapKey]);

  function update<K extends keyof AtlasFilters>(key: K, value: AtlasFilters[K]) { setFilters((current) => ({ ...current, [key]: value })); }
  async function search(region?: AtlasRegion, signature = "") {
    if (!query.trim() && !region) return;
    const sequence = ++searchSequence.current;
    setSearchBusy(true); setSearchError(""); setHighlighted(null);
    setSelectedChainMember(null);
    setSelectedRegion(region?.id ?? ""); setFocusedRegion(region ?? null); setSelectedSignature(signature);
    try {
      const data = await rhymeAtlasApi.search({ ...filters, query: region ? "" : query.trim(), ...(region ? { region: { syllables: region.syllables, first_family: region.first_family, last_family: region.last_family, ...(signature ? { signature } : {}) } } : {}) });
      if (sequence === searchSequence.current) { setResponse(data); setResultFilters(JSON.stringify(filters)); void loadStatus(); }
    } catch (error) { if (sequence === searchSequence.current) setSearchError(errorText(error)); }
    finally { if (sequence === searchSequence.current) setSearchBusy(false); }
  }
  async function expand(candidate: AtlasCandidate) {
    const sequence = ++searchSequence.current;
    setSearchBusy(true); setSearchError(""); setHighlighted(candidate); setQuery(candidate.text);
    setSelectedChainMember(null); setFocusedRegion(null); setSelectedRegion(""); setSelectedSignature("");
    try { const data = await rhymeAtlasApi.expand(candidate.id, filters); if (sequence === searchSequence.current) { setResponse(data); setResultFilters(JSON.stringify(filters)); void loadStatus(); } }
    catch (error) { if (sequence === searchSequence.current) setSearchError(errorText(error)); }
    finally { if (sequence === searchSequence.current) setSearchBusy(false); }
  }
  async function exploreChainMember(member: AtlasChainMember, index: number) {
    const sequence = ++searchSequence.current;
    setSearchBusy(true); setSearchError(""); setQuery(member.text); setHighlighted(null);
    setSelectedChainMember(index); setFocusedRegion(null); setSelectedRegion(""); setSelectedSignature("");
    try {
      const data = member.entry_id != null
        ? await rhymeAtlasApi.expand(member.entry_id, filters)
        : await rhymeAtlasApi.search({ ...filters, query: member.text });
      if (sequence === searchSequence.current) { setResponse(data); setResultFilters(JSON.stringify(filters)); void loadStatus(); }
    } catch (error) { if (sequence === searchSequence.current) setSearchError(errorText(error)); }
    finally { if (sequence === searchSequence.current) setSearchBusy(false); }
  }
  function replaceChainDraft(text: string, references?: DraftMember[]) {
    setChainDraft(text);
    setChainDraftReferences((current) => draftMembers(text, references ?? current));
  }
  function addToChain(candidate: AtlasCandidate) {
    const members = [...draftMembers(chainDraft, chainDraftReferences), { text: candidate.text, entry_id: candidate.id }];
    setChainDraft(members.map((member) => member.text).join("\n")); setChainDraftReferences(members);
    setChainMessage(`„${candidate.text}“ mit dieser Aussprache zur ungespeicherten Reimfolge hinzugefügt.`);
  }
  async function saveChain() {
    const members = draftMembers(chainDraft, chainDraftReferences);
    if (!members.length) return;
    if (members.length > 200 || members.some((member) => member.text.length > 500)) {
      setChainError("Eine Reimfolge kann bis zu 200 Reime mit jeweils bis zu 500 Zeichen enthalten."); return;
    }
    setChainBusy(true); setChainError(""); setChainMessage("");
    try {
      const chain = await rhymeAtlasApi.saveChain(chainTitle.trim() || "Meine Reimfolge", members.map((member) => member.entry_id != null ? member : member.text));
      setChains((current) => [chain, ...current.filter((item) => item.id !== chain.id)]); setChainId(chain.id); setChainTitle(chain.title);
      setChainMessage("Reimfolge gespeichert und als Pfad in der Klangkarte eingeblendet."); void loadStatus();
    } catch (error) { setChainError(errorText(error)); }
    finally { setChainBusy(false); }
  }
  const activeFamilies = useMemo(() => [...new Set((map?.regions ?? []).map((region) => region.last_family))], [map]);
  const inventoryCount = (key: keyof AtlasStatus["counts"]) => status ? count(status.counts[key]) : "…";
  const buildText = status?.build ? [status.build.phase, status.build.source, status.build.message].filter((item) => typeof item === "string" && item).join(" · ") : "";
  const mapEmptyMessage = mapError ? "Die Klangkarte konnte nicht geladen werden."
    : mapBusy ? "Klangregionen werden aus dem Atlas geladen …"
    : status?.status === "building" ? "Der Import läuft. Diese Ansicht enthält noch keine Klangregionen."
    : status?.status === "empty" ? "Der lokale Atlas enthält noch keine importierten Klangregionen."
    : "Für diese Filter sind noch keine Klangregionen vorhanden.";

  return <div className="rwa-atlas">
    <header className="rwa-hero"><div><span className="rwa-overline">REiMWERK / DER REiMATLAS</span><h1>Neue Reime liegen in der Nähe.</h1><p>Wörter, Komposita und mehrteilige Klangfolgen in einem gemeinsamen Raum. Suche einen Reimanker und entdecke, was daneben liegt.</p></div><div className="rwa-atlas-stamp"><span>DE + EN</span><strong>Klang verbindet.</strong><small>Wortgrenzen bleiben beweglich.</small></div></header>
    <div className="rwa-inventory" aria-label="Tatsächlicher Atlasbestand"><div><strong>{inventoryCount("entries")}</strong><span>Schreibformen · DE/EN</span></div><div><strong>{inventoryCount("pronunciations")}</strong><span>Ausspracheeinträge</span></div><div><strong>{inventoryCount("phrases")}</strong><span>davon Aussprachen von Wortfolgen</span></div><div><strong>{inventoryCount("sources")}</strong><span>Quellen</span></div><span className={`rwa-build-state ${status?.status === "building" ? "is-building" : ""}`}>{status?.status === "building" ? "Atlas wird erweitert" : status?.status === "ready" ? "Lokal erschlossen" : status?.status === "empty" ? "Noch kein Bestand" : statusError ? "Bestand nicht erreichbar" : "Bestand wird geprüft"}</span><button type="button" onClick={() => void loadStatus()} aria-label="Atlasbestand aktualisieren">↻</button></div>
    {statusError && <p className="rwa-error" role="alert">{statusError}</p>}
    {status?.status === "building" && <p className="rwa-build-note" role="status">{buildText || "Wort- und Aussprachebestände werden erschlossen. Bereits verfügbare Klangregionen lassen sich erkunden."}</p>}
    {status?.status === "empty" && <p className="rwa-build-note">Dieser lokale Atlas enthält noch keine importierten Daten. Die Karte und Suche zeigen den tatsächlichen Importstand.</p>}

    <section className="rwa-search-panel" aria-label="Neue Reime suchen">
      <form onSubmit={(event) => { event.preventDefault(); void search(); }}>
        <label htmlFor="rwa-query">Dein Reimanker</label>
        <div className="rwa-search-row">
          <textarea id="rwa-query" value={query} rows={2} maxLength={4000} onChange={(event) => setQuery(event.target.value)} placeholder="Ein Wort, ein Kompositum oder eine mehrteilige Klangfolge. Mehrere Reimanker jeweils untereinander." />
          <button className="rw-primary-button" type="submit" disabled={searchBusy || !query.trim()}>
            {searchBusy ? "Suche im Atlas …" : "Neue Reime finden"}<span aria-hidden="true"> ↗</span>
          </button>
        </div>
        <div className="rwa-quick-chips">
          <span style={{ fontSize: "0.72rem", color: "#8fa37d", alignSelf: "center" }}>Sofort-Testen:</span>
          {["Licht", "Gewichtung", "Perspektive", "Wände", "Käfig", "Silben"].map((chip) => (
            <button key={chip} type="button" className="rwa-quick-chip" onClick={() => {
              setQuery(chip);
              const sequence = ++searchSequence.current;
              setSearchBusy(true); setSearchError(""); setHighlighted(null);
              void rhymeAtlasApi.search({ ...filters, query: chip }).then((data) => {
                if (sequence === searchSequence.current) {
                  setResponse(data);
                  setResultFilters(JSON.stringify(filters));
                  void loadStatus();
                }
              }).catch((err) => {
                if (sequence === searchSequence.current) setSearchError(errorText(err));
              }).finally(() => {
                if (sequence === searchSequence.current) setSearchBusy(false);
              });
            }}>
              {chip}
            </button>
          ))}
        </div>
        <p>Gesucht wird im erschlossenen Bestand. Deine Eingaben bilden die Ausgangspunkte; darunter erscheinen neue Kandidaten.</p>
      </form>
      <div className="rwa-filter-row"><label>Silben von <input type="number" min={1} max={64} value={filters.min_syllables} onChange={(event) => { const value = clamp(Number(event.target.value) || 1, 1, 64); setFilters((current) => ({ ...current, min_syllables: value, max_syllables: Math.max(value, current.max_syllables) })); }} /></label><label>bis <input type="number" min={filters.min_syllables} max={64} value={filters.max_syllables} onChange={(event) => update("max_syllables", clamp(Number(event.target.value) || filters.min_syllables, filters.min_syllables, 64))} /></label><label>Sprache <select aria-label="Sprache filtern" value={filters.languages.join(",")} onChange={(event) => update("languages", event.target.value.split(","))}><option value="de,en">Deutsch + Englisch</option><option value="de">Deutsch</option><option value="en">Englisch</option></select></label><label>Spielraum <select aria-label="Reimspielraum filtern" value={filters.mode} onChange={(event) => update("mode", event.target.value as AtlasFilters["mode"])}><option value="dirty">Frei im Klang</option><option value="balanced">Nah am Muster</option><option value="strict">Enger Lautreim</option></select></label><label>Herkunft <select aria-label="Herkunft filtern" value={filters.origin} onChange={(event) => { const origin = event.target.value as AtlasFilters["origin"]; setFilters((current) => ({ ...current, origin, include_combinations: origin !== "attested" })); }}><option value="all">Belegt + neu kombiniert</option><option value="attested">Belegte Einträge</option><option value="constructed">Neue Kombinationen</option></select></label></div>
    </section>

    <div className="rwa-main-grid"><div className="rwa-map-column"><div className="rwa-kind-views" role="group" aria-label="Ansicht der Klanglandkarte">{([{ kind: "all", label: "Alle Formen" }, { kind: "word", label: "Wörter" }, { kind: "compound", label: "Komposita" }, { kind: "phrase", label: "Wortfolgen" }] as const).map((view) => <button key={view.kind} type="button" aria-pressed={filters.kind === view.kind} className={filters.kind === view.kind ? "is-selected" : ""} onClick={() => update("kind", view.kind)}>{view.label}</button>)}</div><div className="rwa-map-loading" aria-live="polite">{mapBusy ? "Klangkarte wird aktualisiert …" : ""}{mapError && <span className="rwa-error">{mapError}</span>}</div><AtlasLandscape map={map} filters={filters} emptyMessage={mapEmptyMessage} selectedRegion={selectedRegion} chain={selectedChain} selectedMember={selectedChainMember} highlighted={highlighted} onRegion={(region) => void search(region)} onMember={(member, index) => void exploreChainMember(member, index)} />
      <div className="rwa-family-key" aria-label="Klangfarben">{activeFamilies.map((family) => <span key={family}><i style={{ background: color(family) }} />{labelFamily(family)}</span>)}<span className="rwa-family-key-note">Kreisgröße = Aussprachen · Farbe = letzte Vokalfamilie · Region öffnen für die ganze Folge</span></div>
      {focusedRegion && <Neighborhood region={focusedRegion} data={neighborhood} selectedSignature={selectedSignature} busy={neighborhoodBusy} error={neighborhoodError} onSignature={(signature) => void search(focusedRegion, signature)} />}
      <details className="rwa-region-directory"><summary>Klangregionen als Liste erkunden</summary><div>{(map?.regions ?? []).map((region) => <button key={region.id} type="button" onClick={() => void search(region)}><strong>{region.syllables} Silben · {labelFamily(region.first_family)} → {labelFamily(region.last_family)}</strong><span>{count(region.count)} Aussprachen</span></button>)}</div></details>
    </div>
    <aside className="rwa-chain-panel" aria-label="Reimfolgen kartieren"><span className="rwa-overline">Reimfolgen</span><h2>Ein Pfad durch den Klangraum.</h2><p>Speichere eine zusammengehörige Reihenfolge. Jeder Reim behält seine Position. Ein Klick auf einen Eintrag sucht neue Nachbarn dazu.</p><label>Gespeicherte Folge <select aria-label="Gespeicherte Reimfolge" value={chainId} onChange={(event) => { setChainId(event.target.value); setSelectedChainMember(null); }}><option value="">Keine eingeblendet</option>{chains.map((chain) => <option key={chain.id} value={chain.id}>{chain.title} · {chain.members.length} Reime</option>)}</select></label>
      {selectedChain && <><ol className="rwa-chain-sequence">{selectedChain.members.map((member, index) => <li key={`${member.position}-${index}`}><button type="button" className={selectedChainMember === index ? "is-selected" : ""} aria-pressed={selectedChainMember === index} disabled={searchBusy} onClick={() => void exploreChainMember(member, index)}><b>{index + 1}</b><span>{member.text}<small>{member.syllable_count} Silben · {member.nuclei.join(" → ")}</small><small className="rwa-chain-ipa">{member.ipa}</small><small className="rwa-chain-discover">Neue Nachbarn ↗</small></span></button></li>)}</ol><button type="button" className="rw-quiet-button" onClick={() => { replaceChainDraft(selectedChain.members.map((member) => member.text).join("\n"), selectedChain.members); setChainTitle(selectedChain.title); setChainMessage("Reimfolge im Editor übernommen. Änderungen werden als neue Folge gespeichert."); }}>Folge im Editor übernehmen</button></>}
      <details className="rwa-chain-editor"><summary>Reimfolge anlegen oder erweitern</summary><div><button type="button" className="rw-quiet-button" onClick={() => { replaceChainDraft(query, [...(highlighted ? [{ text: highlighted.text, entry_id: highlighted.id }] : []), ...(response?.anchors ?? [])]); setChainMessage(""); }}>Suchanker übernehmen</button><label>Name <input aria-label="Name der Reimfolge" maxLength={120} value={chainTitle} onChange={(event) => setChainTitle(event.target.value)} placeholder="Name deiner Reimfolge" /></label><label>Reime in ihrer Reihenfolge <textarea aria-label="Reime der Folge" rows={6} maxLength={16000} value={chainDraft} onChange={(event) => replaceChainDraft(event.target.value)} placeholder="Jeweils ein Reim pro Eintrag. Das kann ein Wort oder eine ganze Wortfolge sein." /></label><button type="button" className="rw-secondary-button" disabled={chainBusy || !chainDraft.trim()} onClick={() => void saveChain()}>{chainBusy ? "Speichere …" : "Reimfolge kartieren"}</button></div></details>
      {chainMessage && <p className="rwa-notice" role="status">{chainMessage}</p>}{chainError && <p className="rwa-error" role="alert">{chainError}</p>}
      <details className="rwa-source-list"><summary>Quellen im Atlas</summary>{(status?.sources ?? []).map((source) => <article key={source.id}><strong>{source.name}</strong><p>{(source.sentence_count ?? 0) > 0 ? <>{count(source.sentence_count)} Satzbelege · {count(source.pronunciation_count ?? 0)} erschlossene Ausspracheeinträge</> : <>{count(source.pronunciation_count ?? source.entry_count)} Aussprachen</>} · {source.license || "Lizenz im Quellnachweis"}</p>{safeUrl(source.url) && <a href={source.url} target="_blank" rel="noreferrer noopener">Quelle öffnen ↗</a>}</article>)}</details>
    </aside></div>

    <section className="rwa-results-section" ref={resultsRef} aria-labelledby="rwa-results-title"><div className="rwa-results-head"><div><span className="rwa-overline">Nachbarschaften entdecken</span><h2 id="rwa-results-title">{response ? "Neue Reimkandidaten" : "Was klingt in der Nähe?"}</h2><p>{response ? `${count(response.results.length)} Vorschläge aus ${count(response.searched_candidates)} geprüften Kandidaten` : "Suche nach einem Reimanker oder wähle eine Klangregion auf der Karte."}</p></div>{searchBusy && <span className="rwa-searching" role="status">Suche läuft …</span>}</div>
      {searchError && <p className="rwa-error" role="alert">{searchError}</p>}
      {resultsStale && <p className="rwa-build-note">Die Filter wurden geändert. Die sichtbaren Treffer gehören noch zur vorherigen Suche; mit „Neue Reime finden“ aktualisieren.</p>}
      {response?.anchors?.length ? <div className="rwa-anchor-strip" aria-label="Verwendete Suchanker">{response.anchors.map((anchor, index) => <span key={index}><strong>{anchor.text}</strong><small>{anchor.syllable_count} Silben · {anchor.nuclei.join(" · ")}</small></span>)}</div> : null}
      {response?.warnings?.length ? <details className="rwa-search-notes"><summary>Hinweise zu dieser Suche</summary>{response.warnings.map((warning, index) => <p key={index}>{warning}</p>)}</details> : null}
      {response && response.results.length === 0 && !searchBusy && <div className="rwa-results-empty"><h3>Hier wurden noch keine passenden Nachbarn gefunden.</h3><p>Wähle eine andere Silbenlänge, weitere Wortarten oder einen größeren klanglichen Spielraum. Die Karte zeigt den aktuell erschlossenen Bestand.</p></div>}
      <div className="rwa-results-grid">{response?.results.map((result, index) => <ResultCard key={`${result.id}-${index}`} result={result} selected={highlighted?.id === result.id} busy={searchBusy} onExpand={() => void expand(result)} onAdd={() => addToChain(result)} />)}</div>
    </section>
    <footer className="rwa-atlas-foot"><span>Eine wachsende Kartierung aus den ausgewiesenen Quellen.</span><span>Einzelwörter → Komposita → Wortfolgen · Aussprachevarianten bleiben unterscheidbar.</span></footer>
  </div>;
}
