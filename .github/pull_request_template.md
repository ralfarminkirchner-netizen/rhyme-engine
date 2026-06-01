## Scope

- [ ] Change supports the personal Rheinwerker rhyme-library goal.
- [ ] Change is not Rainbow Light, Godot, Antigravity, or unrelated game work.
- [ ] Legacy word search behavior is preserved unless intentionally changed.

## Rhyme Quality

- [ ] 3-8 syllable phrase-level end rhymes are prioritized where relevant.
- [ ] Terminal anchor matches are weighted above spelling or visual similarity.
- [ ] Rhythm, cadence, and flow density are considered.
- [ ] Vowel spine is only a secondary signal.

## Privacy

- [ ] No private Pages/text contents are committed.
- [ ] No extracted text files are committed.
- [ ] No SQLite databases are committed.
- [ ] No JSONL training data or local model files are committed.
- [ ] No generated catalogues or user images are committed.

## Verification

```bash
python3 -m pytest -q
npm run build --prefix frontend
python3 -m py_compile scripts/run_personal_rhyme_pipeline.py app/services/personal_rhyme_pipeline.py app/services/local_rhyme_model.py
find app/data/user_texts -maxdepth 3 -type f -print | sort
```

Expected data-folder result: only `.gitkeep` files.
