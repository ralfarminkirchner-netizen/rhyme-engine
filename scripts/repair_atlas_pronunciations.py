#!/usr/bin/env python3
"""Repair composed atlas pronunciations without rebuilding or replacing IDs.

The original database is backed up before the write transaction. Only entries
from the selected composed source are recomputed; all source references and
IDs remain. Sound-node/transition counts and map regions are then recomputed
from the actual persisted pronunciation rows in the same transaction.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import fcntl
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import sys
import time
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.atlas_phonetics import split_ipa_variants
from app.services.rhyme_atlas import AtlasStore, normalized, packed, now


REPAIR_VERSION = "composed-lexicon-case/1"


def german_lexicon(manifest: Path) -> dict[str, str]:
    sources = json.loads(manifest.read_text(encoding="utf-8"))["sources"]
    source = next(item for item in sources if Path(item["path"]).name == "ipa-de.txt")
    lexicon: dict[str, str] = {}
    with Path(source["path"]).open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            text, field = line.rstrip("\r\n").split("\t", 1)
            variants = split_ipa_variants(field)
            if variants:
                key = normalized(text)
                # Exactly the fixed builder rule: a lexical lowercase form
                # wins over a differently cased acronym with the same norm.
                if key not in lexicon or text == text.casefold():
                    lexicon[key] = variants[0]
    return lexicon


@lru_cache(maxsize=65536)
def _sound_key(phones: tuple[str, ...]) -> str:
    return " ".join(phones)


def _refresh_derived(conn: sqlite3.Connection) -> dict:
    nodes, edges = Counter(), Counter()
    syllables_total = transitions_total = pronunciation_count = 0
    cursor = conn.execute("select phonetics from entries order by id")
    for row in cursor:
        data = json.loads(row[0])
        syllables, nuclei, families = data["syllables"], data["nuclei"], data["families"]
        if len(syllables) != len(nuclei) or len(syllables) != len(families):
            raise ValueError("Persisted pronunciation has inconsistent syllable/nucleus/family lengths.")
        keys = []
        for syllable, nucleus, family in zip(syllables, nuclei, families):
            key = _sound_key(tuple(syllable))
            nodes[(key, nucleus, family)] += 1
            keys.append(key)
        edges.update(zip(keys, keys[1:]))
        syllables_total += len(syllables)
        transitions_total += max(0, len(syllables) - 1)
        pronunciation_count += 1
        if pronunciation_count % 200000 == 0:
            print(f"Derived sounds: {pronunciation_count:,} pronunciation rows scanned", flush=True)
    if sum(nodes.values()) != syllables_total or sum(edges.values()) != transitions_total:
        raise AssertionError("Derived occurrence counts are inconsistent.")

    conn.execute("create temp table repaired_sound_nodes(key text primary key,nucleus text,family text,occurrences integer)")
    conn.execute("create temp table repaired_sound_edges(source text,target text,occurrences integer,primary key(source,target))")
    conn.executemany("insert into repaired_sound_nodes values(?,?,?,?)", (
        (key, nucleus, family, count) for (key, nucleus, family), count in nodes.items()
    ))
    conn.executemany("insert into repaired_sound_edges values(?,?,?)", (
        (left, right, count) for (left, right), count in edges.items()
    ))
    # No table is dropped. Preserve each extant natural-key record and replace
    # its derived count; remove only derived keys that no entry realizes now.
    conn.execute("""insert into syllable_nodes select * from repaired_sound_nodes where true
        on conflict(key) do update set nucleus=excluded.nucleus,family=excluded.family,occurrences=excluded.occurrences""")
    conn.execute("delete from syllable_nodes where not exists(select 1 from repaired_sound_nodes n where n.key=syllable_nodes.key)")
    conn.execute("""insert into sound_edges select * from repaired_sound_edges where true
        on conflict(source,target) do update set occurrences=excluded.occurrences""")
    conn.execute("delete from sound_edges where not exists(select 1 from repaired_sound_edges e where e.source=sound_edges.source and e.target=sound_edges.target)")
    conn.execute("delete from regions")
    conn.execute("""insert into regions select syllable_count,first_family,last_family,language,kind,
        count(*),min(text) from entries where syllable_count>0
        group by syllable_count,first_family,last_family,language,kind""")
    conn.execute("""update sources set entry_count=(select count(*) from entries where entries.source_id=sources.id)
        +(select count(*) from corpus_sentences where corpus_sentences.source_id=sources.id)""")
    types = dict(conn.execute("select kind,count(*) from entries group by kind"))
    counts = {
        "entries": conn.execute("select count(*) from (select norm,language from entries group by norm,language)").fetchone()[0],
        "pronunciations": pronunciation_count, "words": types.get("word", 0),
        "phrases": types.get("phrase", 0), "compounds": types.get("compound", 0),
        "sources": conn.execute("select count(*) from sources").fetchone()[0],
        "syllable_nodes": len(nodes), "sound_edges": len(edges),
        "chains": conn.execute("select count(*) from chains").fetchone()[0],
        "corpus_sentences": conn.execute("select count(*) from corpus_sentences").fetchone()[0],
    }
    conn.execute("insert or replace into metadata values ('counts',?)", (packed(counts),))
    conn.execute("insert or replace into metadata values ('revision',?)", (packed(now()),))
    return {"counts": counts, "syllable_occurrences": syllables_total, "transition_occurrences": transitions_total}


def repair(database: Path, manifest: Path, source_id: str = "openthesaurus") -> dict:
    store = AtlasStore(database)
    if not database.is_file():
        raise FileNotFoundError(database)
    lexicon = german_lexicon(manifest)
    lexical_probes = {word: lexicon.get(word) for word in ("im", "in", "am", "an", "der", "die", "das")}
    if not lexical_probes["im"] or not lexical_probes["in"]:
        raise ValueError("The German dictionary lacks required lexical function-word probes.")
    timestamp = now()
    backup = database.with_name(f"{database.stem}.before-pronunciation-repair-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid4().hex[:8]}.sqlite")
    if shutil.disk_usage(database.parent).free < database.stat().st_size * 2.5:
        raise OSError("Insufficient free disk space for a full backup and transaction journal.")
    lock_path = database.parent / "build.lock"
    with lock_path.open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError("Another atlas worker is running; the repair did not start.") from error
        conn = sqlite3.connect(database, timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            backup.touch(exist_ok=False)
            destination = sqlite3.connect(backup)
            try:
                conn.backup(destination, pages=8192)
            finally:
                destination.close()
            print(f"Backup complete: {backup}", flush=True)
            conn.execute("pragma journal_mode=WAL")
            conn.execute("pragma synchronous=NORMAL")
            conn.execute("begin immediate")
            before_count = conn.execute("select count(*) from entries").fetchone()[0]
            rows = conn.execute("select id,text,ipa,phonetics,source_ref from entries where source_id=? order by id", (source_id,)).fetchall()
            conn.execute("create temp table repaired_entry_ids(id integer primary key)")
            changed, batch = 0, []
            for scanned, row in enumerate(rows, 1):
                data, ipa, _ = store.pronounce(row["text"], lexicon=lexicon)
                size = data["syllable_count"]
                if any(len(data[key]) != size for key in ("syllables", "stress", "nuclei", "families")):
                    raise ValueError(f"Repair generated inconsistent pronunciation at entry {row['id']}.")
                reference = json.loads(row["source_ref"])
                reference["pronunciation_basis"] = "composed from German dictionary words; lowercase lexical readings preferred over acronyms; gaps use explicit rule fallback"
                reference["pronunciation_repair"] = {
                    "version": REPAIR_VERSION, "at": timestamp,
                    "previous_ipa_sha256": hashlib.sha256(row["ipa"].encode()).hexdigest(),
                }
                key = hashlib.sha256((source_id + "\0" + row["text"] + "\0" + ipa).encode()).hexdigest()
                serialized = packed(data)
                if ipa != row["ipa"] or serialized != row["phonetics"]:
                    changed += 1
                    conn.execute("insert into repaired_entry_ids values(?)", (row["id"],))
                batch.append((key, packed(reference), ipa, size, data["first_family"], data["last_family"], data["signature"], serialized, row["id"]))
                if len(batch) >= 5000:
                    conn.executemany("""update entries set entry_key=?,source_ref=?,ipa=?,syllable_count=?,
                        first_family=?,last_family=?,signature=?,phonetics=? where id=?""", batch)
                    batch.clear()
                    print(f"Composed source: {scanned:,}/{len(rows):,}; changed pronunciation rows {changed:,}", flush=True)
            if batch:
                conn.executemany("""update entries set entry_key=?,source_ref=?,ipa=?,syllable_count=?,
                    first_family=?,last_family=?,signature=?,phonetics=? where id=?""", batch)
            invalidated = conn.execute("""delete from rhyme_neighbors
                where left_id in (select id from repaired_entry_ids) or right_id in (select id from repaired_entry_ids)""").rowcount
            derived = _refresh_derived(conn)
            after_count = conn.execute("select count(*) from entries").fetchone()[0]
            if before_count != after_count:
                raise AssertionError("Entry IDs/row count were not preserved.")
            report = {
                "version": REPAIR_VERSION, "at": timestamp, "source_id": source_id,
                "database": str(database), "backup": str(backup), "source_rows": len(rows),
                "changed_pronunciations": changed, "invalidated_neighbor_cache_rows": invalidated,
                "entry_rows_preserved": after_count, "lexical_probes": lexical_probes, **derived,
            }
            conn.execute("insert or replace into metadata values ('pronunciation_repair',?)", (packed(report),))
            conn.commit()
            conn.execute("pragma wal_checkpoint(truncate)")
            return report
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    store = AtlasStore(args.database)
    manifest = args.manifest or store.path.parent / "sources-manifest.json"
    started = time.monotonic()
    result = repair(store.path, manifest)
    result["elapsed_seconds"] = round(time.monotonic() - started, 2)
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
