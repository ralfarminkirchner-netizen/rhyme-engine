#!/usr/bin/env python3
"""Build/resume the real local atlas from provenance-preserving open sources."""
from __future__ import annotations

import argparse
from collections import Counter
import fcntl
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.atlas_corpus import iter_ipa_entries, iter_thesaurus_entries, iter_tatoeba_entries
from app.services.atlas_phonetics import parse_ipa, split_ipa_variants
from app.services.rhyme_atlas import AtlasStore, DATA_DIR, WORD, normalized, packed, now


def build(manifest_path):
    store = AtlasStore()
    store.initialize()
    lock = (store.path.parent / "build.lock").open("w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit("Ein Atlasaufbau läuft bereits; kein zweiter Worker gestartet.")
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    sources = manifest["sources"]
    frequencies = Counter()
    corpus = next((source for source in sources if "tatoeba" in source["path"]), None)
    if corpus:
        print("Zähle Worthäufigkeiten aus dem vollständig vorhandenen Satzkorpus …", flush=True)
        for row in iter_tatoeba_entries(corpus["path"], "tatoeba-de"):
            frequencies.update(normalized(word) for word in WORD.findall(row["text"]))
    german = next(source for source in sources if "ipa-de" in source["path"])
    lexicon = {}
    with Path(german["path"]).open(encoding="utf-8") as handle:
        for raw in handle:
            text, field = raw.rstrip("\r\n").split("\t", 1)
            variants = split_ipa_variants(field)
            if variants:
                key = normalized(text)
                # Lowercase function words must not inherit acronym readings
                # such as IM /i ɛm/ instead of im /ɪm/.
                if key not in lexicon or text == text.casefold():
                    lexicon[key] = variants[0]
    lexical_words = {term for term in lexicon if term.isalpha()}
    for source in sources:
        filename = Path(source["path"]).name
        if filename == "ipa-de.txt":
            source_id, name, rows = "ipa-de", "Wiktionary · deutsche Aussprache", iter_ipa_entries(source["path"], "de", "ipa-de")
        elif filename == "ipa-en_US.txt":
            source_id, name, rows = "ipa-en", "CMUdict/IPA-Dict · Englisch", iter_ipa_entries(source["path"], "en", "ipa-en")
        elif filename == "openthesaurus.txt":
            source_id, name, rows = "openthesaurus", "OpenThesaurus · Wörter und Wendungen", iter_thesaurus_entries(source["path"], "openthesaurus")
        elif "tatoeba" in filename:
            source_id, name, rows = "tatoeba-de", "Tatoeba · belegte deutsche Wortfolgen", iter_tatoeba_entries(source["path"], "tatoeba-de")
        else:
            continue
        store.register_source(source_id, name, source)
        with store.connect() as conn:
            previous = conn.execute("select rows,complete from imports where source_id=?", (source_id,)).fetchone()
        if previous and previous["complete"]:
            print(f"{source_id}: vorhandener vollständiger Import bleibt erhalten.", flush=True)
            continue
        skip = previous["rows"] if previous else 0
        processed, batch, nodes, edges = 0, [], Counter(), Counter()
        source_started = time.monotonic()

        def checkpoint(complete=False):
            nonlocal batch, nodes, edges
            with store.connect(True) as conn:
                if source_id == "tatoeba-de":
                    old_max = conn.execute("select coalesce(max(id),0) from corpus_sentences").fetchone()[0]
                    conn.executemany("insert or ignore into corpus_sentences(source_id,sentence_id,text,source_ref) values(?,?,?,?)", batch)
                    conn.execute("insert into corpus_fts(rowid,text) select id,text from corpus_sentences where id>?", (old_max,))
                else:
                    store.insert_entries(batch, conn)
                    conn.executemany("""insert into syllable_nodes values(?,?,?,?)
                        on conflict(key) do update set occurrences=occurrences+excluded.occurrences""",
                        [(key, nucleus, family, count) for (key, nucleus, family), count in nodes.items()])
                    conn.executemany("""insert into sound_edges values(?,?,?)
                        on conflict(source,target) do update set occurrences=occurrences+excluded.occurrences""",
                        [(left, right, count) for (left, right), count in edges.items()])
                conn.execute("insert or replace into imports values(?,?,?)", (source_id, processed, int(complete)))
                progress = {"status": "running", "source": source_id, "processed": processed,
                            "source_rows": source.get("pronunciation_variants", source.get("line_count")),
                            "elapsed_seconds": round(time.monotonic() - source_started, 1), "updated_at": now()}
                conn.execute("insert or replace into metadata values('build',?)", (packed(progress),))
            batch, nodes, edges = [], Counter(), Counter()

        for row in rows:
            processed += 1
            if processed <= skip:
                continue
            if source_id == "tatoeba-de":
                ref = row["source_ref"]
                batch.append((source_id, str(ref["sentence_id"]), row["text"], packed(ref)))
            else:
                if row.get("ipa"):
                    data = parse_ipa(row["ipa"], row.get("language", "de"))
                else:
                    data, ipa, _ = store.pronounce(row["text"], lexicon=lexicon)
                    row["ipa"] = ipa
                    row["source_ref"]["pronunciation_basis"] = "composed from dictionary words; gaps use explicit rule fallback"
                text, kind = row["text"], row["kind"]
                if kind == "word" and row.get("language") == "de" and text[:1].isupper():
                    low = normalized(text)
                    if "-" in low:
                        kind = "compound"
                        row["source_ref"]["components"] = text.split("-")
                    elif len(low) >= 9:
                        for split in range(3, len(low) - 3):
                            if low[:split] in lexical_words and low[split:] in lexical_words:
                                kind = "compound"
                                row["source_ref"]["components"] = [text[:split], text[split:]]
                                row["source_ref"]["construction_basis"] = "lexical-parts hypothesis"
                                break
                tokens = WORD.findall(text)
                frequency = min((frequencies[normalized(word)] for word in tokens), default=0)
                batch.append(store.prepare_entry(row, data, frequency, kind))
                keys = []
                for syllable, nucleus, family in zip(data["syllables"], data["nuclei"], data["families"]):
                    key = " ".join(syllable)
                    nodes[(key, nucleus, family)] += 1
                    keys.append(key)
                edges.update(zip(keys, keys[1:]))
            if len(batch) >= 5000:
                checkpoint()
                if processed % 25000 == 0:
                    print(f"{source_id}: {processed:,} Quellvarianten verarbeitet", flush=True)
        checkpoint(True)
        print(f"{source_id}: {processed:,} vollständig; aktualisiere Kartenregionen …", flush=True)
        print(store.refresh_statistics(), flush=True)
    store.set_metadata("build", {"status": "complete", "updated_at": now(), "sources": len(sources)})
    print("Atlasaufbau abgeschlossen.", flush=True)
    return store.status()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DATA_DIR / "sources-manifest.json")
    options = parser.parse_args()
    build(options.manifest)
