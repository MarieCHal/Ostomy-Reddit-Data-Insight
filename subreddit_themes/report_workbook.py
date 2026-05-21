#!/usr/bin/env python3
"""
Build a lightweight Excel report from posts.jsonl + posts.themes.jsonl.

Run from repo root:
  python3 subreddit_themes/report_workbook.py --help
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

from excel_helpers import (
    category_order,
    format_posts_worksheet,
    infer_category_order,
    merge_posts_and_themes,
    posts_column_order,
    theme_distribution,
)
from jsonl_io import read_jsonl, write_json
from paths import (
    chemin_extract_posts,
    chemin_rapport_meta,
    chemin_rapport_xlsx,
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


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Join posts.jsonl + themes jsonl → lightweight Excel (themes + distribution)."
    )
    ap.add_argument(
        "--run-dir",
        type=Path,
        default=None,
        help="Dossier d'un run (…/limit_N) : lit extract/posts.jsonl et themes/posts.themes.jsonl",
    )
    ap.add_argument(
        "-i",
        "--posts",
        type=Path,
        default=None,
        help="Path to posts.jsonl (défaut si --run-dir : …/extract/posts.jsonl)",
    )
    ap.add_argument(
        "-t",
        "--themes",
        type=Path,
        default=None,
        help="Path to posts.themes.jsonl (défaut si --run-dir : …/themes/posts.themes.jsonl)",
    )
    ap.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output .xlsx (défaut si --run-dir : …/themes/posts_Themes_Report.xlsx)",
    )
    args = ap.parse_args()

    if args.run_dir:
        run_dir = dossier_run(args.run_dir)
        posts_path = args.posts or chemin_extract_posts(run_dir)
        themes_path = args.themes or chemin_themes_jsonl(run_dir)
        out_xlsx_default = chemin_rapport_xlsx(run_dir)
    else:
        if not args.posts or not args.themes:
            print(
                "Indiquez --run-dir OU les deux chemins -i/--posts et -t/--themes.",
                file=sys.stderr,
            )
            sys.exit(2)
        posts_path = args.posts
        themes_path = args.themes
        out_xlsx_default = None

    posts_path = Path(posts_path)
    themes_path = Path(themes_path)
    if not posts_path.is_file():
        print(f"Posts file not found: {posts_path}", file=sys.stderr)
        sys.exit(1)
    if not themes_path.is_file():
        print(f"Themes file not found: {themes_path}", file=sys.stderr)
        sys.exit(1)

    posts = read_jsonl(posts_path)
    themes_by_id = load_by_id(themes_path)

    meta_themes: dict[str, Any] = {}
    themes_meta_path = themes_path.parent / f"{themes_path.stem}.meta.json"
    if themes_meta_path.is_file():
        with open(themes_meta_path, encoding="utf-8") as f:
            meta_themes = json.load(f)

    threshold = meta_themes.get("threshold")
    threshold_f = float(threshold) if threshold is not None else None

    categories = category_order(meta_themes)
    if not categories:
        categories = infer_category_order(themes_by_id)

    merged = merge_posts_and_themes(posts, themes_by_id, categories, threshold_f)

    out_xlsx = args.output
    if out_xlsx is None:
        if out_xlsx_default is not None:
            out_xlsx = out_xlsx_default
        else:
            out_xlsx = posts_path.parent / f"{posts_path.stem}_Themes_Report.xlsx"
    out_xlsx = Path(out_xlsx)
    out_xlsx.parent.mkdir(parents=True, exist_ok=True)

    df_posts = pd.DataFrame(merged)
    if not df_posts.empty:
        df_posts = df_posts[posts_column_order(df_posts, categories)]
    if "created_utc" in df_posts.columns and not df_posts.empty:
        s = pd.to_datetime(
            df_posts["created_utc"], unit="s", utc=True, errors="coerce"
        )
        try:
            if getattr(s.dt, "tz", None) is not None:
                df_posts["created_utc"] = s.dt.tz_convert("UTC").dt.tz_localize(None)
            else:
                df_posts["created_utc"] = s
        except (TypeError, AttributeError):
            df_posts["created_utc"] = s

    df_dist = theme_distribution(merged, categories)

    meta_posts: dict[str, Any] = {}
    meta_path = posts_path.parent / f"{posts_path.stem}.meta.json"
    if meta_path.is_file():
        with open(meta_path, encoding="utf-8") as f:
            meta_posts = json.load(f)

    run_info = {
        "posts_jsonl": str(posts_path.resolve()),
        "themes_jsonl": str(themes_path.resolve()),
        "posts_meta": meta_posts,
        "themes_meta": meta_themes,
    }
    if args.run_dir:
        info_path = chemin_rapport_meta(dossier_run(args.run_dir))
    else:
        info_path = out_xlsx.with_suffix(".report_meta.json")
    write_json(info_path, run_info)

    with pd.ExcelWriter(out_xlsx, engine="openpyxl") as writer:
        df_posts.to_excel(writer, sheet_name="Posts_themes", index=False)
        df_dist.to_excel(writer, sheet_name="Theme_distribution", index=False)
        df_info = pd.DataFrame(
            [
                {"key": k, "value": v}
                for k, v in [
                    ("posts_jsonl", str(posts_path.resolve())),
                    ("themes_jsonl", str(themes_path.resolve())),
                    ("n_posts", len(merged)),
                    ("classification_mode", meta_themes.get("classification_mode", "")),
                    ("threshold", meta_themes.get("threshold", "")),
                    ("max_text_chars", meta_themes.get("max_text_chars", "")),
                    ("n_categories", meta_themes.get("n_labels", "")),
                    ("themes_meta_model", meta_themes.get("model", "")),
                    ("themes_meta_instant", meta_themes.get("instant_utc", "")),
                ]
            ]
        )
        df_info.to_excel(writer, sheet_name="Run_info", index=False)
        format_posts_worksheet(
            writer.sheets["Posts_themes"],
            list(df_posts.columns),
        )

    print(f"Wrote {out_xlsx}")
    print(f"Wrote {info_path}")


if __name__ == "__main__":
    main()
