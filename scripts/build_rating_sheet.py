#!/usr/bin/env python3
"""
Baut einen lokalen HTML-Bewertungsbogen aus den vom Algorithmus entdeckten
Reim-Paaren (rhyme_pairs). Score-geschichtetes Spektrum, damit die Bewertung
maximal lehrreich fuer das Feedback-Training ist (zeigt, WO die Engine falsch liegt).

Privatsphaere: liest die lokale SQLite, schreibt HTML in den gitignorten
Datenordner. Keine Texte verlassen die Maschine.

Aufruf:
    python3 scripts/build_rating_sheet.py
"""
from __future__ import annotations

import json
import random
import sqlite3
import unicodedata
from pathlib import Path

DB_PATH = Path("app/data/user_texts/rhyme_database.sqlite")
OUT_HTML = Path("app/data/user_texts/reim_bewertung.html")

# (low, high, anzahl) — Spektrum ueber alle Score-Baender
BANDS = [
    (0.88, 1.01, 40),   # "Engine sagt perfekt" — testet -en-Falle / falsche Sicherheit
    (0.80, 0.88, 20),
    (0.72, 0.80, 25),
    (0.65, 0.72, 20),
    (0.58, 0.65, 20),
]
MAX_PER_PHRASE = 2       # Variety: ein Phrase darf max. so oft auftauchen
SEED = 42


def _norm(phrase: str) -> str:
    return " ".join(
        unicodedata.normalize("NFKC", phrase or "").casefold().split()
    )


def select_pairs(conn: sqlite3.Connection) -> list[dict]:
    rng = random.Random(SEED)
    selected: list[dict] = []
    seen_pair: set[tuple[str, str]] = set()
    phrase_uses: dict[str, int] = {}

    for lo, hi, want in BANDS:
        rows = conn.execute(
            """
            select p.score, p.anchor, p.tail, p.vowel, p.cadence,
                   l.phrase lp, l.syllable_count ls, l.source_title lst, l.line_no lln,
                   r.phrase rp, r.syllable_count rs, r.source_title rst, r.line_no rln
            from rhyme_pairs p
            join rhyme_units l on l.id = p.left_unit_id
            join rhyme_units r on r.id = p.right_unit_id
            where p.score >= ? and p.score < ?
            """,
            (lo, hi),
        ).fetchall()
        rng.shuffle(rows)

        picked = 0
        for x in rows:
            if picked >= want:
                break
            ln, rn = _norm(x["lp"]), _norm(x["rp"])
            if not ln or not rn or ln == rn:
                continue
            key = tuple(sorted((ln, rn)))
            if key in seen_pair:
                continue
            if phrase_uses.get(ln, 0) >= MAX_PER_PHRASE or phrase_uses.get(rn, 0) >= MAX_PER_PHRASE:
                continue
            seen_pair.add(key)
            phrase_uses[ln] = phrase_uses.get(ln, 0) + 1
            phrase_uses[rn] = phrase_uses.get(rn, 0) + 1
            selected.append(
                {
                    "left": x["lp"],
                    "right": x["rp"],
                    "left_syl": x["ls"],
                    "right_syl": x["rs"],
                    "score": round(x["score"], 3),
                    "anchor": round(x["anchor"], 2),
                    "tail": round(x["tail"], 2),
                    "vowel": round(x["vowel"], 2),
                    "cadence": round(x["cadence"], 2),
                    "band": f"{lo:.2f}+",
                    # Feedback-Mapping: query=left, Kandidat=right (source/line/phrase)
                    "query": x["lp"],
                    "source_title": x["rst"],
                    "line_no": x["rln"],
                    "phrase": x["rp"],
                }
            )
            picked += 1
    # nach Score absteigend fuer angenehmes Durchgehen (stark -> grenzwertig)
    selected.sort(key=lambda d: d["score"], reverse=True)
    return selected


