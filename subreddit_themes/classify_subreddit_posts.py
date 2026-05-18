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

import yaml

from jsonl_io import read_jsonl, write_json, write_jsonl
from paths import prefixe_themes_sortie

_DEFAULT_MODEL = "facebook/bart-large-mnli"
_DIR = Path(__file__).resolve().parent


def load_themes_config(path: Path) -> tuple[list[str], str]:
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    if not cfg or "labels" not in cfg:
        raise ValueError(f"Invalid themes file (missing 'labels'): {path}")
    labels = cfg["labels"]
    if not isinstance(labels, list) or not all(isinstance(x, str) for x in labels):
        raise ValueError("'labels' must be a list of strings")
    template = str(
        cfg.get("hypothesis_template") or "This post discusses {}."
    )
    return labels, template


def post_text(row: dict[str, Any]) -> str:
    title = (row.get("title") or "").strip()
    body = (row.get("selftext") or "").strip()
    if title and body:
        return f"{title}\n{body}"
    return title or body


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


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Classify Reddit posts into fixed English themes (BART-MNLI zero-shot)."
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
        help="YAML with 'labels' and optional 'hypothesis_template'",
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

    labels, hypothesis_template = load_themes_config(args.themes)
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
        text = post_text(row)
        base = {
            "id": row.get("id"),
            "created_utc": row.get("created_utc"),
            "title": row.get("title") or "",
            "selftext": row.get("selftext") or "",
        }

        if not text:
            n_empty += 1
            enriched = {
                **base,
                "theme_label": None,
                "theme_score": None,
                "theme_scores": {},
                "theme_classifier_note": "empty_text",
            }
            output_rows.append(enriched)
            continue

        result = classifier(
            text,
            candidate_labels=labels,
            hypothesis_template=hypothesis_template,
            multi_label=False,
            truncation=True,
        )
        labs = result["labels"]
        scores = result["scores"]
        theme_scores = dict(zip(labs, scores))
        enriched = {
            **base,
            "theme_label": labs[0],
            "theme_score": float(scores[0]),
            "theme_scores": theme_scores,
        }
        output_rows.append(enriched)

        if (i + 1) % 10 == 0 or i == len(rows) - 1:
            print(f"  classified {i + 1}/{len(rows)}", flush=True)

    write_jsonl(out_jsonl, output_rows)

    meta = {
        "version": 1,
        "model": args.model,
        "device_requested": args.device,
        "device_resolved": str(device),
        "themes_file": str(args.themes.resolve()),
        "hypothesis_template": hypothesis_template,
        "labels": labels,
        "n_labels": len(labels),
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
