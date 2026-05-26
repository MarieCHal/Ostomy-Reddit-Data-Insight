#!/usr/bin/env python3
"""
Zero-shot theme assignment with BART-MNLI (facebook/bart-large-mnli).

Reads posts.jsonl (same schema as subreddit_extract), writes posts.themes.jsonl
and posts.themes.meta.json alongside it.

Run from repo root:
  python3 subreddit_themes/classify_subreddit_posts.py --help
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonl_io import read_jsonl, write_json, write_jsonl
from paths import prefixe_themes_sortie
from themes_config import (
    ThemeCategory,
    ThemesConfig,
    apply_exclusion_penalty,
    apply_keyword_boost,
    build_nli_hypothesis,
    load_themes_config,
)

_DEFAULT_MODEL = "facebook/bart-large-mnli"
_DIR = Path(__file__).resolve().parent


def post_text(row: dict[str, Any], max_chars: int) -> str:
    title = (row.get("title") or "").strip()
    body = (row.get("selftext") or "").strip()
    if title and body:
        text = f"{title}\n{body}"
    else:
        text = title or body
    return text[:max_chars]


def resolve_device(name: str) -> int | str:
    if name in ("cpu", "-1"):
        return -1
    if name == "cuda" or name.startswith("cuda:"):
        return name if ":" in name else 0
    if name == "mps":
        return "mps"
    if name == "auto":
        import torch

        if torch.cuda.is_available():
            return 0
        if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            return "mps"
        return -1
    raise ValueError(f"Unknown device: {name}")


def classify_text(
    classifier: Any,
    text: str,
    categories: list[ThemeCategory],
    config: ThemesConfig,
    threshold: float,
) -> dict[str, Any]:
    hypotheses = [build_nli_hypothesis(c, config) for c in categories]
    hypothesis_to_short = dict(zip(hypotheses, [c.short_name for c in categories], strict=True))

    result = classifier(
        text,
        candidate_labels=hypotheses,
        hypothesis_template=config.hypothesis_template,
        multi_label=True,
        truncation=True,
    )

    theme_scores: dict[str, float] = {}
    for label, score in zip(result["labels"], result["scores"], strict=True):
        short_name = hypothesis_to_short[label]
        theme_scores[short_name] = float(score)

    theme_scores = apply_keyword_boost(text, theme_scores, categories, config)
    theme_scores = apply_exclusion_penalty(text, theme_scores, categories, config)

    theme_labels = [
        name for name, score in theme_scores.items() if score >= threshold
    ]
    theme_labels.sort(key=lambda n: theme_scores[n], reverse=True)

    if theme_labels:
        top = theme_labels[0]
        top_score = theme_scores[top]
    else:
        top = max(theme_scores, key=theme_scores.get)
        top_score = theme_scores[top]

    return {
        "theme_scores": theme_scores,
        "theme_labels": theme_labels,
        "theme_label": top,
        "theme_score": top_score,
    }


def empty_result() -> dict[str, Any]:
    return {
        "theme_label": None,
        "theme_score": None,
        "theme_labels": [],
        "theme_scores": {},
        "theme_classifier_note": "empty_text",
    }


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Classify Reddit posts into fixed English themes (BART-MNLI zero-shot, multi-label)."
    )
    ap.add_argument(
        "-i",
        "--input",
        required=True,
        type=Path,
        help="Path to posts.jsonl",
    )
    ap.add_argument(
        "--themes",
        type=Path,
        default=_DIR / "themes_ostomy.yaml",
        help="YAML taxonomy (categories with hypothesis per label)",
    )
    ap.add_argument(
        "--model",
        default=_DEFAULT_MODEL,
        help="Hugging Face model id (default: BART-MNLI)",
    )
    ap.add_argument(
        "--device",
        default="auto",
        help="auto | cpu | cuda | mps",
    )
    ap.add_argument(
        "--threshold",
        type=float,
        default=None,
        help="Score threshold per label (default: value from YAML, usually 0.40)",
    )
    ap.add_argument(
        "--max-chars",
        type=int,
        default=None,
        help="Max characters of title+body sent to the model (default: YAML, usually 1000)",
    )
    ap.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Process at most N posts (0 = all)",
    )
    ap.add_argument(
        "-o",
        "--output-prefix",
        type=Path,
        default=None,
        help="Prefix without extension for .themes.jsonl / .themes.meta.json "
        "(default: …/themes/posts if input is …/extract/posts.jsonl)",
    )
    args = ap.parse_args()

    inp: Path = args.input
    if not inp.is_file():
        print(f"Input not found: {inp}", file=sys.stderr)
        sys.exit(1)

    config = load_themes_config(args.themes)
    threshold = config.threshold if args.threshold is None else args.threshold
    max_chars = config.max_text_chars if args.max_chars is None else args.max_chars
    device = resolve_device(args.device.lower())

    from transformers import pipeline

    print(f"Loading model {args.model!r} (device={device!r})…", flush=True)
    classifier = pipeline(
        "zero-shot-classification",
        model=args.model,
        device=device,
    )

    rows = read_jsonl(inp)
    if args.limit and args.limit > 0:
        rows = rows[: args.limit]

    out_base = args.output_prefix
    if out_base is None:
        out_base = prefixe_themes_sortie(inp)
    else:
        out_base = Path(out_base)
        if out_base.suffix == ".jsonl":
            out_base = out_base.with_suffix("")

    out_jsonl = out_base.parent / f"{out_base.name}.themes.jsonl"
    out_meta = out_base.parent / f"{out_base.name}.themes.meta.json"

    output_rows: list[dict[str, Any]] = []
    n_empty = 0

    for i, row in enumerate(rows):
        text = post_text(row, max_chars)
        base = {
            "id": row.get("id"),
            "created_utc": row.get("created_utc"),
            "title": row.get("title") or "",
            "selftext": row.get("selftext") or "",
        }

        if not text.strip():
            n_empty += 1
            output_rows.append({**base, **empty_result()})
            continue

        classified = classify_text(
            classifier, text, config.categories, config, threshold
        )
        output_rows.append({**base, **classified})

        if (i + 1) % 10 == 0 or i == len(rows) - 1:
            print(f"  classified {i + 1}/{len(rows)}", flush=True)

    write_jsonl(out_jsonl, output_rows)

    meta = {
        "version": config.version,
        "classification_mode": config.classification_mode,
        "threshold": threshold,
        "max_text_chars": max_chars,
        "model": args.model,
        "device_requested": args.device,
        "device_resolved": str(device),
        "themes_file": str(args.themes.resolve()),
        "enrich_hypothesis_with_keywords": config.enrich_hypothesis_with_keywords,
        "enrich_hypothesis_with_definition": config.enrich_hypothesis_with_definition,
        "enrich_hypothesis_with_examples": config.enrich_hypothesis_with_examples,
        "max_examples_in_hypothesis": config.max_examples_in_hypothesis,
        "max_hypothesis_chars": config.max_hypothesis_chars,
        "keyword_boost_per_match": config.keyword_boost_per_match,
        "keyword_boost_cap": config.keyword_boost_cap,
        "exclusion_penalty": config.exclusion_penalty,
        "hypothesis_template": config.hypothesis_template,
        "categories": [
            {
                "id": c.id,
                "short_name": c.short_name,
                "display_name": c.display_name,
            }
            for c in config.categories
        ],
        "n_labels": len(config.categories),
        "input_jsonl": str(inp.resolve()),
        "output_jsonl": str(out_jsonl.resolve()),
        "n_posts": len(rows),
        "n_empty_text": n_empty,
        "instant_utc": datetime.now(timezone.utc).isoformat(),
    }
    write_json(out_meta, meta)

    print(f"Wrote {out_jsonl}")
    print(f"Wrote {out_meta}")


if __name__ == "__main__":
    main()
