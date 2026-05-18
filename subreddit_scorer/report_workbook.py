#!/usr/bin/env python3
"""
Build an Excel report from posts.jsonl + posts.sentiment.jsonl (+ themes if present).

Run from repo root:
  python3 subreddit_scorer/report_workbook.py --help
"""

from __future__ import annotations

import argparse
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


def load_by_id(path: Path) -> dict[str, dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for row in read_jsonl(path):
        pid = row.get("id")
        if pid is not None:
            by_id[str(pid)] = row
    return by_id


def merge_posts_corpus(
    posts: list[dict[str, Any]],
    sentiment_by_id: dict[str, dict[str, Any]],
    themes_by_id: dict[str, dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    themes_by_id = themes_by_id or {}
    merged: list[dict[str, Any]] = []
    for row in posts:
        pid = str(row.get("id", ""))
        s = sentiment_by_id.get(pid, {})
        t = themes_by_id.get(pid, {})
        title = (row.get("title") or "") or ""
        body = (row.get("selftext") or "") or ""
        text = f"{title}\n{body}".strip() if title and body else (title or body).strip()

        theme_scores = t.get("theme_scores")
        if isinstance(theme_scores, dict):
            theme_scores_json = json.dumps(theme_scores, ensure_ascii=False)
        else:
            theme_scores_json = ""

        sent_scores = s.get("sentiment_scores")
        if isinstance(sent_scores, dict):
            sentiment_scores_json = json.dumps(sent_scores, ensure_ascii=False)
        else:
            sentiment_scores_json = ""

        merged.append(
            {
                "id": row.get("id"),
                "created_utc": row.get("created_utc"),
                "title": title,
                "selftext": body,
                "text_for_review": text[:8000] + ("…" if len(text) > 8000 else ""),
                "theme_label": t.get("theme_label"),
                "theme_score": t.get("theme_score"),
                "theme_scores_json": theme_scores_json,
                "theme_classifier_note": t.get("theme_classifier_note", ""),
                "sentiment_label": s.get("sentiment_label"),
                "sentiment_score": s.get("sentiment_score"),
                "sentiment_polarity_index": s.get("sentiment_polarity_index"),
                "sentiment_scores_json": sentiment_scores_json,
                "sentiment_classifier_note": s.get("sentiment_classifier_note", ""),
            }
        )
    return merged


def theme_distribution(rows: list[dict[str, Any]]) -> pd.DataFrame:
    labels = []
    for r in rows:
        lab = r.get("theme_label")
        if lab is None or lab == "":
            labels.append("(no text / unclassified)")
        else:
            labels.append(str(lab))
    c = Counter(labels)
    total = sum(c.values()) or 1
    out = [
        {"theme": k, "count": v, "percent": round(100.0 * v / total, 2)}
        for k, v in sorted(c.items(), key=lambda x: (-x[1], x[0]))
    ]
    return pd.DataFrame(out)


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
        description="Join posts + sentiment (+ optional themes) → Excel under scorer/."
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
    if themes_path and themes_path.is_file():
        themes_by_id = load_by_id(themes_path)
        has_themes = True

    merged = merge_posts_corpus(posts, sentiment_by_id, themes_by_id)

    out_xlsx = args.output
    if out_xlsx is None:
        out_xlsx = out_xlsx_default or (
            posts_path.parent / f"{posts_path.stem}_Corpus_Report.xlsx"
        )
    out_xlsx = Path(out_xlsx)
    out_xlsx.parent.mkdir(parents=True, exist_ok=True)

    df_posts = format_created_utc(pd.DataFrame(merged))
    df_sent_dist = sentiment_distribution(merged)

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

    meta_themes: dict[str, Any] = {}
    if has_themes and themes_path:
        themes_meta_path = themes_path.parent / f"{themes_path.stem}.meta.json"
        if themes_meta_path.is_file():
            with open(themes_meta_path, encoding="utf-8") as f:
                meta_themes = json.load(f)

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
            ]
        )

    with pd.ExcelWriter(out_xlsx, engine="openpyxl") as writer:
        df_posts.to_excel(writer, sheet_name="Posts_corpus", index=False)
        df_sent_dist.to_excel(writer, sheet_name="Sentiment_distribution", index=False)
        if has_themes:
            theme_distribution(merged).to_excel(
                writer, sheet_name="Theme_distribution", index=False
            )
        pd.DataFrame([{"key": k, "value": v} for k, v in info_rows]).to_excel(
            writer, sheet_name="Run_info", index=False
        )

    print(f"Wrote {out_xlsx}")
    print(f"Wrote {info_path}")
    if not has_themes:
        print("Note: themes file absent — theme columns left empty.", flush=True)


if __name__ == "__main__":
    main()
