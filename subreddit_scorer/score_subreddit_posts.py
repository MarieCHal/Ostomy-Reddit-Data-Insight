#!/usr/bin/env python3
"""
Sentiment scoring with RoBERTa (cardiffnlp/twitter-roberta-base-sentiment-latest by default).

Reads posts.jsonl (same schema as subreddit_extract), writes posts.sentiment.jsonl
and posts.sentiment.meta.json.

Run from repo root:
  python3 subreddit_scorer/score_subreddit_posts.py --help
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonl_io import read_jsonl, write_json, write_jsonl
from paths import prefixe_scorer_sortie

_DEFAULT_MODEL = "cardiffnlp/twitter-roberta-base-sentiment-latest"
_POLARITY_FORMULA = "P(positive) - P(negative)"
_CANONICAL_LABELS = ("negative", "neutral", "positive")
_LABEL_ALIASES: dict[str, str] = {
    "LABEL_0": "negative",
    "LABEL_1": "neutral",
    "LABEL_2": "positive",
    "NEGATIVE": "negative",
    "NEUTRAL": "neutral",
    "POSITIVE": "positive",
}


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


def normalize_label(raw: str) -> str:
    key = raw.strip()
    if key.lower() in _CANONICAL_LABELS:
        return key.lower()
    upper = key.upper()
    if upper in _LABEL_ALIASES:
        return _LABEL_ALIASES[upper]
    return key.lower()


def pipeline_scores_to_dict(items: list[dict[str, Any]]) -> dict[str, float]:
    out: dict[str, float] = {}
    for item in items:
        lab = normalize_label(str(item["label"]))
        out[lab] = float(item["score"])
    return out


def polarity_index(scores: dict[str, float]) -> float:
    return float(scores.get("positive", 0.0) - scores.get("negative", 0.0))


def top_label_and_score(scores: dict[str, float]) -> tuple[str, float]:
    if not scores:
        return "", 0.0
    lab = max(scores, key=scores.get)
    return lab, float(scores[lab])


def enrich_row(
    row: dict[str, Any],
    scores: dict[str, float] | None,
    note: str = "",
) -> dict[str, Any]:
    base = {
        "id": row.get("id"),
        "created_utc": row.get("created_utc"),
        "title": row.get("title") or "",
        "selftext": row.get("selftext") or "",
    }
    if scores is None:
        return {
            **base,
            "sentiment_label": None,
            "sentiment_score": None,
            "sentiment_scores": {},
            "sentiment_polarity_index": None,
            "sentiment_classifier_note": note or "empty_text",
        }
    label, score = top_label_and_score(scores)
    return {
        **base,
        "sentiment_label": label,
        "sentiment_score": score,
        "sentiment_scores": scores,
        "sentiment_polarity_index": polarity_index(scores),
        "sentiment_classifier_note": note,
    }


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Score Reddit post sentiment (RoBERTa, 3-class + polarity index)."
    )
    ap.add_argument(
        "-i",
        "--input",
        required=True,
        type=Path,
        help="Path to posts.jsonl",
    )
    ap.add_argument(
        "--model",
        default=_DEFAULT_MODEL,
        help="Hugging Face model id (default: twitter-roberta sentiment)",
    )
    ap.add_argument(
        "--device",
        default="auto",
        help="auto | cpu | cuda | mps",
    )
    ap.add_argument(
        "--batch-size",
        type=int,
        default=8,
        help="Batch size for inference (default: 8)",
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
        help="Prefix without extension for .sentiment.jsonl / .sentiment.meta.json "
        "(default: …/scorer/posts if input is …/extract/posts.jsonl)",
    )
    args = ap.parse_args()

    inp: Path = args.input
    if not inp.is_file():
        print(f"Input not found: {inp}", file=sys.stderr)
        sys.exit(1)

    batch_size = max(1, args.batch_size)
    device = resolve_device(args.device.lower())

    from transformers import pipeline

    print(f"Loading model {args.model!r} (device={device!r})…", flush=True)
    classifier = pipeline(
        "sentiment-analysis",
        model=args.model,
        device=device,
        top_k=None,
    )

    rows = read_jsonl(inp)
    if args.limit and args.limit > 0:
        rows = rows[: args.limit]

    out_base = args.output_prefix
    if out_base is None:
        out_base = prefixe_scorer_sortie(inp)
    else:
        out_base = Path(out_base)
        if out_base.suffix == ".jsonl":
            out_base = out_base.with_suffix("")

    out_jsonl = out_base.parent / f"{out_base.name}.sentiment.jsonl"
    out_meta = out_base.parent / f"{out_base.name}.sentiment.meta.json"

    output_rows: list[dict[str, Any]] = []
    n_empty = 0
    n_scored = 0

    batch_indices: list[int] = []
    batch_texts: list[str] = []

    def flush_batch() -> None:
        nonlocal n_scored
        if not batch_texts:
            return
        results = classifier(batch_texts, truncation=True)
        if isinstance(results, dict):
            results = [results]
        elif (
            len(batch_texts) == 1
            and results
            and isinstance(results[0], dict)
            and "label" in results[0]
        ):
            results = [results]
        for idx, raw in zip(batch_indices, results):
            scores = pipeline_scores_to_dict(raw)
            output_rows[idx] = enrich_row(rows[idx], scores)
            n_scored += 1
        batch_indices.clear()
        batch_texts.clear()

    for i, row in enumerate(rows):
        text = post_text(row)
        if not text:
            n_empty += 1
            output_rows.append(enrich_row(row, None))
            continue

        batch_indices.append(i)
        batch_texts.append(text)
        output_rows.append({})  # placeholder

        if len(batch_texts) >= batch_size:
            flush_batch()
            print(f"  scored {min(i + 1, len(rows))}/{len(rows)}", flush=True)

    flush_batch()
    if rows:
        print(f"  scored {len(rows)}/{len(rows)}", flush=True)

    write_jsonl(out_jsonl, output_rows)

    meta = {
        "version": 1,
        "model": args.model,
        "device_requested": args.device,
        "device_resolved": str(device),
        "polarity_index_formula": _POLARITY_FORMULA,
        "label_map": dict(_LABEL_ALIASES),
        "canonical_labels": list(_CANONICAL_LABELS),
        "batch_size": batch_size,
        "input_jsonl": str(inp.resolve()),
        "output_jsonl": str(out_jsonl.resolve()),
        "n_posts": len(rows),
        "n_scored": n_scored,
        "n_empty_text": n_empty,
        "instant_utc": datetime.now(timezone.utc).isoformat(),
    }
    write_json(out_meta, meta)

    print(f"Wrote {out_jsonl}")
    print(f"Wrote {out_meta}")


if __name__ == "__main__":
    main()
