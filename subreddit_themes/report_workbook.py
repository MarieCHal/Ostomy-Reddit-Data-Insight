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
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd

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


def merge_posts_and_themes(
    posts: list[dict[str, Any]],
    themes_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    for row in posts:
        pid = str(row.get("id", ""))
        t = themes_by_id.get(pid, {})
        title = (row.get("title") or "") or ""
        body = (row.get("selftext") or "") or ""
        text = f"{title}\n{body}".strip() if title and body else (title or body).strip()
        scores = t.get("theme_scores")
        if isinstance(scores, dict):
            scores_json = json.dumps(scores, ensure_ascii=False)
        else:
            scores_json = ""
        merged.append(
            {
                "id": row.get("id"),
                "created_utc": row.get("created_utc"),
                "title": title,
                "selftext": body,
                "text_for_review": text[:8000] + ("…" if len(text) > 8000 else ""),
                "theme_label": t.get("theme_label"),
                "theme_score": t.get("theme_score"),
                "theme_scores_json": scores_json,
                "theme_classifier_note": t.get("theme_classifier_note", ""),
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
    merged = merge_posts_and_themes(posts, themes_by_id)

    out_xlsx = args.output
    if out_xlsx is None:
        if out_xlsx_default is not None:
            out_xlsx = out_xlsx_default
        else:
            out_xlsx = posts_path.parent / f"{posts_path.stem}_Themes_Report.xlsx"
    out_xlsx = Path(out_xlsx)
    out_xlsx.parent.mkdir(parents=True, exist_ok=True)

    df_posts = pd.DataFrame(merged)
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

    df_dist = theme_distribution(merged)

    meta_posts: dict[str, Any] = {}
    meta_path = posts_path.parent / f"{posts_path.stem}.meta.json"
    if meta_path.is_file():
        with open(meta_path, encoding="utf-8") as f:
            meta_posts = json.load(f)

    meta_themes: dict[str, Any] = {}
    themes_meta_path = themes_path.parent / f"{themes_path.stem}.meta.json"
    if themes_meta_path.is_file():
        with open(themes_meta_path, encoding="utf-8") as f:
            meta_themes = json.load(f)

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
                    ("themes_meta_model", meta_themes.get("model", "")),
                    ("themes_meta_instant", meta_themes.get("instant_utc", "")),
                ]
            ]
        )
        df_info.to_excel(writer, sheet_name="Run_info", index=False)

    print(f"Wrote {out_xlsx}")
    print(f"Wrote {info_path}")


if __name__ == "__main__":
    main()