def render_html(pairs: list[dict]) -> str:
    data_json = json.dumps(pairs, ensure_ascii=False)
    total = len(pairs)
    return f"""<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Reim-Bewertung — Rheinwerker</title>
<style>
  :root {{ --bg:#0f1115; --card:#1a1d24; --line:#2a2f3a; --ink:#e6e9ef; --mut:#8b93a3;
           --good:#2ecc71; --bad:#e74c3c; --mid:#f1c40f; --acc:#5b8cff; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--ink);
          font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; padding-bottom:96px; }}
  header {{ padding:20px 22px 12px; border-bottom:1px solid var(--line); }}
  h1 {{ font-size:19px; margin:0 0 6px; }}
  .sub {{ color:var(--mut); font-size:13px; max-width:760px; }}
  .wrap {{ max-width:820px; margin:0 auto; padding:16px; }}
  .card {{ background:var(--card); border:1px solid var(--line); border-left:4px solid var(--acc);
           border-radius:12px; padding:14px 16px; margin:12px 0; }}
  .card.rated {{ opacity:.62; }}
  .pair {{ font-size:17px; font-weight:600; letter-spacing:.1px; }}
  .pair .arrow {{ color:var(--acc); margin:0 8px; }}
  .meta {{ color:var(--mut); font-size:12px; margin-top:6px; display:flex; gap:10px; flex-wrap:wrap; }}
  .badge {{ background:#23283200; border:1px solid var(--line); border-radius:6px; padding:1px 7px; }}
  .scale {{ display:flex; gap:5px; margin-top:12px; flex-wrap:wrap; align-items:center; }}
  .scale button {{ width:34px; height:34px; border-radius:8px; border:1px solid var(--line);
                   background:#222732; color:var(--ink); cursor:pointer; font-weight:600; font-size:14px; }}
  .scale button:hover {{ border-color:var(--acc); }}
  .scale button.sel {{ outline:2px solid #fff; }}
  .scale button[data-v="0"],[data-v="1"],[data-v="2"],[data-v="3"] {{}}
  .lab {{ color:var(--mut); font-size:11px; margin-right:6px; }}
  .cmt {{ margin-top:9px; width:100%; background:#11141a; color:var(--ink); border:1px solid var(--line);
          border-radius:8px; padding:7px 9px; font-size:13px; resize:vertical; }}
  footer {{ position:fixed; bottom:0; left:0; right:0; background:#0c0e12ee; backdrop-filter:blur(6px);
            border-top:1px solid var(--line); padding:12px 18px; display:flex; gap:14px;
            align-items:center; justify-content:space-between; }}
  .prog {{ font-size:14px; }}
  .prog b {{ color:var(--acc); }}
  .btns {{ display:flex; gap:10px; }}
  .btn {{ background:var(--acc); color:#fff; border:0; border-radius:9px; padding:10px 16px;
          font-weight:600; cursor:pointer; font-size:14px; }}
  .btn.ghost {{ background:#222732; color:var(--ink); border:1px solid var(--line); }}
  .hint {{ color:var(--mut); font-size:11px; }}
</style>
</head>
<body>
<header>
  <h1>Reim-Bewertung — {total} Paare aus deinen Texten</h1>
  <div class="sub">Bewerte jedes vom Algorithmus gefundene Reim-Paar von <b>0</b> (kein Reim / falsch)
  bis <b>10</b> (perfekter Reim, genau dein Geschmack). Score = was die Engine <i>aktuell</i> denkt.
  Wo sie danebenliegt, korrigiert dein Rating das Lernen. Fortschritt wird im Browser gespeichert
  (localStorage). Am Ende <b>Export JSON</b> → gib mir die Datei zurück, ich spiele sie ins Feedback-Training.</div>
</header>
<div class="wrap" id="list"></div>
<footer>
  <div class="prog"><b id="done">0</b> / {total} bewertet · <span class="hint">0-3 schlecht · 4-7 ok · 8-10 stark</span></div>
  <div class="btns">
    <button class="btn ghost" id="resetBtn">Zurücksetzen</button>
    <button class="btn" id="exportBtn">Export JSON</button>
  </div>
</footer>
<script>
const PAIRS = {data_json};
const KEY = "rheinwerker_reim_rating_v1";
let ratings = {{}};
try {{ ratings = JSON.parse(localStorage.getItem(KEY) || "{{}}"); }} catch(e) {{ ratings = {{}}; }}

const list = document.getElementById("list");
const doneEl = document.getElementById("done");

function bandColor(p) {{
  if (p.score >= 0.88) return "#5b8cff";
  if (p.score >= 0.72) return "#3fb6a8";
  if (p.score >= 0.65) return "#f1c40f";
  return "#e0773f";
}}
function ratingColor(v) {{
  if (v <= 3) return "var(--bad)";
  if (v <= 7) return "var(--mid)";
  return "var(--good)";
}}
function updateDone() {{ doneEl.textContent = Object.keys(ratings).length; }}

PAIRS.forEach((p, i) => {{
  const card = document.createElement("div");
  card.className = "card";
  card.style.borderLeftColor = bandColor(p);
  const scale = Array.from({{length:11}}, (_,v) =>
    `<button data-i="${{i}}" data-v="${{v}}">${{v}}</button>`).join("");
  card.innerHTML = `
    <div class="pair">${{esc(p.left)}}<span class="arrow">↔</span>${{esc(p.right)}}</div>
    <div class="meta">
      <span class="badge">Engine ${{p.score.toFixed(3)}}</span>
      <span class="badge">Anker ${{p.anchor}}</span>
      <span class="badge">Tail ${{p.tail}}</span>
      <span class="badge">Vokal ${{p.vowel}}</span>
      <span class="badge">Kadenz ${{p.cadence}}</span>
      <span class="badge">${{p.left_syl}}↔${{p.right_syl}} Silben</span>
      <span class="badge">${{esc(p.source_title)}}</span>
    </div>
    <div class="scale"><span class="lab">0–10</span>${{scale}}</div>
    <textarea class="cmt" data-ci="${{i}}" placeholder="Kommentar (optional, bleibt lokal)"></textarea>`;
  list.appendChild(card);

  const buttons = card.querySelectorAll(".scale button");
  function paint() {{
    const r = ratings[i];
    buttons.forEach(b => {{
      const v = +b.dataset.v;
      b.classList.toggle("sel", r && r.rating === v);
      b.style.background = (r && r.rating === v) ? ratingColor(v) : "#222732";
    }});
    card.classList.toggle("rated", !!r);
  }}
  buttons.forEach(b => b.addEventListener("click", () => {{
    const v = +b.dataset.v;
    const cmt = card.querySelector(".cmt").value.trim();
    ratings[i] = {{ rating:v, comment:cmt,
      query:p.query, source_title:p.source_title, line_no:p.line_no, phrase:p.phrase,
      left:p.left, right:p.right, engine_score:p.score }};
    localStorage.setItem(KEY, JSON.stringify(ratings));
    paint(); updateDone();
  }}));
  const ta = card.querySelector(".cmt");
  if (ratings[i]) ta.value = ratings[i].comment || "";
  ta.addEventListener("input", () => {{
    if (ratings[i]) {{ ratings[i].comment = ta.value.trim();
      localStorage.setItem(KEY, JSON.stringify(ratings)); }}
  }});
  paint();
}});
updateDone();

function esc(s) {{ return String(s).replace(/[&<>"]/g, c =>
  ({{ "&":"&amp;","<":"&lt;",">":"&gt;","\\"":"&quot;" }}[c])); }}

document.getElementById("exportBtn").addEventListener("click", () => {{
  const out = Object.values(ratings).map(r => ({{
    query:r.query, source_title:r.source_title, line_no:r.line_no, phrase:r.phrase,
    rating:r.rating, comment:r.comment||"", engine_score:r.engine_score,
    left:r.left, right:r.right
  }}));
  const blob = new Blob([JSON.stringify(out, null, 2)], {{type:"application/json"}});
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "reim_bewertung_export.json";
  a.click();
}});
document.getElementById("resetBtn").addEventListener("click", () => {{
  if (confirm("Alle Bewertungen löschen?")) {{ ratings = {{}};
    localStorage.removeItem(KEY); location.reload(); }}
}});
</script>
</body>
</html>
"""


def main() -> None:
    if not DB_PATH.exists():
        raise SystemExit(f"Keine Reim-DB unter {DB_PATH}. Erst importieren.")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        pairs = select_pairs(conn)
    finally:
        conn.close()
    OUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    OUT_HTML.write_text(render_html(pairs), "utf-8")
    bands: dict[str, int] = {}
    for p in pairs:
        bands[p["band"]] = bands.get(p["band"], 0) + 1
    print(f"OK: {len(pairs)} Paare -> {OUT_HTML}")
    for b in sorted(bands, reverse=True):
        print(f"  Band {b}: {bands[b]}")


if __name__ == "__main__":
    main()
