"""
Analyse hors ligne : lit un .jsonl (+ .meta.json) et produit les Excel.
Pas d’appel à Reddit. Nécessite requests uniquement en indirect — ici : pandas, nltk, spacy, vader, openpyxl.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from ostomy_common import analyser_depuis_fichier_brut


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Lemmatisation, VADER, Top 100, export Excel (sans extraction Reddit)."
    )
    ap.add_argument(
        "-i",
        "--input",
        required=True,
        help="Fichier exporté par reddit_extract.py (ex. data_brutes/ostomy_2025.jsonl)",
    )
    ap.add_argument(
        "-o",
        "--output",
        type=str,
        default="",
        help="Fichier Excel principal (défaut: même dossier que l’entrée, "
        "nom = <entrée_sans_ext>_Resultats_Ostomy.xlsx)",
    )
    ap.add_argument(
        "--annee",
        type=int,
        default=0,
        help="Forcer l’année d’affichage dans l’Excel (0 = celle du .meta.json ou défaut config)",
    )
    args = ap.parse_args()
    inp = Path(args.input)
    if not args.output:
        out = str(inp.parent / f"{inp.stem}_Resultats_Ostomy.xlsx")
    else:
        out = args.output
    analyser_depuis_fichier_brut(str(inp), out, args.annee)


if __name__ == "__main__":
    main()
