"""Convention de chemins sous results/ (extract/ vs themes/ vs scorer/)."""

from __future__ import annotations

from pathlib import Path

EXTRACT_DIR = "extract"
THEMES_DIR = "themes"
SCORER_DIR = "scorer"
POSTS_STEM = "posts"
_RUN_SUBDIRS = frozenset({EXTRACT_DIR, THEMES_DIR, SCORER_DIR})


def dossier_run(path: Path) -> Path:
    """
    Dossier d'un run (…/limit_N ou …/date_range) à partir d'un fichier ou sous-dossier.
    """
    p = path.resolve()
    if p.is_file():
        p = p.parent
    if p.name in _RUN_SUBDIRS:
        return p.parent
    return p


def chemin_extract_posts(run_dir: Path) -> Path:
    return run_dir / EXTRACT_DIR / f"{POSTS_STEM}.jsonl"


def chemin_themes_jsonl(run_dir: Path) -> Path:
    return run_dir / THEMES_DIR / f"{POSTS_STEM}.themes.jsonl"


def chemin_scorer_jsonl(run_dir: Path) -> Path:
    return run_dir / SCORER_DIR / f"{POSTS_STEM}.sentiment.jsonl"


def chemin_scorer_meta(run_dir: Path) -> Path:
    return run_dir / SCORER_DIR / f"{POSTS_STEM}.sentiment.meta.json"


def chemin_rapport_corpus_xlsx(run_dir: Path) -> Path:
    return run_dir / SCORER_DIR / f"{POSTS_STEM}_Corpus_Report.xlsx"


def chemin_rapport_corpus_meta(run_dir: Path) -> Path:
    return run_dir / SCORER_DIR / f"{POSTS_STEM}_Corpus_Report.report_meta.json"


def prefixe_scorer_sortie(input_jsonl: Path) -> Path:
    """
    Si l'entrée est …/extract/posts.jsonl → sortie …/scorer/posts (sans extension).
    Sinon → même dossier que l'entrée (comportement legacy).
    """
    inp = input_jsonl.resolve()
    if inp.parent.name == EXTRACT_DIR and inp.name == f"{POSTS_STEM}.jsonl":
        run_dir = inp.parent.parent
        scorer_dir = run_dir / SCORER_DIR
        scorer_dir.mkdir(parents=True, exist_ok=True)
        return scorer_dir / POSTS_STEM
    return inp.with_suffix("")
