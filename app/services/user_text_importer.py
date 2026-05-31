"""Import user Pages/text files into a local rhyme database."""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import subprocess
import time
import unicodedata
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from app.services.parser import is_vowel, parse_german_word
from app.services.phrase_scorer import PhraseFeatures, score_rhyme


DATA_ROOT = Path("app/data/user_texts")
INBOX_DIR = DATA_ROOT / "inbox"
EXTRACTED_DIR = DATA_ROOT / "extracted"
DB_PATH = DATA_ROOT / "rhyme_database.sqlite"
SUMMARY_PATH = DATA_ROOT / "import_summary.json"

WORD_RE = re.compile(r"[A-Za-zÄÖÜäöüß]+")
TEXT_FRAGMENT_RE = re.compile(
    r"[A-Za-zÄÖÜäöüß0-9][A-Za-zÄÖÜäöüß0-9 .,:;!?()/'’´`\"„“”\-]{2,}"
)

JUNK_EXACT = {
    "title", "subtitle", "heading 1", "heading 2", "subheading 1",
    "subheading 2", "body", "body 1", "body bullet", "bullet",
    "caption", "caption 1", "header & footer", "label", "label dark",
    "shape caption", "shape caption white", "text", "titel", "untertitel",
    "freie form", "notentext", "kopf- und fusszeilen", "iso-a4", "blank",
    "standard toc", "de_de",
}
JUNK_CONTAINS = (
    "sqlite format", "create table", "imported-", "application/blank",
    "documentstylesheet", "documentmetadata", "buildversionhistory",
)


@dataclass
class ImportedDocumentInfo:
    source_id: str
    title: str
    path: str
    kind: str
    extraction_method: str
    status: str
    line_count: int = 0
    rhyme_unit_count: int = 0
    warning: str = ""


@dataclass
class RhymeUnit:
    id: int
    source_id: str
    source_title: str
    line_no: int
    line_text: str
    phrase: str
    word_count: int
    syllable_count: int
    terminal_anchor: str
    terminal_vowel: str
    terminal_vowel_family: str
    terminal_tail: str
    phrase_vowels: str


@dataclass
class RhymePairSample:
    left_phrase: str
    right_phrase: str
    score: float
    source_title: str
    left_line_no: int
    right_line_no: int


@dataclass
class UserTextDatabaseSummary:
    inbox_dir: str
    extracted_dir: str
    database_path: str
    source_count: int
    imported_count: int
    skipped_count: int
    line_count: int
    rhyme_unit_count: int
    rhyme_pair_count: int
    documents: List[ImportedDocumentInfo] = field(default_factory=list)
    sample_pairs: List[RhymePairSample] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


def _source_id(path: Path) -> str:
    digest = hashlib.sha1(str(path.resolve()).encode("utf-8")).hexdigest()[:10]
    stem = re.sub(r"[^A-Za-z0-9]+", "-", path.stem).strip("-").lower()[:40]
    return f"{stem or 'source'}-{digest}"


def _document_kind(path: Path) -> str:
    suffix = path.suffix.lower()
    if path.is_file() and suffix == ".pages":
        return "pages_zip"
    if path.is_dir() and suffix == ".pages" and (path / "Index.zip").exists():
        return "pages_package_zip"
    if path.is_dir() and (path / "index.db").exists():
        return "pages_tef_db"
    if path.is_file() and suffix in {".txt", ".md"}:
        return "plain_text"
    return "unsupported"


def _discover_sources(inbox_dir: Path) -> List[Path]:
    if not inbox_dir.exists():
        return []
    return sorted(
        path
        for path in inbox_dir.iterdir()
        if path.name != ".DS_Store" and _document_kind(path) != "unsupported"
    )


def _clean_line(raw: str) -> str:
    text = unicodedata.normalize("NFKC", raw)
    text = text.replace("\u00a0", " ").replace("\ufeff", "")
    text = "".join(ch if ch == "\t" or ch == "\n" or not unicodedata.category(ch).startswith("C") else " " for ch in text)
    text = " ".join(text.strip().split())
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    return text.strip()


