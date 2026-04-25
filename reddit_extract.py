"""
Extraction seule (Reddit, endpoints .json) → fichiers .jsonl + .meta.json.
Ne charge pas spaCy ni VADER. Réseau requis.
"""

from __future__ import annotations

import argparse

from ostomy_common import ANNEE_CIBLE, extraire_vers_fichiers_bruts


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Télécharge les posts r/ostomy pour une année (UTC) et enregistre le brut."
    )
    ap.add_argument(
        "--annee",
        type=int,
        default=ANNEE_CIBLE,
        help="Année calendaire cible (UTC), ex. 2025 ou 2026",
    )
    ap.add_argument(
        "-o",
        "--out",
        type=str,
        default="data_brutes/ostomy",
        help="Préfixe de fichiers de sortie : <out>.jsonl et <out>.meta.json (dossier créé si besoin)",
    )
    args = ap.parse_args()
    cj, cm, nreq, npost, note = extraire_vers_fichiers_bruts(args.out, args.annee)
    print(f"OK — JSONL : {cj}")
    print(f"     Meta : {cm}")
    print(f"     posts = {npost} | requêtes HTTP = {nreq}")
    print(f"     {note}")


if __name__ == "__main__":
    main()
