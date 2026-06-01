import subprocess
import sys
from pathlib import Path


def test_pipeline_cli_runs_end_to_end_without_printing_full_context(tmp_path: Path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "rap.txt").write_text(
        "\n".join(
            [
                "nachts wach lieg im Bett",
                "absichtlich erschreckt",
                "lass die finger weg",
                "machen wir es jetzt",
                "wackeliges brett",
                "plastik im besteck",
            ]
        )
        + "\n",
        "utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/run_personal_rhyme_pipeline.py",
            "schattenkabinett",
            "--inbox",
            str(inbox),
            "--data-root",
            str(tmp_path),
            "--no-pages-export",
            "--min-pair-score",
            "0.50",
            "--min-score",
            "0.35",
            "--limit",
            "4",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert "Status:              ok" in completed.stdout
    assert "Trainingsbeispiele:" in completed.stdout
    assert "Reranker:            local (True)" in completed.stdout
    assert "Top-Phrasen:" in completed.stdout
    assert "nachts wach lieg im Bett" not in completed.stdout


def test_pipeline_cli_returns_nonzero_without_sources(tmp_path: Path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/run_personal_rhyme_pipeline.py",
            "schattenkabinett",
            "--inbox",
            str(inbox),
            "--data-root",
            str(tmp_path),
            "--no-pages-export",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 2
    assert "Status:              no_training_pairs" in completed.stdout