def _looks_like_text_line(line: str) -> bool:
    if not line:
        return False
    lower = line.lower().strip()
    if lower in JUNK_EXACT:
        return False
    if any(marker in lower for marker in JUNK_CONTAINS):
        return False
    letters = WORD_RE.findall(line)
    letter_count = sum(len(part) for part in letters)
    if letter_count < 2:
        return False
    if len(line) > 260:
        return False
    if letter_count / max(len(line), 1) < 0.35:
        return False
    return True


def _dedupe(lines: Iterable[str]) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    for raw in lines:
        line = _clean_line(raw)
        if not _looks_like_text_line(line):
            continue
        key = line.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(line)
    return out


def _lines_from_text(text: str) -> List[str]:
    return _dedupe(text.splitlines())


def _strings_from_bytes(data: bytes) -> List[str]:
    chunks: List[str] = []
    seen: set[str] = set()
    for encoding in ("utf-8", "utf-16-le", "utf-16-be"):
        decoded = data.decode(encoding, errors="ignore")
        decoded = unicodedata.normalize("NFKC", decoded)
        for match in TEXT_FRAGMENT_RE.finditer(decoded):
            line = _clean_line(match.group(0))
            key = line.lower()
            if key and key not in seen:
                seen.add(key)
                chunks.append(line)
    return _dedupe(chunks)


PAGES_EXPORT_SCRIPT = """
on run argv
    set inputPath to POSIX file (item 1 of argv)
    set outputPath to POSIX file (item 2 of argv)
    tell application "Pages"
        launch
        set theDoc to open inputPath
        export theDoc to outputPath as unformatted text
        close theDoc saving no
    end tell
end run
"""


