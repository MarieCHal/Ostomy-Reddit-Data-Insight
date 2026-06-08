#!/usr/bin/env python3
"""
Exporte un posts.jsonl (sortie de extract_subreddit.py) vers un Excel simple.

Colonnes : id, created_utc, title, selftext

  python3 subreddit_extract/export_posts_xlsx.py -i results/.../extract/posts.jsonl
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def lire_jsonl(chemin: Path) -> list[dict]:
    lignes: list[dict] = []
    with open(chemin, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                lignes.append(json.loads(line))
    return lignes


def exporter_xlsx(entree: Path, sortie: Path | None) -> Path:
    rows = lire_jsonl(entree)
    df = pd.DataFrame(rows, columns=["id", "created_utc", "title", "selftext"])
    if "created_utc" in df.columns:
        df["created_utc"] = pd.to_datetime(df["created_utc"], unit="s", utc=True)
        df["created_utc"] = df["created_utc"].dt.tz_convert("UTC").dt.tz_localize(None)

    if sortie is None:
        sortie = entree.with_name(f"{entree.stem}.xlsx")
    sortie = Path(sortie)
    sortie.parent.mkdir(parents=True, exist_ok=True)

    with pd.ExcelWriter(sortie, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Posts", index=False)
        ws = writer.sheets["Posts"]
        from openpyxl.styles import Alignment

        for col in ("C", "D"):
            for cell in ws[col][1:]:
                cell.alignment = Alignment(wrap_text=True, vertical="top")
        ws.column_dimensions["A"].width = 12
        ws.column_dimensions["B"].width = 22
        ws.column_dimensions["C"].width = 45
        ws.column_dimensions["D"].width = 80

    return sortie


def main() -> int:
    p = argparse.ArgumentParser(description="JSONL posts → Excel simple")
    p.add_argument("-i", "--input", required=True, help="Chemin vers posts.jsonl")
    p.add_argument("-o", "--output", default=None, help="Chemin .xlsx (défaut : à côté du jsonl)")
    args = p.parse_args()
    entree = Path(args.input)
    if not entree.is_file():
        raise SystemExit(f"Fichier introuvable : {entree}")
    rows = lire_jsonl(entree)
    sortie = exporter_xlsx(entree, Path(args.output) if args.output else None)
    print(f"OK — Excel : {sortie} ({len(rows)} lignes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
