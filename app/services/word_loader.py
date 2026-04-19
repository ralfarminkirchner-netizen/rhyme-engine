import re, csv, json, hashlib, pickle, time, logging
from pathlib import Path
from typing import List, Optional
from app.schemas.rhyme import ParsedWord

logger = logging.getLogger(__name__)

# ── WordLoader ────────────────────────────────────────────────────────────────

class WordLoader:
    MIN = 2; MAX = 40
    ALLOWED = re.compile(r'^[a-zäöüß-]+$')
    BLACKLIST = {"", " ", "-", "--", "http", "https", "www"}

    @classmethod
    def load(cls, path: Path, max_words: Optional[int] = None) -> List[str]:
        if not path.exists():
            raise FileNotFoundError(path)
        if path.suffix == ".csv":  return cls._csv(path, max_words)
        if path.suffix == ".json": return cls._json(path, max_words)
        return cls._txt(path, max_words)

    @classmethod
    def _txt(cls, p: Path, n) -> List[str]:
        words = []
        with open(p, encoding="utf-8", errors="ignore") as f:
            for i, line in enumerate(f):
                if n and i >= n: break
                w = line.strip().lower().split()[0] if line.strip() else ""
                if cls._ok(w): words.append(w)
        return words

    @classmethod
    def _csv(cls, p: Path, n) -> List[str]:
        words = []
        with open(p, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            col = "word" if "word" in (reader.fieldnames or []) else (reader.fieldnames or [""])[0]
            for i, row in enumerate(reader):
                if n and i >= n: break
                w = row.get(col,"").strip().lower()
                if cls._ok(w): words.append(w)
        return words

    @classmethod
    def _json(cls, p: Path, n) -> List[str]:
        words = []
        data = json.loads(p.read_text("utf-8"))
        items = data if isinstance(data, list) else list(data.keys())
        for i, item in enumerate(items):
            if n and i >= n: break
            w = (item.get("word","") if isinstance(item, dict) else str(item)).strip().lower()
            if cls._ok(w): words.append(w)
        return words

    @classmethod
    def _ok(cls, w: str) -> bool:
        return bool(w and cls.MIN <= len(w) <= cls.MAX
                    and w not in cls.BLACKLIST and cls.ALLOWED.match(w) and not w.isdigit())

    @classmethod
    def load_multiple(cls, sources: List[Path], max_words: Optional[int] = None) -> List[str]:
        seen: set[str] = set()
        for src in sources:
            if src.exists():
                for w in cls.load(src, max_words):
                    seen.add(w)
        result = list(seen)
        return result[:max_words] if max_words else result


# ── WordCache ─────────────────────────────────────────────────────────────────

class WordCache:
    CACHE_DIR = Path("cache")
    VERSION   = 3

    @classmethod
    def _key(cls, words: List[str]) -> str:
        sample = "".join(sorted(words[:1000]))
        return hashlib.md5(f"{cls.VERSION}_{len(words)}_{sample}".encode()).hexdigest()

    @classmethod
    def load_or_process(
        cls,
        words: List[str],
        force: bool = False,
        max_workers: int = 4,
    ) -> List[ParsedWord]:
        from app.services.parser import parse_german_word
        cls.CACHE_DIR.mkdir(exist_ok=True)
        cache_path = cls.CACHE_DIR / f"{cls._key(words)}.pkl"

        if not force and cache_path.exists():
            try:
                data = pickle.loads(cache_path.read_bytes())
                logger.info(f"Cache hit: {len(data)} Wörter")
                return data
            except Exception:
                pass

        logger.info(f"Parse {len(words)} Wörter …")
        t0 = time.time()
        parsed = []
        for w in words:
            try: parsed.append(parse_german_word(w))
            except Exception: pass

        cache_path.write_bytes(pickle.dumps(parsed))
        logger.info(f"Fertig in {time.time()-t0:.1f}s → {len(parsed)} Wörter gecacht")
        return parsed
