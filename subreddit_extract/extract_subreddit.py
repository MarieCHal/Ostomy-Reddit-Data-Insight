#!/usr/bin/env python3
"""
Script autonome : télécharge les posts d'un subreddit (API JSON publique Reddit)
et écrit posts.jsonl + posts.meta.json.

Ce n'est pas un « package » installable : un seul fichier à lancer, par ex. depuis
la racine du dépôt :

  python3 subreddit_extract/extract_subreddit.py --help
  python3 subreddit_extract/extract_subreddit.py -s ostomy --start 2026-01-01 --end 2026-05-14 --limit 500
"""

from __future__ import annotations

import argparse
import json
import logging
import string
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

# ---------------------------------------------------------------------------
# Paramètres HTTP (alignés sur l'ancien flux ostomy_common)
# ---------------------------------------------------------------------------
SLEEP_ENTRE_REQUETES_S: float = 2.0
TIMEOUT_S: int = 45
MAX_TENTATIVES_HTTP: int = 6
ATTENTE_S_SUR_429: float = 90.0

USER_AGENT: str = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

LISTE_QUERIES_RECHERCHE_OSTOMY: list[str] = list(string.ascii_lowercase) + [
    "ostomy",
    "stoma",
    "ileostomy",
    "colostomy",
]
LISTE_QUERIES_RECHERCHE_GENERIQUE: list[str] = list(string.ascii_lowercase)

log = logging.getLogger(__name__)


# --- HTTP -----------------------------------------------------------------
def requete_reddit(url: str, params: dict[str, str | int | None]) -> Any:
    import requests

    headers = {"User-Agent": USER_AGENT}
    for tentative in range(MAX_TENTATIVES_HTTP):
        log.debug("GET %s params=%s", url, params)
        r = requests.get(url, params=params, headers=headers, timeout=TIMEOUT_S)
        if r.status_code == 429:
            attente = ATTENTE_S_SUR_429 + 30.0 * tentative
            log.warning(
                "HTTP 429 — pause %.0fs avant nouvelle tentative (%s/%s)…",
                attente,
                tentative + 1,
                MAX_TENTATIVES_HTTP,
            )
            time.sleep(attente)
            continue
        r.raise_for_status()
        return r
    r.raise_for_status()
    raise RuntimeError("requête Reddit: échec inattendu")