def _try_pages_export(path: Path, output_path: Path, timeout_seconds: int = 60) -> tuple[Optional[str], str]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.unlink(missing_ok=True)
    try:
        subprocess.run(["open", "-gj", "-a", "Pages"], check=False, capture_output=True, timeout=20)
        time.sleep(1.0)
        completed = subprocess.run(
            ["osascript", "-e", PAGES_EXPORT_SCRIPT, str(path.resolve()), str(output_path.resolve())],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except Exception as exc:
        return None, f"Pages export failed: {exc}"

    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        return None, f"Pages export failed: {detail}"
    if not output_path.exists() or output_path.stat().st_size == 0:
        return None, "Pages export produced no text"
    return output_path.read_text("utf-8", errors="ignore"), ""


def _extract_zip_iwa(path: Path) -> List[str]:
    chunks: List[str] = []
    with zipfile.ZipFile(path) as zf:
        for name in zf.namelist():
            if not name.startswith("Index/") or not name.endswith(".iwa"):
                continue
            if "DocumentStylesheet" in name or "ViewState" in name:
                continue
            chunks.extend(_strings_from_bytes(zf.read(name)))
    return _dedupe(chunks)


def _extract_index_zip(path: Path) -> List[str]:
    return _extract_zip_iwa(path / "Index.zip")


def _extract_index_db(path: Path) -> List[str]:
    db = path / "index.db"
    chunks: List[str] = []
    uri = f"file:{db.resolve()}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True)
        try:
            for table, column in (("objects", "state"), ("dataStates", "state")):
                try:
                    rows = conn.execute(f"select {column} from {table}").fetchall()
                except sqlite3.Error:
                    continue
                for (blob,) in rows:
                    if isinstance(blob, bytes):
                        chunks.extend(_strings_from_bytes(blob))
        finally:
            conn.close()
    except sqlite3.Error:
        chunks.extend(_strings_from_bytes(db.read_bytes()))
    return _dedupe(chunks)


def _extract_document(path: Path, extracted_dir: Path, prefer_pages_export: bool) -> tuple[List[str], str, str]:
    kind = _document_kind(path)
    export_target = extracted_dir / f"{_source_id(path)}.txt"
    warning = ""

    if prefer_pages_export and kind.startswith("pages"):
        text, warning = _try_pages_export(path, export_target)
        if text:
            lines = _lines_from_text(text)
            if lines:
                return lines, "pages_export", warning

    try:
        if kind == "plain_text":
            return _lines_from_text(path.read_text("utf-8", errors="ignore")), "plain_text", warning
        if kind == "pages_zip":
            return _extract_zip_iwa(path), "iwa_strings", warning
        if kind == "pages_package_zip":
            return _extract_index_zip(path), "index_zip_strings", warning
        if kind == "pages_tef_db":
            return _extract_index_db(path), "index_db_strings", warning
    except Exception as exc:
        return [], "failed", f"{warning}; fallback failed: {exc}".strip("; ")

    return [], "unsupported", warning


def _vowel_family(phoneme: str) -> str:
    families = {
        "a": "a", "aː": "a",
        "ɛ": "e", "eː": "e", "œ": "oe", "øː": "oe",
        "ɪ": "i", "iː": "i",
        "ɔ": "o", "oː": "o",
        "ʊ": "u", "uː": "u",
        "ʏ": "ue", "yː": "ue",
        "aɪ": "ai", "aʊ": "au", "ɔʏ": "eu",
    }
    return families.get(phoneme, phoneme)


def _last_vowel(phonemes: List[str]) -> str:
    for phoneme in reversed(phonemes):
        if is_vowel(phoneme):
            return phoneme
    return ""


def _line_tail_unit(
    line: str,
    source_id: str,
    source_title: str,
    line_no: int,
    unit_id: int,
) -> Optional[RhymeUnit]:
    words = WORD_RE.findall(line)
    if not words:
        return None

    parsed_words = []
    for word in words:
        try:
            parsed_words.append((word, parse_german_word(word)))
        except Exception:
            continue
    if not parsed_words:
        return None

    window: List[tuple[str, Any]] = []
    syllables = 0
    for word, parsed in reversed(parsed_words):
        next_count = syllables + parsed.syllable_count
        if window and next_count > 8:
            break
        window.append((word, parsed))
        syllables = next_count
        if syllables >= 8:
            break

    window = list(reversed(window))
    if syllables < 3 or syllables > 8:
        return None

    phrase = " ".join(word for word, _parsed in window)
    try:
        features = PhraseFeatures.from_phrase(phrase)
    except Exception:
        return None

    terminal_vowel = _last_vowel(features.anchor)
    return RhymeUnit(
        id=unit_id,
        source_id=source_id,
        source_title=source_title,
        line_no=line_no,
        line_text=line,
        phrase=phrase,
        word_count=len(window),
        syllable_count=syllables,
        terminal_anchor=" ".join(features.anchor),
        terminal_vowel=terminal_vowel,
        terminal_vowel_family=_vowel_family(terminal_vowel) if terminal_vowel else "",
        terminal_tail=" ".join(features.end_tail),
        phrase_vowels=" ".join(features.phrase_vowels),
    )


def _build_units(source_id: str, source_title: str, lines: List[str], start_id: int) -> List[RhymeUnit]:
    units: List[RhymeUnit] = []
    next_id = start_id
    for line_no, line in enumerate(lines, 1):
        unit = _line_tail_unit(line, source_id, source_title, line_no, next_id)
        if unit is None:
            continue
        units.append(unit)
        next_id += 1
    return units


def _create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        drop table if exists rhyme_pairs;
        drop table if exists rhyme_units;
        drop table if exists lines;
        drop table if exists documents;

        create table documents (
            source_id text primary key,
            title text not null,
            path text not null,
            kind text not null,
            extraction_method text not null,
            status text not null,
            line_count integer not null,
            rhyme_unit_count integer not null,
            warning text not null
        );

        create table lines (
            id integer primary key autoincrement,
            source_id text not null,
            line_no integer not null,
            text text not null
        );

        create table rhyme_units (
            id integer primary key,
            source_id text not null,
            source_title text not null,
            line_no integer not null,
            line_text text not null,
            phrase text not null,
            word_count integer not null,
            syllable_count integer not null,
            terminal_anchor text not null,
            terminal_vowel text not null,
            terminal_vowel_family text not null,
            terminal_tail text not null,
            phrase_vowels text not null
        );

        create table rhyme_pairs (
            id integer primary key autoincrement,
            left_unit_id integer not null,
            right_unit_id integer not null,
            source_id text not null,
            score real not null,
            anchor real not null,
            tail real not null,
            vowel real not null,
            cadence real not null
        );

        create index idx_units_family on rhyme_units(terminal_vowel_family);
        create index idx_units_source on rhyme_units(source_id, line_no);
        create index idx_pairs_score on rhyme_pairs(score desc);
        """
    )


def _write_database(
    db_path: Path,
    documents: List[ImportedDocumentInfo],
    doc_lines: Dict[str, List[str]],
    units: List[RhymeUnit],
    context_radius: int,
) -> List[RhymePairSample]:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        _create_schema(conn)
        conn.executemany(
            """
            insert into documents (
                source_id, title, path, kind, extraction_method, status,
                line_count, rhyme_unit_count, warning
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    doc.source_id, doc.title, doc.path, doc.kind,
                    doc.extraction_method, doc.status, doc.line_count,
                    doc.rhyme_unit_count, doc.warning,
                )
                for doc in documents
            ],
        )
        line_rows = [
            (source_id, line_no, line)
            for source_id, lines in doc_lines.items()
            for line_no, line in enumerate(lines, 1)
        ]
        conn.executemany("insert into lines (source_id, line_no, text) values (?, ?, ?)", line_rows)
        conn.executemany(
            """
            insert into rhyme_units (
                id, source_id, source_title, line_no, line_text, phrase,
                word_count, syllable_count, terminal_anchor, terminal_vowel,
                terminal_vowel_family, terminal_tail, phrase_vowels
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    unit.id, unit.source_id, unit.source_title, unit.line_no,
                    unit.line_text, unit.phrase, unit.word_count,
                    unit.syllable_count, unit.terminal_anchor, unit.terminal_vowel,
                    unit.terminal_vowel_family, unit.terminal_tail, unit.phrase_vowels,
                )
                for unit in units
            ],
        )

        pairs: List[tuple[int, int, str, float, float, float, float, float]] = []
        samples: List[RhymePairSample] = []
        by_source: Dict[str, List[RhymeUnit]] = {}
        for unit in units:
            by_source.setdefault(unit.source_id, []).append(unit)

        for source_units in by_source.values():
            ordered = sorted(source_units, key=lambda unit: unit.line_no)
            for i, left in enumerate(ordered):
                for right in ordered[i + 1:]:
                    if right.line_no - left.line_no > context_radius:
                        break
                    if left.terminal_vowel_family != right.terminal_vowel_family:
                        continue
                    try:
                        score = score_rhyme(left.phrase, right.phrase)
                    except Exception:
                        continue
                    if score.total < 0.58:
                        continue
                    pairs.append(
                        (
                            left.id, right.id, left.source_id, score.total,
                            score.anchor, score.tail, score.vowel, score.cadence,
                        )
                    )
                    samples.append(
                        RhymePairSample(
                            left_phrase=left.phrase,
                            right_phrase=right.phrase,
                            score=score.total,
                            source_title=left.source_title,
                            left_line_no=left.line_no,
                            right_line_no=right.line_no,
                        )
                    )

        conn.executemany(
            """
            insert into rhyme_pairs (
                left_unit_id, right_unit_id, source_id, score,
                anchor, tail, vowel, cadence
            ) values (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            pairs,
        )
        conn.commit()
    finally:
        conn.close()

    return sorted(samples, key=lambda pair: pair.score, reverse=True)[:20]


def refresh_user_text_database(
    inbox_dir: Path = INBOX_DIR,
    data_root: Path = DATA_ROOT,
    prefer_pages_export: bool = True,
    context_radius: int = 12,
) -> UserTextDatabaseSummary:
    extracted_dir = data_root / "extracted"
    db_path = data_root / "rhyme_database.sqlite"
    summary_path = data_root / "import_summary.json"
    extracted_dir.mkdir(parents=True, exist_ok=True)

    sources = _discover_sources(inbox_dir)
    documents: List[ImportedDocumentInfo] = []
    doc_lines: Dict[str, List[str]] = {}
    units: List[RhymeUnit] = []
    warnings: List[str] = []
    next_unit_id = 1

    for path in sources:
        source_id = _source_id(path)
        title = path.stem
        kind = _document_kind(path)
        lines, method, warning = _extract_document(path, extracted_dir, prefer_pages_export)
        if warning:
            warnings.append(f"{path.name}: {warning}")
        status = "imported" if lines else "skipped"

        source_units: List[RhymeUnit] = []
        if lines:
            extracted_path = extracted_dir / f"{source_id}.txt"
            extracted_path.write_text("\n".join(lines) + "\n", "utf-8")
            doc_lines[source_id] = lines
            source_units = _build_units(source_id, title, lines, next_unit_id)
            next_unit_id += len(source_units)
            units.extend(source_units)

        documents.append(
            ImportedDocumentInfo(
                source_id=source_id,
                title=title,
                path=str(path),
                kind=kind,
                extraction_method=method,
                status=status,
                line_count=len(lines),
                rhyme_unit_count=len(source_units),
                warning=warning,
            )
        )

    sample_pairs = _write_database(db_path, documents, doc_lines, units, context_radius)

    summary = UserTextDatabaseSummary(
        inbox_dir=str(inbox_dir),
        extracted_dir=str(extracted_dir),
        database_path=str(db_path),
        source_count=len(sources),
        imported_count=sum(1 for doc in documents if doc.status == "imported"),
        skipped_count=sum(1 for doc in documents if doc.status != "imported"),
        line_count=sum(doc.line_count for doc in documents),
        rhyme_unit_count=len(units),
        rhyme_pair_count=_count_rows(db_path, "rhyme_pairs"),
        documents=documents,
        sample_pairs=sample_pairs,
        warnings=warnings[:30],
    )
    summary_path.write_text(json.dumps(asdict(summary), ensure_ascii=False, indent=2) + "\n", "utf-8")
    return summary


def _count_rows(db_path: Path, table: str) -> int:
    if not db_path.exists():
        return 0
    conn = sqlite3.connect(db_path)
    try:
        return int(conn.execute(f"select count(*) from {table}").fetchone()[0])
    finally:
        conn.close()


def load_user_text_summary(data_root: Path = DATA_ROOT) -> Dict[str, Any]:
    summary_path = data_root / "import_summary.json"
    if not summary_path.exists():
        return {
            "inbox_dir": str(data_root / "inbox"),
            "extracted_dir": str(data_root / "extracted"),
            "database_path": str(data_root / "rhyme_database.sqlite"),
            "source_count": 0,
            "imported_count": 0,
            "skipped_count": 0,
            "line_count": 0,
            "rhyme_unit_count": 0,
            "rhyme_pair_count": 0,
            "documents": [],
            "sample_pairs": [],
            "warnings": ["Noch kein Import gelaufen."],
        }
    return json.loads(summary_path.read_text("utf-8"))


def _syllable_fit(query_syllables: int, candidate_syllables: int) -> float:
    diff = abs(query_syllables - candidate_syllables)
    if diff == 0:
        return 1.0
    if diff == 1:
        return 0.88
    if diff == 2:
        return 0.70
    if diff == 3:
        return 0.52
    return 0.40


def _phrase_window_fit(candidate_syllables: int) -> float:
    if 4 <= candidate_syllables <= 6:
        return 1.0
    if 3 <= candidate_syllables <= 8:
        return 0.86
    return 0.55


def _terminal_fit(score: Any) -> float:
    if score.anchor >= 0.90 and score.tail >= 0.90:
        return 1.0
    if score.anchor >= 0.78 and score.tail >= 0.70:
        return 0.90
    if score.anchor >= 0.70 and score.tail >= 0.50:
        return 0.78
    if score.anchor >= 0.62 and score.vowel >= 0.85:
        return 0.66
    if score.anchor >= 0.55:
        return 0.48
    return 0.0


def _personal_phrase_score(
    score: Any,
    query_syllables: int,
    candidate_syllables: int,
    candidate_word_count: int,
) -> float:
    """Personal ranking profile for 3-8-syllable phrase-level rap rhymes."""
    phrase_grip = (score.cadence * 0.65) + (score.global_v * 0.35)
    multi_word_fit = 1.0 if candidate_word_count > 1 else 0.78
    profile = (
        _terminal_fit(score) * 0.40
        + _syllable_fit(query_syllables, candidate_syllables) * 0.25
        + _phrase_window_fit(candidate_syllables) * 0.15
        + multi_word_fit * 0.10
        + phrase_grip * 0.10
    )

    final_score = score.total * (0.45 + 0.55 * profile)

    # Keep weak/non-anchors from climbing through cadence or vowel-spine fit.
    if score.anchor < 0.55:
        final_score = min(final_score, 0.35)
    elif score.anchor < 0.62:
        final_score = min(final_score, 0.44)
    elif score.anchor < 0.70 and score.tail < 0.45:
        final_score = min(final_score, 0.58)

    return round(min(final_score, 0.9999), 4)


def search_user_rhymes(
    query: str,
    db_path: Path = DB_PATH,
    limit: int = 30,
    min_score: float = 0.0,
    rerank: bool = False,
    rerank_candidate_count: int = 120,
    include_context_in_rerank: bool = False,
) -> Dict[str, Any]:
    if not db_path.exists():
        return {"query": query, "results": [], "warning": "Reimdatenbank fehlt. Erst importieren."}

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            select id, source_title, line_no, line_text, phrase, syllable_count
            from rhyme_units
            """
        ).fetchall()
    finally:
        conn.close()

    try:
        q_syllables = PhraseFeatures.from_phrase(query).syllable_count
    except Exception:
        q_syllables = max(1, len(WORD_RE.findall(query)) * 2)

    results: List[Dict[str, Any]] = []
    for row in rows:
        try:
            score = score_rhyme(query, row["phrase"])
        except Exception:
            continue

        cand_syllables = row["syllable_count"]
        cand_words = len(WORD_RE.findall(row["phrase"]))
        final_score = _personal_phrase_score(score, q_syllables, cand_syllables, cand_words)

        if final_score < min_score:
            continue

        results.append(
            {
                "phrase": row["phrase"],
                "score": round(final_score, 4),
                "raw_score": score.total,
                "anchor": score.anchor,
                "tail": score.tail,
                "vowel": score.vowel,
                "cadence": score.cadence,
                "source_title": row["source_title"],
                "line_no": row["line_no"],
                "line_text": row["line_text"],
                "syllable_count": row["syllable_count"],
                "reason": score.reason,
            }
        )

    results.sort(
        key=lambda item: (item["score"], item["raw_score"], item["anchor"], item["tail"]),
        reverse=True,
    )

    rerank_info: Dict[str, Any] = {"enabled": False, "provider": "none"}
    if rerank:
        from app.services.ai_reranker import rerank_rhymes

        pool_size = max(limit, min(max(1, rerank_candidate_count), 250))
        pool = results[:pool_size]
        reranked = rerank_rhymes(query, pool)
        results = reranked["results"]
        rerank_info = {
            key: value
            for key, value in reranked.items()
            if key not in {"results"}
        }

    return {
        "query": query,
        "results": results[:limit],
        "total_candidates": len(rows),
        "retrieved_candidates": len(results),
        "rerank": rerank_info,
    }
