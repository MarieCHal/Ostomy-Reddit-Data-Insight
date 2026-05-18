"""Convention de chemins sous results/ (extract/ vs themes/)."""

from __future__ import annotations

from pathlib import Path

EXTRACT_DIR = "extract"
THEMES_DIR = "themes"
POSTS_STEM = "posts"


def dossier_run(path: Path) -> Path:
    """
    Dossier d'un run (…/limit_N ou …/date_range) à partir d'un fichier ou sous-dossier.
    """
    p = path.resolve()
    if p.is_file():
        p = p.parent
    if p.name in (EXTRACT_DIR, THEMES_DIR):
        return p.parent
    return p


def chemin_extract_posts(run_dir: Path) -> Path:
    return run_dir / EXTRACT_DIR / f"{POSTS_STEM}.jsonl"


def chemin_themes_jsonl(run_dir: Path) -> Path:
    return run_dir / THEMES_DIR / f"{POSTS_STEM}.themes.jsonl"


def chemin_themes_meta(run_dir: Path) -> Path:
    return run_dir / THEMES_DIR / f"{POSTS_STEM}.themes.meta.json"


def chemin_rapport_xlsx(run_dir: Path) -> Path:
    return run_dir / THEMES_DIR / f"{POSTS_STEM}_Themes_Report.xlsx"


def chemin_rapport_meta(run_dir: Path) -> Path:
    return run_dir / THEMES_DIR / f"{POSTS_STEM}_Themes_Report.report_meta.json"


def prefixe_themes_sortie(input_jsonl: Path) -> Path:
    """
    Si l'entrée est …/extract/posts.jsonl → sortie …/themes/posts (sans extension).
    Sinon → même dossier que l'entrée (comportement legacy).
    """
    inp = input_jsonl.resolve()
    if inp.parent.name == EXTRACT_DIR and inp.name == f"{POSTS_STEM}.jsonl":
        run_dir = inp.parent.parent
        themes_dir = run_dir / THEMES_DIR
        themes_dir.mkdir(parents=True, exist_ok=True)
        return themes_dir / POSTS_STEM
    return inp.with_suffix("")
