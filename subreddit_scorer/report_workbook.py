#!/usr/bin/env python3
"""
Build an Excel report from posts.jsonl + posts.sentiment.jsonl (+ themes if present).

Run from repo root:
  python3 subreddit_scorer/report_workbook.py --help
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd

from jsonl_io import read_jsonl, write_json
from paths import (
    chemin_extract_posts,
    chemin_rapport_corpus_meta,
    chemin_rapport_corpus_xlsx,
    chemin_scorer_jsonl,
    chemin_themes_jsonl,
    dossier_run,
)

_EXCEL_HELPERS_PATH = (
    Path(__file__).resolve().parent.parent / "subreddit_themes" / "excel_helpers.py"
)


def _excel_helpers() -> Any:
    spec = importlib.util.spec_from_file_location(
        "theme_excel_helpers", _EXCEL_HELPERS_PATH
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {_EXCEL_HELPERS_PATH}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_by_id(path: Path) -> dict[str, dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for row in read_jsonl(path):
        pid = row.get("id")
        if pid is not None:
            by_id[str(pid)] = row
    return by_id


def _sentiment_fields(s: dict[str, Any]) -> dict[str, Any]:
    sent_scores = s.get("sentiment_scores")
    if isinstance(sent_scores, dict):
        sentiment_scores_json = json.dumps(sent_scores, ensure_ascii=False)
    else:
        sentiment_scores_json = ""
    return {
        "sentiment_label": s.get("sentiment_label"),
        "sentiment_score": s.get("sentiment_score"),
        "sentiment_polarity_index": s.get("sentiment_polarity_index"),
        "sentiment_scores_json": sentiment_scores_json,
        "sentiment_classifier_note": s.get("sentiment_classifier_note", ""),
    }


def merge_posts_corpus_basic(
    posts: list[dict[str, Any]],
    sentiment_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    for row in posts:
        pid = str(row.get("id", ""))
        s = sentiment_by_id.get(pid, {})
        title = (row.get("title") or "") or ""
        body = (row.get("selftext") or "") or ""
        text = f"{title}\n{body}".strip() if title and body else (title or body).strip()
        merged.append(
            {
                "id": row.get("id"),
                "created_utc": row.get("created_utc"),
                "title": title,
                "selftext": body,
                "text_for_review": text,
                **_sentiment_fields(s),
            }
        )
    return merged


def attach_sentiment(
    rows: list[dict[str, Any]],
    sentiment_by_id: dict[str, dict[str, Any]],
) -> None:
    for record in rows:
        pid = str(record.get("id", ""))
        record.update(_sentiment_fields(sentiment_by_id.get(pid, {})))


def _corpus_column_order(
    df: pd.DataFrame,
    categories: list[dict[str, str]],
    has_themes: bool,
) -> list[str]:
    short_names = [c["short_name"] for c in categories]
    front = [
        "id",
        "created_utc",
        "title",
        "selftext",
        "text_for_review",
    ]
    sentiment = [
        "sentiment_label",
        "sentiment_polarity_index",
        "sentiment_score",
        "sentiment_scores_json",
        "sentiment_classifier_note",
    ]
    theme_summary = [
        "theme_labels",
        "theme_label",
        "theme_score",
    ]
    label_cols = [f"label_{s}" for s in short_names if f"label_{s}" in df.columns]
    score_cols = [f"score_{s}" for s in short_names if f"score_{s}" in df.columns]
    tail = ["theme_classifier_note", "theme_scores_json"]

    ordered: list[str] = []
    blocks = front + sentiment
    if has_themes:
        blocks += theme_summary + label_cols + score_cols + tail
    for col in blocks:
        if col in df.columns and col not in ordered:
            ordered.append(col)
    for col in df.columns:
        if col not in ordered:
            ordered.append(col)
    return ordered


def sentiment_distribution(rows: list[dict[str, Any]]) -> pd.DataFrame:
    labels = []
    for r in rows:
        lab = r.get("sentiment_label")
        if lab is None or lab == "":
            labels.append("(no text)")
        else:
            labels.append(str(lab))
    c = Counter(labels)
    total = sum(c.values()) or 1
    out = [
        {"sentiment": k, "count": v, "percent": round(100.0 * v / total, 2)}
        for k, v in sorted(c.items(), key=lambda x: (-x[1], x[0]))
    ]
    return pd.DataFrame(out)


def guide_sheet_rows() -> pd.DataFrame:
    rows = [
        ("Posts_corpus", "Une ligne = un post Reddit. Lire text_for_review pour la relecture."),
        ("text_for_review", "Titre + message complets (retours à la ligne activés)."),
        ("sentiment_label", "positive / negative / neutral (RoBERTa Twitter)."),
        ("sentiment_polarity_index", "Indice −1…+1 : P(positive) − P(negative). Plus bas = plus négatif."),
        ("theme_labels", "Catégories retenues (score thème ≥ 0,40), une par ligne dans la cellule."),
        ("label_*", "1 = catégorie retenue, 0 = non. Ex. label_digestive_relevance filtre stomie digestive."),
        ("label_crisis_suicidal_ideation", "1 = relecture manuelle recommandée avant toute stat."),
        ("label_hospital_to_home_transition", "Catégorie C9 — priorité recherche (transition hôpital–domicile)."),
        ("score_*", "Confiance brute du modèle BART (0–1). Utile pour les cas limites."),
        ("Filtre Excel conseillé", "label_digestive_relevance = 1 pour le corpus digestif."),
        ("Exclure des stats", "label_crisis_suicidal_ideation = 0 (ou relire les = 1)."),
        ("Theme_distribution", "Nombre de posts par catégorie (multi-label : % cumulables > 100 %)."),
        ("Sentiment_distribution", "Répartition positive / negative / neutral."),
    ]
    return pd.DataFrame(rows, columns=["Élément", "Description"])


def format_created_utc(df: pd.DataFrame) -> pd.DataFrame:
    if "created_utc" not in df.columns or df.empty:
        return df
    s = pd.to_datetime(df["created_utc"], unit="s", utc=True, errors="coerce")
    try:
        if getattr(s.dt, "tz", None) is not None:
            df = df.copy()
            df["created_utc"] = s.dt.tz_convert("UTC").dt.tz_localize(None)
        else:
            df = df.copy()
            df["created_utc"] = s
    except (TypeError, AttributeError):
        df = df.copy()
        df["created_utc"] = s
    return df


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Join posts + sentiment (+ themes) → Excel corpus under scorer/."
    )
    ap.add_argument(
        "--run-dir",
        type=Path,
        default=None,
        help="Dossier d'un run (…/limit_N) : lit extract/, scorer/, themes/ si présent",
    )
    ap.add_argument(
        "-i",
        "--posts",
        type=Path,
        default=None,
        help="Path to posts.jsonl",
    )
    ap.add_argument(
        "-s",
        "--sentiment",
        type=Path,
        default=None,
        help="Path to posts.sentiment.jsonl",
    )
    ap.add_argument(
        "-t",
        "--themes",
        type=Path,
        default=None,
        help="Path to posts.themes.jsonl (optionnel)",
    )
    ap.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output .xlsx (défaut si --run-dir : …/scorer/posts_Corpus_Report.xlsx)",
    )
    args = ap.parse_args()

    if args.run_dir:
        run_dir = dossier_run(args.run_dir)
        posts_path = args.posts or chemin_extract_posts(run_dir)
        sentiment_path = args.sentiment or chemin_scorer_jsonl(run_dir)
        themes_path = args.themes or chemin_themes_jsonl(run_dir)
        out_xlsx_default = chemin_rapport_corpus_xlsx(run_dir)
    else:
        if not args.posts or not args.sentiment:
            print(
                "Indiquez --run-dir OU les chemins -i/--posts et -s/--sentiment.",
                file=sys.stderr,
            )
            sys.exit(2)
        posts_path = args.posts
        sentiment_path = args.sentiment
        themes_path = args.themes
        out_xlsx_default = None

    posts_path = Path(posts_path)
    sentiment_path = Path(sentiment_path)
    themes_path = Path(themes_path) if themes_path else None

    if not posts_path.is_file():
        print(f"Posts file not found: {posts_path}", file=sys.stderr)
        sys.exit(1)
    if not sentiment_path.is_file():
        print(f"Sentiment file not found: {sentiment_path}", file=sys.stderr)
        sys.exit(1)

    posts = read_jsonl(posts_path)
    sentiment_by_id = load_by_id(sentiment_path)
    themes_by_id: dict[str, dict[str, Any]] | None = None
    has_themes = False
    categories: list[dict[str, str]] = []
    meta_themes: dict[str, Any] = {}

    if themes_path and themes_path.is_file():
        themes_by_id = load_by_id(themes_path)
        has_themes = True
        themes_meta_path = themes_path.parent / f"{themes_path.stem}.meta.json"
        if themes_meta_path.is_file():
            with open(themes_meta_path, encoding="utf-8") as f:
                meta_themes = json.load(f)

    if has_themes and themes_by_id is not None:
        xh = _excel_helpers()
        threshold = meta_themes.get("threshold")
        threshold_f = float(threshold) if threshold is not None else None
        categories = xh.category_order(meta_themes)
        if not categories:
            categories = xh.infer_category_order(themes_by_id)
        merged = xh.merge_posts_and_themes(
            posts, themes_by_id, categories, threshold_f
        )
        attach_sentiment(merged, sentiment_by_id)
    else:
        merged = merge_posts_corpus_basic(posts, sentiment_by_id)
        xh = _excel_helpers()

    out_xlsx = args.output
    if out_xlsx is None:
        out_xlsx = out_xlsx_default or (
            posts_path.parent / f"{posts_path.stem}_Corpus_Report.xlsx"
        )
    out_xlsx = Path(out_xlsx)
    out_xlsx.parent.mkdir(parents=True, exist_ok=True)

    df_posts = format_created_utc(pd.DataFrame(merged))
    if not df_posts.empty:
        df_posts = df_posts[_corpus_column_order(df_posts, categories, has_themes)]

    df_sent_dist = sentiment_distribution(merged)
    df_guide = guide_sheet_rows()

    meta_posts: dict[str, Any] = {}
    meta_path = posts_path.parent / f"{posts_path.stem}.meta.json"
    if meta_path.is_file():
        with open(meta_path, encoding="utf-8") as f:
            meta_posts = json.load(f)

    meta_sentiment: dict[str, Any] = {}
    sent_meta_path = sentiment_path.parent / f"{sentiment_path.stem}.meta.json"
    if sent_meta_path.is_file():
        with open(sent_meta_path, encoding="utf-8") as f:
            meta_sentiment = json.load(f)

    run_info = {
        "posts_jsonl": str(posts_path.resolve()),
        "sentiment_jsonl": str(sentiment_path.resolve()),
        "themes_jsonl": str(themes_path.resolve()) if has_themes and themes_path else None,
        "posts_meta": meta_posts,
        "sentiment_meta": meta_sentiment,
        "themes_meta": meta_themes if has_themes else None,
    }
    if args.run_dir:
        info_path = chemin_rapport_corpus_meta(dossier_run(args.run_dir))
    else:
        info_path = out_xlsx.with_suffix(".report_meta.json")
    write_json(info_path, run_info)

    info_rows = [
        ("posts_jsonl", str(posts_path.resolve())),
        ("sentiment_jsonl", str(sentiment_path.resolve())),
        ("themes_jsonl", str(themes_path.resolve()) if has_themes and themes_path else ""),
        ("n_posts", len(merged)),
        ("themes_included", has_themes),
        ("sentiment_meta_model", meta_sentiment.get("model", "")),
        ("sentiment_meta_instant", meta_sentiment.get("instant_utc", "")),
        ("polarity_index_formula", meta_sentiment.get("polarity_index_formula", "")),
    ]
    if has_themes:
        info_rows.extend(
            [
                ("themes_meta_model", meta_themes.get("model", "")),
                ("themes_meta_instant", meta_themes.get("instant_utc", "")),
                ("themes_threshold", meta_themes.get("threshold", "")),
                ("themes_classification_mode", meta_themes.get("classification_mode", "")),
            ]
        )

    with pd.ExcelWriter(out_xlsx, engine="openpyxl") as writer:
        df_guide.to_excel(writer, sheet_name="Guide", index=False)
        df_posts.to_excel(writer, sheet_name="Posts_corpus", index=False)
        df_sent_dist.to_excel(writer, sheet_name="Sentiment_distribution", index=False)
        if has_themes and categories:
            xh.theme_distribution(merged, categories).to_excel(
                writer, sheet_name="Theme_distribution", index=False
            )
        pd.DataFrame([{"key": k, "value": v} for k, v in info_rows]).to_excel(
            writer, sheet_name="Run_info", index=False
        )
        xh.format_posts_worksheet(
            writer.sheets["Posts_corpus"],
            list(df_posts.columns),
        )
        guide_ws = writer.sheets["Guide"]
        guide_ws.column_dimensions["A"].width = 36
        guide_ws.column_dimensions["B"].width = 72
        from openpyxl.styles import Alignment, Font

        for row in guide_ws.iter_rows(min_row=1, max_row=guide_ws.max_row):
            for cell in row:
                cell.alignment = Alignment(wrap_text=True, vertical="top")
                if cell.row == 1:
                    cell.font = Font(bold=True)

    print(f"Wrote {out_xlsx}")
    print(f"Wrote {info_path}")
    if not has_themes:
        print("Note: themes file absent — run subreddit_themes first for label_* columns.", flush=True)


if __name__ == "__main__":
    main()
