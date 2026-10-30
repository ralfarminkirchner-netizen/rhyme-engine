"""Persistent multilingual sound atlas and corpus-backed rhyme discovery.

The indexed vocabulary is finite and source-backed. Longer word paths remain
composable; search materializes attested windows rather than pretending to
enumerate infinitely many possible German compounds and utterances.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sqlite3
import time
import unicodedata
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from uuid import uuid4

from app.services.atlas_phonetics import parse_ipa
from app.services.graph_pronunciation import pronounce_graph_word


DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "atlas"
WORD = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)*", re.UNICODE)
FAMILIES = ["a", "e", "i", "o", "u", "oe", "ue", "ai", "au", "oi", "ei", "ou", "schwa"]
VERSION = "reimatlas/1"


def packed(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def normalized(text):
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def compact(text):
    return "".join(character for character in normalized(text) if character.isalnum())


def now():
    return datetime.now(timezone.utc).isoformat()


def atlas_path():
    return Path(os.environ.get("REIM_ATLAS_DIR", str(DATA_DIR))).expanduser() / "atlas.sqlite"


class AtlasStore:
    def __init__(self, path=None):
        self.path = Path(path) if path else atlas_path()
        self._word_cache = {}

    @contextmanager
    def connect(self, write=False):
        if write:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.is_file() and not write:
            raise FileNotFoundError("Der Atlasbestand ist noch nicht aufgebaut.")
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            if write:
                conn.execute("pragma journal_mode=WAL")
                conn.execute("pragma synchronous=NORMAL")
            yield conn
            if write:
                conn.commit()
        finally:
            conn.close()

    def initialize(self):
        with self.connect(True) as conn:
            conn.executescript("""
                create table if not exists metadata(key text primary key,value text not null);
                create table if not exists sources(
                    id text primary key,name text not null,url text not null,license text not null,
                    manifest_json text not null,entry_count integer not null default 0
                );
                create table if not exists entries(
                    id integer primary key,entry_key text not null unique,
                    text text not null,norm text not null,compact text not null,
                    language text not null,kind text not null,origin text not null,
                    source_id text not null,source_ref text not null,ipa text not null,
                    syllable_count integer not null,first_family text not null,last_family text not null,
                    signature text not null,phonetics text not null,frequency real not null default 0
                );
                create index if not exists atlas_word_lookup on entries(norm,language);
                create index if not exists atlas_compact_lookup on entries(compact,language);
                create index if not exists atlas_sound_lookup on entries(syllable_count,last_family,first_family);
                create index if not exists atlas_source on entries(source_id);
                create index if not exists atlas_discovery_words on entries(language,kind,last_family,syllable_count,frequency desc);
                create table if not exists corpus_sentences(
                    id integer primary key,source_id text not null,sentence_id text not null,
                    text text not null,source_ref text not null,unique(source_id,sentence_id)
                );
                create virtual table if not exists corpus_fts using fts5(text,content='corpus_sentences',content_rowid='id');
                create table if not exists syllable_nodes(
                    key text primary key,nucleus text not null,family text not null,occurrences integer not null
                );
                create table if not exists sound_edges(
                    source text not null,target text not null,occurrences integer not null,
                    primary key(source,target)
                );
                create table if not exists rhyme_neighbors(
                    left_id integer not null,right_id integer not null,score real not null,
                    relation_json text not null,primary key(left_id,right_id)
                );
                create table if not exists chains(
                    id text primary key,title text not null,members_json text not null,created_at text not null
                );
                create table if not exists imports(source_id text primary key,rows integer not null,complete integer not null default 0);
                create table if not exists regions(
                    syllables integer not null,first_family text not null,last_family text not null,
                    language text not null,kind text not null,count integer not null,sample text not null,
                    primary key(syllables,first_family,last_family,language,kind)
                );
            """)

    def set_metadata(self, key, value):
        with self.connect(True) as conn:
            conn.execute("insert or replace into metadata values (?,?)", (key, packed(value)))

    def metadata(self, key, default=None):
        if not self.path.is_file():
            return default
        with self.connect() as conn:
            row = conn.execute("select value from metadata where key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def register_source(self, source_id, name, manifest):
        with self.connect(True) as conn:
            conn.execute("""insert into sources(id,name,url,license,manifest_json) values(?,?,?,?,?)
                on conflict(id) do update set name=excluded.name,url=excluded.url,
                license=excluded.license,manifest_json=excluded.manifest_json""", (
                source_id, name, manifest.get("download_url", manifest.get("url", "")),
                manifest.get("license", "Herkunft lokal dokumentiert"), packed(manifest),
            ))

    def prepare_entry(self, row, phonetics=None, frequency=0, kind=None):
        text = row["text"]
        ipa = row.get("ipa") or ""
        phonetics = phonetics or parse_ipa(ipa, row.get("language", "de"))
        language = "en" if row.get("language", "de").startswith("en") else row.get("language", "de")
        key = hashlib.sha256((row["source_id"] + "\0" + text + "\0" + ipa).encode()).hexdigest()
        return (
            key, text, normalized(text), compact(text), language, kind or row.get("kind", "word"),
            row.get("origin", "dictionary"), row["source_id"], packed(row.get("source_ref", {})), ipa,
            phonetics["syllable_count"], phonetics["first_family"], phonetics["last_family"],
            phonetics["signature"], packed(phonetics), frequency,
        )

    def insert_entries(self, prepared, conn=None):
        sql = """insert or ignore into entries(entry_key,text,norm,compact,language,kind,origin,
            source_id,source_ref,ipa,syllable_count,first_family,last_family,signature,phonetics,frequency)
            values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"""
        if conn is not None:
            conn.executemany(sql, prepared)
        else:
            with self.connect(True) as target:
                target.executemany(sql, prepared)

    def materialize(self, rows):
        """Add explored paths and their provenance without rescanning the atlas."""
        inserted, records = [], []
        with self.connect(True) as conn:
            for row in rows:
                data = row.get("data") or parse_ipa(row["ipa"], row.get("language", "de"))
                prepared = self.prepare_entry(row, data, row.get("frequency", 0))
                previous = conn.execute("select 1 from entries where norm=? and language=? limit 1", (prepared[2], prepared[4])).fetchone()
                before = conn.total_changes
                self.insert_entries([prepared], conn)
                found = dict(conn.execute("select * from entries where entry_key=?", (prepared[0],)).fetchone())
                records.append(found)
                if conn.total_changes == before:
                    continue
                inserted.append((found, previous is None))
                conn.execute("""insert into regions values(?,?,?,?,?,1,?)
                    on conflict(syllables,first_family,last_family,language,kind)
                    do update set count=count+1,sample=min(sample,excluded.sample)""",
                    (found["syllable_count"], found["first_family"], found["last_family"], found["language"], found["kind"], found["text"]))
                keys = []
                for syllable, nucleus, family in zip(data["syllables"], data["nuclei"], data["families"]):
                    key = " ".join(syllable); keys.append(key)
                    conn.execute("insert into syllable_nodes values(?,?,?,1) on conflict(key) do update set occurrences=occurrences+1", (key, nucleus, family))
                conn.executemany("insert into sound_edges values(?,?,1) on conflict(source,target) do update set occurrences=occurrences+1", zip(keys, keys[1:]))
            if inserted:
                stored = conn.execute("select value from metadata where key='counts'").fetchone()
                counts = json.loads(stored[0]) if stored else {}
                counts["entries"] = counts.get("entries", 0) + sum(fresh for _, fresh in inserted)
                counts["pronunciations"] = counts.get("pronunciations", 0) + len(inserted)
                for kind, name in (("word", "words"), ("compound", "compounds"), ("phrase", "phrases")):
                    counts[name] = counts.get(name, 0) + sum(row["kind"] == kind for row, _ in inserted)
                for name, table in (("sources", "sources"), ("syllable_nodes", "syllable_nodes"), ("sound_edges", "sound_edges")):
                    counts[name] = conn.execute(f"select count(*) from {table}").fetchone()[0]
                conn.execute("insert or replace into metadata values('counts',?)", (packed(counts),))
                conn.execute("insert or replace into metadata values('revision',?)", (packed(now()),))
                for source_id, count in Counter(row["source_id"] for row, _ in inserted).items():
                    conn.execute("update sources set entry_count=entry_count+? where id=?", (count, source_id))
        self._word_cache.clear()
        return records

    def lookup_word(self, text, language="de"):
        key = (text, language)
        if key in self._word_cache:
            return self._word_cache[key]
        with self.connect() as conn:
            row = conn.execute("select * from entries where norm=? and language=? order by text=? desc,source_id='ipa-de' desc,frequency desc,id limit 1", (normalized(text), language, text)).fetchone()
            if row is None:
                row = conn.execute("select * from entries where compact=? and language=? order by source_id='ipa-de' desc,frequency desc,id limit 1", (compact(text), language)).fetchone()
        value = dict(row) if row else None
        if len(self._word_cache) > 80000:
            self._word_cache.clear()
        self._word_cache[key] = value
        return value

    def pronounce(self, text, language="de", lexicon=None):
        exact = None if lexicon is not None else self.lookup_word(text, language)
        if exact:
            return json.loads(exact["phonetics"]), exact["ipa"], exact["id"]
        phones, stress, notes, ipas, used_fallback = [], [], [], [], False
        for token in WORD.findall(text):
            found_ipa = lexicon.get(normalized(token)) if lexicon is not None else None
            found = self.lookup_word(token, language) if lexicon is None else None
            if found:
                data, ipa = json.loads(found["phonetics"]), found["ipa"]
            elif found_ipa:
                ipa = found_ipa
                data = parse_ipa(ipa, language)
            else:
                raw, pattern, rules = pronounce_graph_word(token)
                from app.services.rhyme_graph import _graph_syllables
                from app.services.parser import is_vowel
                grouped, pattern = _graph_syllables(token, raw, pattern)
                rendered = []
                for index, syllable in enumerate(grouped):
                    heard_nucleus = False
                    tokens = []
                    for phone in syllable:
                        if phone == "ɐ" and heard_nucleus:
                            phone = "ɐ̯"
                        elif is_vowel(phone):
                            heard_nucleus = True
                        tokens.append(phone)
                    rendered.append(("ˈ" if pattern[index] else "") + "".join(tokens))
                ipa = ".".join(rendered)
                data = parse_ipa(ipa, language)
                data["stress"] = (pattern + [0] * len(data["syllables"]))[:len(data["syllables"])]
                notes.extend(rules)
                used_fallback = True
            ipas.append(ipa.strip("/[]"))
            phones.extend(data["syllables"])
            stress.extend(data["stress"])
            notes.extend(data.get("notes", []))
        joined = "/" + " ".join(ipas) + "/"
        # Preserve word-level pronunciation evidence while concatenating nuclei.
        data = parse_ipa(joined, language)
        data["syllables"] = phones
        data["stress"] = stress
        data["notes"] = list(dict.fromkeys([*data["notes"], *notes]))
        if used_fallback:
            data["notes"].append("Mindestens ein Wort besitzt nur eine ergänzende Regel-Aussprache.")
        return data, joined, None

    def refresh_statistics(self):
        with self.connect(True) as conn:
            conn.execute("delete from regions")
            conn.execute("""insert into regions select syllable_count,first_family,last_family,language,kind,
                count(*),min(text) from entries where syllable_count>0
                group by syllable_count,first_family,last_family,language,kind""")
            total = conn.execute("select count(*) from entries").fetchone()[0]
            lexical = conn.execute("select count(*) from (select norm,language from entries group by norm,language)").fetchone()[0]
            types = {row[0]: row[1] for row in conn.execute("select kind,count(*) from entries group by kind")}
            counts = {"entries": lexical, "pronunciations": total, "words": types.get("word", 0),
                      "phrases": types.get("phrase", 0), "compounds": types.get("compound", 0),
                      "sources": conn.execute("select count(*) from sources").fetchone()[0],
                      "syllable_nodes": conn.execute("select count(*) from syllable_nodes").fetchone()[0],
                      "sound_edges": conn.execute("select count(*) from sound_edges").fetchone()[0],
                      "chains": conn.execute("select count(*) from chains").fetchone()[0],
                      "corpus_sentences": conn.execute("select count(*) from corpus_sentences").fetchone()[0]}
            conn.execute("update sources set entry_count=(select count(*) from entries where entries.source_id=sources.id)+(select count(*) from corpus_sentences where corpus_sentences.source_id=sources.id)")
            conn.execute("insert or replace into metadata values ('counts',?)", (packed(counts),))
            conn.execute("insert or replace into metadata values ('revision',?)", (packed(now()),))
        return counts

    def status(self):
        if not self.path.is_file():
            return {"status": "empty", "revision": VERSION, "counts": {name: 0 for name in ("entries", "pronunciations", "words", "phrases", "compounds", "sources", "syllable_nodes", "sound_edges", "chains")}, "syllable_layers": [], "sources": []}
        with self.connect() as conn:
            sources = [dict(row) for row in conn.execute("""select id,name,url,license,entry_count,
                (select count(*) from entries where source_id=sources.id) as pronunciation_count,
                (select count(*) from corpus_sentences where source_id=sources.id) as sentence_count from sources""")]
            layers = [dict(row) for row in conn.execute("""select syllables,sum(count) as count,
                sum(case when kind='word' then count else 0 end) as words,
                sum(case when kind='phrase' then count else 0 end) as phrases,
                sum(case when kind='compound' then count else 0 end) as compounds
                from regions group by syllables order by syllables""")]
            chain_count = conn.execute("select count(*) from chains").fetchone()[0]
        counts = self.metadata("counts", {})
        counts["chains"] = chain_count
        build = self.metadata("build", {})
        return {"status": "building" if build.get("status") == "running" else ("ready" if counts.get("entries") else "empty"),
                "revision": self.metadata("revision", VERSION), "counts": counts, "syllable_layers": layers,
                "sources": sources, "build": build}

    def map(self, options):
        clauses, params = self._filters(options, region=True)
        with self.connect() as conn:
            if options.get("origin", "all") != "all" or options.get("include_combinations") is False:
                direct_clauses, direct_params = self._filters(options)
                rows = conn.execute("select syllable_count as syllables,first_family,last_family,count(*) as count,min(text) as sample from entries where " + " and ".join(direct_clauses) + " group by syllable_count,first_family,last_family order by count desc", direct_params).fetchall()
            else:
                rows = conn.execute("""select syllables,first_family,last_family,sum(count) as count,min(sample) as sample
                    from regions where """ + " and ".join(clauses) + " group by syllables,first_family,last_family order by count desc", params).fetchall()
        total = sum(row["count"] for row in rows)
        limit = options.get("limit", 300)
        # Keep even rare long layers visible before filling with large regions.
        selected, seen_layers = [], set()
        for row in rows:
            if row["syllables"] not in seen_layers:
                selected.append(row); seen_layers.add(row["syllables"])
        keys = {(row["syllables"], row["first_family"], row["last_family"]) for row in selected}
        for row in rows:
            key = (row["syllables"], row["first_family"], row["last_family"])
            if len(selected) >= limit:
                break
            if key not in keys:
                selected.append(row); keys.add(key)
        max_syllables = options.get("max_syllables", 32)
        min_syllables = options.get("min_syllables", 1)
        regions = []
        for row in selected:
            level = (row["syllables"] - min_syllables) / max(1, max_syllables - min_syllables)
            first = FAMILIES.index(row["first_family"]) if row["first_family"] in FAMILIES else 0
            last = FAMILIES.index(row["last_family"]) if row["last_family"] in FAMILIES else 0
            x = 0.04 + 0.70 * level + 0.22 * first / len(FAMILIES)
            y = 0.04 + 0.70 * level + 0.22 * last / len(FAMILIES)
            if min_syllables == max_syllables:
                x, y = .06 + .88 * first / (len(FAMILIES) - 1), .06 + .88 * last / (len(FAMILIES) - 1)
            regions.append({"id": f"{row['syllables']}:{row['first_family']}:{row['last_family']}",
                "syllables": row["syllables"], "first_family": row["first_family"], "last_family": row["last_family"],
                "count": row["count"], "x": x, "y": y, "samples": [row["sample"]]})
        return {"regions": regions, "total_entries": total, "layout": "Silbenzahl diagonal von oben links nach unten rechts; Lautfamilien ordnen die Nachbarschaften.", "max_syllables": max_syllables}

    def neighborhood(self, region, options):
        clauses, params = self._filters(options)
        clauses += ["syllable_count=?", "first_family=?", "last_family=?"]
        params += [region["syllables"], region["first_family"], region["last_family"]]
        with self.connect() as conn:
            rows = conn.execute("select signature,count(*) as count,min(text) as sample from entries where " +
                " and ".join(clauses) + " group by signature order by count desc limit ?", [*params, options.get("limit", 100)]).fetchall()
        return {"region": region, "signatures": [{"signature": row["signature"], "nuclei": row["signature"].split("-"),
                "count": row["count"], "samples": [row["sample"]]} for row in rows]}

    @staticmethod
    def _filters(options, region=False):
        field = "syllables" if region else "syllable_count"
        clauses = [f"{field} between ? and ?"]
        params = [options.get("min_syllables", 1), options.get("max_syllables", 64)]
        if options.get("kind", "all") != "all":
            clauses.append("kind=?"); params.append(options["kind"])
        languages = options.get("languages", ["de", "en"])
        if languages:
            clauses.append("language in (" + ",".join("?" for _ in languages) + ")"); params.extend(languages)
        if not region:
            origin = options.get("origin", "all")
            if origin == "attested": clauses.append("origin!='constructed'")
            elif origin == "constructed": clauses.append("origin='constructed'")
            if options.get("include_combinations") is False:
                clauses.append("origin!='constructed'")
        return clauses, params

    def _result(self, row, match=None, anchor=""):
        source_ref = json.loads(row["source_ref"])
        data = json.loads(row["phonetics"])
        with self.connect() as conn:
            source = conn.execute("select id,name,url,license from sources where id=?", (row["source_id"],)).fetchone()
        return {"id": row["id"], "text": row["text"], "ipa": row["ipa"], "language": row["language"],
            "kind": row["kind"], "syllable_count": row["syllable_count"], "nuclei": data["nuclei"],
            "syllables": data["syllables"], "origin": row["origin"],
            "source": {**(dict(source) if source else {"id": row["source_id"], "name": "Lokaler Bestand", "url": "", "license": "lokal"}),
                       **{key: source_ref[key] for key in ("author", "sentence_id", "url") if key in source_ref}},
            "source_ref": source_ref, "score": match["score"] if match else 0,
            "matched_anchor": anchor, "reason": match["reason"] if match else "Eintrag dieser Klangregion.",
            "notes": data.get("notes", []), "relation": match}

    def search(self, options):
        from app.services.atlas_matching import compare_pronunciations, candidate_families

        query = options.get("query", "").strip()
        raw_anchors = list(dict.fromkeys(item.strip() for item in query.splitlines() if item.strip()))[:24]
        excluded = {normalized(item) for item in raw_anchors}
        excluded_compact = {compact(item) for item in raw_anchors}
        anchors, all_rows, warnings, capped = [], {}, [], False
        region = options.get("region")
        if not raw_anchors and not region:
            return {"query": query, "anchors": [], "results": [], "searched_candidates": 0, "total_matches": 0, "warnings": ["Wähle eine Klangregion oder gib einen Reimanker ein."]}
        specific = options.get("_entry")
        for text in raw_anchors:
            if specific and specific["text"] == text:
                data, ipa, entry_id = json.loads(specific["phonetics"]), specific["ipa"], specific["id"]
            else:
                language = "en" if options.get("languages") == ["en"] else "de"
                if language == "de" and not self.lookup_word(text) and self.lookup_word(text, "en"):
                    language = "en"
                data, ipa, entry_id = self.pronounce(text, language)
            if not data["nuclei"]:
                continue
            anchors.append({"text": text, "ipa": ipa, "entry_id": entry_id, **data})
        clauses, params = self._filters(options)
        if region:
            clauses += ["syllable_count=?", "first_family=?", "last_family=?"]
            params += [region["syllables"], region["first_family"], region["last_family"]]
            if region.get("signature"):
                clauses.append("signature=?"); params.append(region["signature"])
            with self.connect() as conn:
                rows = conn.execute("select * from entries where " + " and ".join(clauses) + " order by frequency desc,id limit 2400", params).fetchall()
            all_rows.update({row["id"]: dict(row) for row in rows})
        else:
            for anchor in anchors:
                size = anchor["syllable_count"]
                flex = 2 if size >= 3 and options.get("mode", "dirty") == "dirty" else 0
                last_families = candidate_families(anchor["last_family"], options.get("mode", "dirty"))
                query_clauses = [*clauses, "syllable_count between ? and ?", "last_family in (" + ",".join("?" for _ in last_families) + ")"]
                query_params = [*params, max(1, size - flex), size + flex, *last_families]
                with self.connect() as conn:
                    rows = conn.execute("select * from entries where " + " and ".join(query_clauses) +
                        " order by first_family=? desc, frequency desc,id limit 3000", [*query_params, anchor["first_family"]]).fetchall()
                capped = capped or len(rows) == 3000
                all_rows.update({row["id"]: dict(row) for row in rows})
            if options.get("kind", "all") in {"all", "phrase"} and "de" in options.get("languages", ["de", "en"]):
                from app.services.atlas_discovery import discover
                generated = discover(self, anchors, options)
                if generated:
                    if any(row["origin"] == "constructed" for row in generated):
                        self.register_source("atlas-combinations", "Zusammengesetzte Klangpfade", {
                            "license": "Quellen und Lizenzen der Teilbelege beachten", "url": "",
                            "method": "Neu zusammengesetzt aus belegten Wortgruppen; der Übergang besitzt einen Satzbeleg.",
                        })
                    all_rows.update({row["id"]: row for row in self.materialize(generated)})
        ranked = []
        for row in all_rows.values():
            if row["norm"] in excluded or row["compact"] in excluded_compact:
                continue
            data = json.loads(row["phonetics"])
            best, best_anchor = None, ""
            for anchor in anchors:
                relation = compare_pronunciations(anchor, data, options.get("mode", "dirty"))
                if relation and (best is None or relation["score"] > best["score"]):
                    best, best_anchor = relation, anchor["text"]
            if not anchors and region:
                best = {"score": 0, "reason": "Ausgewählter Bereich im Klangatlas.", "kind": "near", "matched_syllables": data["syllable_count"], "details": {}}
            if best:
                bonus = min(0.025, math.log1p(row["frequency"]) * 0.002)
                # A rule reading of an unknown word is a weaker basis than
                # sourced IPA, even if its guessed vowels appear to match.
                fallback = any("Regel-Aussprache" in note for note in data.get("notes", []))
                uncertainty = .16 if fallback else .04 if data.get("unknown") else 0
                ranked.append((best["score"] + bonus - uncertainty, row, best, best_anchor))
        ranked.sort(key=lambda item: (-item[0], -item[1]["frequency"], len(item[1]["text"])))
        results, seen, seen_compact, families, origins, relations = [], set(), set(), Counter(), Counter(), []
        for _, row, relation, anchor in ranked:
            if row["norm"] in seen or row["compact"] in seen_compact:
                continue
            # A plural of an input anchor is not a new rhyme discovery.
            inflections = {"s", "es", "e", "en", "n", "er", "em"}
            if any((row["compact"].startswith(term) and row["compact"][len(term):] in inflections)
                   or (term.startswith(row["compact"]) and term[len(row["compact"]):] in inflections)
                   for term in excluded_compact if len(term) >= 5):
                continue
            # Inflection-heavy dictionaries must not fill a page with one stem.
            stem = row["norm"][:10] if row["kind"] != "phrase" else row["norm"]
            if families[stem] >= 3:
                continue
            if options.get("origin", "all") == "all" and row["origin"] == "constructed" and origins["constructed"] >= max(3, options.get("limit", 40) // 3):
                continue
            families[stem] += 1; seen.add(row["norm"]); seen_compact.add(row["compact"])
            origins[row["origin"]] += 1
            results.append(self._result(row, relation, anchor))
            anchor_record = next((record for record in anchors if record["text"] == anchor), None)
            if anchor_record and anchor_record.get("entry_id") and row["id"] != anchor_record["entry_id"]:
                relations.append((anchor_record["entry_id"], row["id"], relation["score"], packed(relation)))
            if len(results) >= options.get("limit", 40):
                break
        if relations:
            with self.connect(True) as conn:
                conn.executemany("""insert into rhyme_neighbors values(?,?,?,?)
                    on conflict(left_id,right_id) do update set score=excluded.score,relation_json=excluded.relation_json""", relations)
        if capped:
            warnings.append("Die Nachbarsuche prüft einen begrenzten, nach Klang und Häufigkeit vorgeordneten Ausschnitt; weitere Bereiche lassen sich über die Filter erschließen.")
        return {"query": query, "anchors": [{key: value for key, value in anchor.items() if key != "syllables"} for anchor in anchors],
            "results": results, "searched_candidates": len(all_rows), "total_matches": len(ranked), "warnings": warnings}

    def expand(self, entry_id, options):
        with self.connect() as conn:
            row = conn.execute("select * from entries where id=?", (entry_id,)).fetchone()
        if row is None:
            raise KeyError(entry_id)
        return self.search({**options, "query": row["text"], "_entry": dict(row)})

    def chains(self):
        if not self.path.is_file():
            return {"chains": []}
        with self.connect() as conn:
            rows = conn.execute("select * from chains order by created_at desc limit 200").fetchall()
        return {"chains": [{"id": row["id"], "title": row["title"], "created_at": row["created_at"],
                            "members": json.loads(row["members_json"])} for row in rows]}

    def save_chain(self, title, members):
        resolved = []
        self.register_source("user-local", "Eigene Reimfolgen · lokal", {"url": "", "license": "Privater lokaler Bestand"})
        for index, text in enumerate(members):
            requested_id = text.get("entry_id") if isinstance(text, dict) else None
            text = text["text"] if isinstance(text, dict) else text
            exact = None
            if requested_id:
                with self.connect() as conn:
                    exact = conn.execute("select * from entries where id=?", (requested_id,)).fetchone()
                if exact is None or compact(exact["text"]) != compact(text):
                    raise ValueError("Der ausgewählte Ausspracheeintrag passt nicht zum Reimsegment.")
            if exact:
                data, ipa, entry_id, language = json.loads(exact["phonetics"]), exact["ipa"], exact["id"], exact["language"]
            else:
                language = "en" if not self.lookup_word(text) and self.lookup_word(text, "en") else "de"
                data, ipa, entry_id = self.pronounce(text, language)
            if entry_id is None:
                saved = self.materialize([{"text": text, "ipa": ipa, "language": language, "kind": "phrase" if len(WORD.findall(text)) > 1 else "word",
                    "origin": "user", "source_id": "user-local", "source_ref": {"pronunciation_basis": "Wörterbuchteile; ergänzende Regelaussprache ist in den Notizen markiert"}, "data": data}])[0]
                entry_id = saved["id"]
            resolved.append({"position": index, "text": text, "entry_id": entry_id,
                "syllable_count": data["syllable_count"], "nuclei": data["nuclei"],
                "families": data["families"], "first_family": data["first_family"], "last_family": data["last_family"], "ipa": ipa, "language": language})
        chain = {"id": str(uuid4()), "title": title, "created_at": now(), "members": resolved}
        with self.connect(True) as conn:
            conn.execute("insert into chains values(?,?,?,?)", (chain["id"], title, packed(resolved), chain["created_at"]))
        return chain