def payload_children(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data") or {}
    return data.get("children") or []


# --- Chemins & fichiers -----------------------------------------------------
def dossier_resultat_defaut(
    subreddit: str,
    date_debut: str,
    date_fin: str,
    limit: int,
    racine_results: str = "results",
) -> Path:
    base = Path(racine_results) / subreddit.lower() / f"{date_debut}_{date_fin}"
    if limit and limit > 0:
        base = base / f"limit_{limit}"
    return base


def prefixe_posts(dossier: Path) -> Path:
    """Préfixe sans extension : …/<run>/extract/posts → posts.jsonl + posts.meta.json."""
    extract_dir = dossier / "extract"
    extract_dir.mkdir(parents=True, exist_ok=True)
    return extract_dir / "posts"


def chemins_bruts(chemin_base: str | Path) -> tuple[Path, Path]:
    p = Path(chemin_base)
    jsonl = p if p.suffix == ".jsonl" else p.with_suffix(".jsonl")
    meta = jsonl.parent / f"{jsonl.stem}.meta.json"
    return jsonl, meta


def sauvegarder_posts_bruts(
    chemin_base: str | Path,
    entrees: list[dict[str, Any]],
    meta: dict[str, Any],
) -> tuple[str, str]:
    jsonl, metaf = chemins_bruts(chemin_base)
    jsonl.parent.mkdir(parents=True, exist_ok=True)
    with open(jsonl, "w", encoding="utf-8") as f:
        for e in entrees:
            o = {
                "id": e.get("id"),
                "created_utc": e.get("created_utc"),
                "title": (e.get("title") or "") or "",
                "selftext": (e.get("selftext") or "") or "",
            }
            f.write(json.dumps(o, ensure_ascii=False) + "\n")
    with open(metaf, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=True, indent=2)
    return str(jsonl), str(metaf)


# --- Extraction -------------------------------------------------------------
def bornes_dates_utc_iso(date_debut: str, date_fin: str) -> tuple[float, float, str]:
    d0 = datetime.strptime(date_debut, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    d1 = datetime.strptime(date_fin, "%Y-%m-%d").replace(
        hour=23, minute=59, second=59, tzinfo=timezone.utc
    )
    if d1 < d0:
        raise ValueError("date_fin doit être >= date_debut")
    label = f"{date_debut}_{date_fin}"
    return d0.timestamp(), d1.timestamp(), label


def entree_de_t3(d: dict[str, Any]) -> dict[str, Any] | None:
    pid = d.get("id")
    if not pid:
        return None
    cu = d.get("created_utc")
    if cu is None:
        return None
    title = (d.get("title") or "") or ""
    selftext = (d.get("selftext") or "") or ""
    return {
        "id": pid,
        "created_utc": float(cu),
        "title": title,
        "selftext": selftext,
    }


@dataclass
class EtatPlafond:
    by_id: dict[str, dict[str, Any]]
    limite: int

    def ajouter_si_periode(
        self,
        d: dict[str, Any],
        ts_deb: float,
        ts_fin: float,
    ) -> bool:
        cu = d.get("created_utc")
        if cu is None:
            return True
        ft = float(cu)
        if not (ts_deb <= ft <= ts_fin):
            return True
        if self.limite and len(self.by_id) >= self.limite:
            return False
        ent = entree_de_t3(d)
        if ent is None:
            return True
        self.by_id[ent["id"]] = ent
        return True


def extraire_posts_periode(
    subreddit: str,
    ts_deb: float,
    ts_fin: float,
    limite_posts: int,
    liste_queries_recherche: list[str],
    elargissement_search: bool,
    sleep_s: float,
) -> tuple[list[dict[str, Any]], int, int, str]:
    etat = EtatPlafond(by_id={}, limite=limite_posts)
    n_requetes = 0
    notes: list[str] = []
    sub = subreddit.strip().removeprefix("r/").strip()
    plafond_stop = False

    tete_new = f"https://www.reddit.com/r/{sub}/new.json"
    params_new: dict[str, str | int] = {"limit": 100, "raw_json": 1}

    log.info("Phase /new — r/%s (fenêtre UTC [%.0f, %.0f])", sub, ts_deb, ts_fin)
    after: str | None = None
    premiere_new = True
    note_new = "indefini"
    page_new = 0

    while not plafond_stop:
        if not premiere_new:
            log.info("Pause %.1fs avant requête /new (pagination)…", sleep_s)
            time.sleep(sleep_s)
            log.debug("Fin pause /new.")
        premiere_new = False
        page_new += 1
        p = {**params_new, **({"after": after} if after else {})}
        n_requetes += 1
        r = requete_reddit(tete_new, p)
        payload = r.json()
        children = payload_children(payload)

        for child in children:
            if child.get("kind") != "t3":
                continue
            d = child.get("data") or {}
            if not etat.ajouter_si_periode(d, ts_deb, ts_fin):
                plafond_stop = True
                note_new = f"arret_plafond_{limite_posts}"
                break
        if plafond_stop:
            break

        if limite_posts and len(etat.by_id) >= limite_posts:
            note_new = f"arret_plafond_{limite_posts}"
            break

        if not children:
            note_new = "arret_liste_vide"
            break

        data = payload.get("data") or {}
        log.info(
            "[/new] page=%s requêtes_http=%s posts_dans_fenêtre=%s after=%s",
            page_new,
            n_requetes,
            len(etat.by_id),
            "oui" if data.get("after") else "non",
        )

        last = children[-1]
        if last.get("kind") == "t3" and (last.get("data") or {}).get("created_utc") is not None:
            plus_ancien = float((last.get("data") or {})["created_utc"])
            if plus_ancien < ts_deb:
                note_new = "arret_pages_apres_ancien_avant_debut_fenetre"
                break

        after = data.get("after")
        if not after:
            note_new = "arret_pas_d_after"
            break

    notes.append(f"new:{note_new},n_dans_fenetre={len(etat.by_id)}")
    log.info("Fin phase /new — %s", notes[-1])

    if elargissement_search and not plafond_stop:
        tete_search = f"https://www.reddit.com/r/{sub}/search.json"
        n_avant = len(etat.by_id)
        n_q = len(liste_queries_recherche)
        log.info(
            "Phase /search — %s requêtes, pause %.1fs entre appels HTTP…",
            n_q,
            sleep_s,
        )
        for i, requ in enumerate(liste_queries_recherche, start=1):
            if plafond_stop:
                break
            log.info("[/search] requête %s/%s q=%r (posts_dans_fenêtre=%s)", i, n_q, requ, len(etat.by_id))
            after_s: str | None = None
            premiere_s = True
            page_s = 0
            while not plafond_stop:
                if not premiere_s:
                    log.info("Pause %.1fs avant pagination /search…", sleep_s)
                    time.sleep(sleep_s)
                    log.debug("Fin pause /search.")
                premiere_s = False
                page_s += 1
                n_requetes += 1
                p_s: dict[str, str | int | None] = {
                    "q": requ,
                    "restrict_sr": 1,
                    "sort": "new",
                    "limit": 100,
                    "raw_json": 1,
                    **({"after": after_s} if after_s else {}),
                }
                r2 = requete_reddit(tete_search, p_s)
                pl = r2.json()
                ch2 = payload_children(pl)
                for child in ch2:
                    if child.get("kind") != "t3":
                        continue
                    d = child.get("data") or {}
                    if not etat.ajouter_si_periode(d, ts_deb, ts_fin):
                        plafond_stop = True
                        break
                if plafond_stop:
                    break
                log.debug(
                    "[/search] q=%r page=%s +posts_session=%s",
                    requ,
                    page_s,
                    len(ch2),
                )
                d2 = pl.get("data") or {}
                after_s = d2.get("after")
                if not after_s:
                    break
        n_apres = len(etat.by_id)
        notes.append(
            f"search:requetes={len(liste_queries_recherche)},+posts={n_apres - n_avant}"
        )
        log.info("Fin phase /search — posts_dans_fenêtre=%s (%s)", n_apres, notes[-1])

    if plafond_stop and limite_posts and not any(
        f"plafond_{limite_posts}" in n for n in notes[-3:]
    ):
        notes.append(f"arret_plafond_{limite_posts}")

    entrees = sorted(etat.by_id.values(), key=lambda x: x["created_utc"], reverse=True)
    run_full = " | ".join(notes)
    log.info(
        "Extraction terminée — posts=%s requêtes_http=%s résumé: %s",
        len(entrees),
        n_requetes,
        run_full,
    )
    return entrees, n_requetes, len(entrees), run_full


def extraire_vers_fichiers_bruts(
    chemin_base: str,
    subreddit: str,
    date_debut: str,
    date_fin: str,
    limite_posts: int,
    liste_queries_recherche: list[str],
    elargissement_search: bool,
    sleep_s: float,
) -> tuple[str, str, int, int, str]:
    ts_deb, ts_fin, label_plage = bornes_dates_utc_iso(date_debut, date_fin)
    entrees, n_req, n_posts, run_note = extraire_posts_periode(
        subreddit=subreddit,
        ts_deb=ts_deb,
        ts_fin=ts_fin,
        limite_posts=limite_posts,
        liste_queries_recherche=liste_queries_recherche,
        elargissement_search=elargissement_search,
        sleep_s=sleep_s,
    )
    maintenant = datetime.now(timezone.utc).isoformat()
    meta = {
        "version": 1,
        "subreddit": subreddit.strip().removeprefix("r/").strip(),
        "periode_utc": {
            "debut_ts": ts_deb,
            "fin_ts": ts_fin,
            "label": label_plage,
            "date_debut": date_debut,
            "date_fin": date_fin,
        },
        "limite_posts": limite_posts or None,
        "n_requetes": n_req,
        "n_posts": n_posts,
        "code_arret": run_note,
        "elargissement_search": elargissement_search,
        "queries_search_utilisees": liste_queries_recherche if elargissement_search else [],
        "instant_extraction_utc": maintenant,
    }
    cj, cm = sauvegarder_posts_bruts(chemin_base, entrees, meta)
    return cj, cm, n_req, n_posts, run_note


# --- CLI -------------------------------------------------------------------
EPILOG = """
Exemples :
  python3 subreddit_extract/extract_subreddit.py -s ostomy --start 2025-01-01 --end 2025-01-31
  python3 subreddit_extract/extract_subreddit.py -s ostomy --start 2025-01-01 --end 2025-12-31 --limit 500
  python3 subreddit_extract/extract_subreddit.py -s ostomy --start 2025-06-01 --end 2025-06-30 \\
      --out-prefix ./exports/test --no-search

Les dates sont en UTC (début 00:00:00, fin 23:59:59 du jour indiqué).
"""


def configurer_logging(verbose: bool) -> None:
    niveau = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=niveau,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
        force=True,
    )


def resoudre_liste_queries(subreddit: str, mode: str) -> list[str]:
    sub = subreddit.strip().removeprefix("r/").strip().lower()
    if mode == "ostomy":
        return list(LISTE_QUERIES_RECHERCHE_OSTOMY)
    if mode == "generic":
        return list(LISTE_QUERIES_RECHERCHE_GENERIQUE)
    if sub == "ostomy":
        return list(LISTE_QUERIES_RECHERCHE_OSTOMY)
    return list(LISTE_QUERIES_RECHERCHE_GENERIQUE)


def construire_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="reddit-subreddit-extract",
        description=(
            "Télécharge les soumissions (posts) d'un subreddit via l'API JSON publique "
            "de Reddit, pour une plage de dates UTC, et enregistre un fichier .jsonl "
            "ainsi qu'un .meta.json (réanalysable sans refetch)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=EPILOG,
    )
    p.add_argument("-s", "--subreddit", required=True, help="Subreddit sans r/ (ex. ostomy).")
    p.add_argument("--start", required=True, metavar="YYYY-MM-DD", help="Début inclusif UTC.")
    p.add_argument("--end", required=True, metavar="YYYY-MM-DD", help="Fin inclusive UTC (23:59:59).")
    p.add_argument("--limit", type=int, default=0, metavar="N", help="Max posts (0 = illimité).")
    p.add_argument(
        "--out-prefix",
        default=None,
        metavar="CHEMIN",
        help="Préfixe sans extension → CHEMIN.jsonl et CHEMIN.meta.json.",
    )
    p.add_argument(
        "--results-root",
        default="results",
        metavar="DOSSIER",
        help="Racine si sortie par défaut (défaut: results).",
    )
    p.add_argument("--no-search", action="store_true", help="Désactiver la phase /search.")
    p.add_argument(
        "--search-queries",
        choices=("auto", "ostomy", "generic"),
        default="auto",
        help="Requêtes /search : auto, ostomy (domaine), ou generic (a–z).",
    )
    p.add_argument(
        "--sleep",
        type=float,
        default=SLEEP_ENTRE_REQUETES_S,
        metavar="SEC",
        help=f"Pause entre requêtes (défaut: {SLEEP_ENTRE_REQUETES_S}).",
    )
    p.add_argument("-v", "--verbose", action="store_true", help="Logs DEBUG.")
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = construire_parser().parse_args(list(argv) if argv is not None else None)
    configurer_logging(args.verbose)

    try:
        import requests  # noqa: F401
    except ImportError:
        print(
            "Erreur : le module « requests » n’est pas installé pour ce Python.\n\n"
            "Sur macOS (Python Homebrew), installez dans un environnement virtuel :\n"
            "  python3 -m venv .venv && source .venv/bin/activate\n"
            "  pip install -r requirements-extract.txt\n\n"
            "Puis relancez cette commande (avec le venv activé).\n",
            file=sys.stderr,
        )
        return 1

    limite = max(0, args.limit)
    queries = resoudre_liste_queries(args.subreddit, args.search_queries)
    elargissement = not args.no_search

    if args.out_prefix:
        chemin_base = args.out_prefix
        log_dossier = str(chemin_base)
    else:
        dossier = dossier_resultat_defaut(
            args.subreddit,
            args.start,
            args.end,
            limite,
            racine_results=args.results_root,
        )
        chemin_base = str(prefixe_posts(dossier))
        log_dossier = str(dossier)

    logging.info("Sortie prévue sous : %s (.jsonl + .meta.json)", log_dossier)

    cj, cm, n_req, n_posts, note = extraire_vers_fichiers_bruts(
        chemin_base=chemin_base,
        subreddit=args.subreddit,
        date_debut=args.start,
        date_fin=args.end,
        limite_posts=limite,
        liste_queries_recherche=queries,
        elargissement_search=elargissement,
        sleep_s=args.sleep,
    )
    print(f"OK — JSONL : {cj}")
    print(f"     Meta : {cm}")
    print(f"     posts = {n_posts} | requêtes HTTP = {n_req}")
    print(f"     {note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
