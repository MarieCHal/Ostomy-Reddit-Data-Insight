#!/usr/bin/env python3
"""
Script autonome : télécharge les posts d'un subreddit (API JSON publique Reddit)
et écrit posts.jsonl + posts.meta.json.

Pipeline réseau (voir extraire_posts_periode) :
  1. /r/<sub>/new.json   — flux récent → ancien, filtre par created_utc
  2. /r/<sub>/search.json — optionnel ; plusieurs paramètres q= pour élargir le corpus
     (enregistrés dans meta sous queries_search_utilisees)

Un seul fichier à lancer depuis la racine du dépôt :

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
# Paramètres HTTP (alignés sur l'ancien flux ostomy_common).
# LISTE_QUERIES_* : paramètres « q= » pour la phase /search (voir extraire_posts_periode).
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
]
LISTE_QUERIES_RECHERCHE_GENERIQUE: list[str] = list(string.ascii_lowercase)

ARCTIC_SHIFT_POSTS_URL: str = (
    "https://arctic-shift.photon-reddit.com/api/posts/search"
)
ARCTIC_SHIFT_PAGE_LIMIT: int = 100

log = logging.getLogger(__name__)


# --- HTTP -----------------------------------------------------------------
def requete_reddit(url: str, params: dict[str, str | int | None]) -> Any:
    """
    GET vers un endpoint Reddit *.json (public, sans clé API).

    En-tête User-Agent obligatoire pour limiter les refus côté Reddit.
    En cas de 429 (trop de requêtes), attend puis réessaie jusqu'à MAX_TENTATIVES_HTTP.
    """
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


def requete_arctic_shift(
    session: Any,
    params: dict[str, str | int | None],
) -> Any:
    """
    GET vers l'API Arctic Shift (archive Reddit publique).

    Même schéma de posts que l'API Reddit ; utile quand reddit.com renvoie HTTP 403.
    """
    import requests

    headers = {"User-Agent": USER_AGENT}
    for tentative in range(MAX_TENTATIVES_HTTP):
        log.debug("GET %s params=%s", ARCTIC_SHIFT_POSTS_URL, params)
        try:
            r = session.get(
                ARCTIC_SHIFT_POSTS_URL,
                params=params,
                headers=headers,
                timeout=TIMEOUT_S,
            )
        except (
            requests.exceptions.Timeout,
            requests.exceptions.ConnectionError,
        ) as exc:
            attente = ATTENTE_S_SUR_429 + 15.0 * tentative
            log.warning(
                "Arctic Shift erreur réseau (%s) — pause %.0fs (%s/%s)…",
                type(exc).__name__,
                attente,
                tentative + 1,
                MAX_TENTATIVES_HTTP,
            )
            time.sleep(attente)
            continue
        if r.status_code == 429:
            attente = ATTENTE_S_SUR_429 + 30.0 * tentative
            log.warning(
                "Arctic Shift HTTP 429 — pause %.0fs (%s/%s)…",
                attente,
                tentative + 1,
                MAX_TENTATIVES_HTTP,
            )
            time.sleep(attente)
            continue
        r.raise_for_status()
        return r
    raise RuntimeError("requête Arctic Shift: échec inattendu")


def payload_children(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Extrait la liste `data.children` d'une réponse JSON Reddit (/new ou /search)."""
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
    """
    Dossier de run par défaut : results/<sub>/<debut>_<fin>[/limit_N].

    Le sous-dossier extract/ et le préfixe posts sont ajoutés par prefixe_posts().
    """
    base = Path(racine_results) / subreddit.lower() / f"{date_debut}_{date_fin}"
    if limit and limit > 0:
        base = base / f"limit_{limit}"
    return base


def prefixe_posts(dossier: Path) -> Path:
    """
    Chemin de base des fichiers bruts (sans extension).

    Produit …/<run>/extract/posts.jsonl et posts.meta.json via chemins_bruts().
    """
    extract_dir = dossier / "extract"
    extract_dir.mkdir(parents=True, exist_ok=True)
    return extract_dir / "posts"


def chemins_bruts(chemin_base: str | Path) -> tuple[Path, Path]:
    """
    Déduit les chemins JSONL et meta à partir d'un préfixe (avec ou sans .jsonl).

    Ex. chemin_base=…/posts → (…/posts.jsonl, …/posts.meta.json).
    """
    p = Path(chemin_base)
    jsonl = p if p.suffix == ".jsonl" else p.with_suffix(".jsonl")
    meta = jsonl.parent / f"{jsonl.stem}.meta.json"
    return jsonl, meta


def sauvegarder_posts_bruts(
    chemin_base: str | Path,
    entrees: list[dict[str, Any]],
    meta: dict[str, Any],
) -> tuple[str, str]:
    """
    Écrit le corpus brut : une ligne JSON par post + fichier .meta.json (paramètres du run).

    Champs JSONL : id, created_utc, title, selftext (soumissions uniquement, pas les commentaires).
    Retourne (chemin_jsonl, chemin_meta) en chaînes.
    """
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
    """
    Convertit --start / --end (YYYY-MM-DD) en timestamps Unix UTC inclusifs.

    Début : 00:00:00 du jour de début. Fin : 23:59:59 du jour de fin.
    Retourne (ts_debut, ts_fin, label_plage) pour filtrage et meta.
    """
    d0 = datetime.strptime(date_debut, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    d1 = datetime.strptime(date_fin, "%Y-%m-%d").replace(
        hour=23, minute=59, second=59, tzinfo=timezone.utc
    )
    if d1 < d0:
        raise ValueError("date_fin doit être >= date_debut")
    label = f"{date_debut}_{date_fin}"
    return d0.timestamp(), d1.timestamp(), label


def entree_de_t3(d: dict[str, Any]) -> dict[str, Any] | None:
    """
    Normalise un objet `data` Reddit de type t3 (soumission / post du fil).

    Retourne None si id ou created_utc manquants. Les commentaires (t1) sont ignorés ailleurs.
    """
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
    """
    Posts uniques collectés (clé = id Reddit), avec plafond optionnel (--limit).

    Utilisé pendant /new et /search pour dédupliquer les mêmes fils renvoyés par plusieurs requêtes.
    """

    by_id: dict[str, dict[str, Any]]
    limite: int  # 0 = pas de plafond

    def ajouter_si_periode(
        self,
        d: dict[str, Any],
        ts_deb: float,
        ts_fin: float,
    ) -> bool:
        """
        Ajoute le post s'il est dans [ts_deb, ts_fin] et sous la limite.

        Retourne False si le plafond est atteint (signal d'arrêt pour la boucle d'extraction).
        Retourne True si le post est hors période ou ignoré (on continue à paginer).
        """
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
    """
    Collecte les soumissions (t3) d'un subreddit sur une fenêtre temporelle UTC.

    Phase 1 — /new.json : flux antichronologique, pagination `after`, filtre created_utc.
    Phase 2 — /search.json (si elargissement_search) : pour chaque chaîne de
    liste_queries_recherche (ex. a…z, ostomy…), même filtre date + dédup par id.
    Les requêtes search ne filtrent pas le texte des posts : elles servent à découvrir
    plus d'URL de posts que /new seul n'atteint pas toujours.

    Retourne (posts_triés_récents_d'abord, n_requêtes_http, n_posts, note_run).
    note_run documente pourquoi l'extraction s'est arrêtée (plafond, liste vide, etc.).
    """
    etat = EtatPlafond(by_id={}, limite=limite_posts)
    n_requetes = 0
    notes: list[str] = []
    sub = subreddit.strip().removeprefix("r/").strip()
    plafond_stop = False

    tete_new = f"https://www.reddit.com/r/{sub}/new.json"
    params_new: dict[str, str | int] = {"limit": 100, "raw_json": 1}

    # --- Phase 1 : /new (posts récents → plus anciens) -----------------------
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

        # Arrêt anticipé : la page la plus ancienne est déjà avant le début de la fenêtre
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

    # --- Phase 2 : /search (élargissement ; liste enregistrée dans meta queries_search_utilisees)
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
                # q= requ : paramètre de recherche Reddit (pas un filtre sur le texte final)
                p_s: dict[str, str | int | None] = {
                    "q": requ,
                    "restrict_sr": 1,  # limiter la recherche à ce subreddit
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


def extraire_posts_arctic_shift(
    subreddit: str,
    ts_deb: float,
    ts_fin: float,
    limite_posts: int,
    sleep_s: float,
) -> tuple[list[dict[str, Any]], int, int, str]:
    """
    Collecte les soumissions via Arctic Shift (archive Reddit), même fenêtre UTC.

    Pagination par created_utc croissant ; dédup par id ; mêmes champs que posts.jsonl.
    """
    import requests

    sub = subreddit.strip().removeprefix("r/").strip()
    by_id: dict[str, dict[str, Any]] = {}
    n_requetes = 0
    cursor_after = int(ts_deb)
    note = "arctic_shift_pagination"
    session = requests.Session()

    log.info(
        "Phase Arctic Shift — r/%s (fenêtre UTC [%.0f, %.0f])",
        sub,
        ts_deb,
        ts_fin,
    )

    while True:
        if limite_posts and len(by_id) >= limite_posts:
            note = f"arret_plafond_{limite_posts}"
            break

        params: dict[str, str | int | None] = {
            "subreddit": sub,
            "after": cursor_after,
            "before": int(ts_fin),
            "limit": ARCTIC_SHIFT_PAGE_LIMIT,
            "sort": "asc",
        }
        if n_requetes:
            pause = min(sleep_s, 0.5)
            log.info("Pause %.1fs avant requête Arctic Shift…", pause)
            time.sleep(pause)
        n_requetes += 1
        r = requete_arctic_shift(session, params)
        batch = (r.json().get("data") or [])
        if not batch:
            note = "arret_liste_vide"
            break

        plafond_stop = False
        for d in batch:
            ent = entree_de_t3(d)
            if ent is None:
                continue
            cu = ent["created_utc"]
            if not (ts_deb <= cu <= ts_fin):
                continue
            if limite_posts and len(by_id) >= limite_posts:
                plafond_stop = True
                note = f"arret_plafond_{limite_posts}"
                break
            by_id[ent["id"]] = ent
        if plafond_stop:
            break

        last_cu = float((batch[-1].get("created_utc") or 0))
        cursor_after = int(last_cu) + 1
        log.info(
            "[arctic-shift] requêtes=%s posts_dans_fenêtre=%s cursor_after=%s",
            n_requetes,
            len(by_id),
            cursor_after,
        )
        if cursor_after > int(ts_fin):
            note = "arret_fin_fenetre"
            break
        if len(batch) < ARCTIC_SHIFT_PAGE_LIMIT:
            note = "arret_derniere_page"
            break

    entrees = sorted(by_id.values(), key=lambda x: x["created_utc"], reverse=True)
    log.info(
        "Extraction Arctic Shift terminée — posts=%s requêtes_http=%s résumé: %s",
        len(entrees),
        n_requetes,
        note,
    )
    return entrees, n_requetes, len(entrees), note


def extraire_vers_fichiers_bruts(
    chemin_base: str,
    subreddit: str,
    date_debut: str,
    date_fin: str,
    limite_posts: int,
    liste_queries_recherche: list[str],
    elargissement_search: bool,
    sleep_s: float,
    source: str = "auto",
) -> tuple[str, str, int, int, str]:
    """
    Orchestre l'extraction réseau puis l'écriture posts.jsonl + posts.meta.json.

    Le meta inclut la période, le code d'arrêt, et queries_search_utilisees si /search a tourné.
    Retourne (chemin_jsonl, chemin_meta, n_requêtes_http, n_posts, note_run).
    """
    import requests

    ts_deb, ts_fin, label_plage = bornes_dates_utc_iso(date_debut, date_fin)
    source_effectif = source
    if source == "arctic-shift":
        entrees, n_req, n_posts, run_note = extraire_posts_arctic_shift(
            subreddit=subreddit,
            ts_deb=ts_deb,
            ts_fin=ts_fin,
            limite_posts=limite_posts,
            sleep_s=sleep_s,
        )
    else:
        try:
            entrees, n_req, n_posts, run_note = extraire_posts_periode(
                subreddit=subreddit,
                ts_deb=ts_deb,
                ts_fin=ts_fin,
                limite_posts=limite_posts,
                liste_queries_recherche=liste_queries_recherche,
                elargissement_search=elargissement_search,
                sleep_s=sleep_s,
            )
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else None
            if source == "auto" and status == 403:
                log.warning(
                    "Reddit HTTP 403 — bascule automatique sur Arctic Shift "
                    "(archive publique)."
                )
                source_effectif = "arctic-shift"
                entrees, n_req, n_posts, run_note = extraire_posts_arctic_shift(
                    subreddit=subreddit,
                    ts_deb=ts_deb,
                    ts_fin=ts_fin,
                    limite_posts=limite_posts,
                    sleep_s=sleep_s,
                )
            else:
                raise
    maintenant = datetime.now(timezone.utc).isoformat()
    meta = {
        "version": 1,
        "source": source_effectif,
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
        "elargissement_search": (
            elargissement_search if source_effectif != "arctic-shift" else False
        ),
        "queries_search_utilisees": (
            liste_queries_recherche
            if elargissement_search and source_effectif != "arctic-shift"
            else []
        ),
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
    """Active les logs horodatés sur stdout (INFO par défaut, DEBUG avec -v)."""
    niveau = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=niveau,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
        force=True,
    )


def resoudre_liste_queries(subreddit: str, mode: str) -> list[str]:
    """
    Choisit les valeurs `q=` pour la phase /search (--search-queries).

    auto : liste « domaine » pour r/ostomy, sinon alphabet a–z seulement.
    """
    sub = subreddit.strip().removeprefix("r/").strip().lower()
    if mode == "ostomy":
        return list(LISTE_QUERIES_RECHERCHE_OSTOMY)
    if mode == "generic":
        return list(LISTE_QUERIES_RECHERCHE_GENERIQUE)
    if sub == "ostomy":
        return list(LISTE_QUERIES_RECHERCHE_OSTOMY)
    return list(LISTE_QUERIES_RECHERCHE_GENERIQUE)


def construire_parser() -> argparse.ArgumentParser:
    """Définit la CLI reddit-subreddit-extract (voir --help et EPILOG)."""
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
    p.add_argument(
        "--source",
        choices=("auto", "reddit", "arctic-shift"),
        default="auto",
        help=(
            "Source des posts : reddit (API publique), arctic-shift (archive), "
            "ou auto (reddit puis arctic-shift si HTTP 403)."
        ),
    )
    p.add_argument("-v", "--verbose", action="store_true", help="Logs DEBUG.")
    return p


def main(argv: Sequence[str] | None = None) -> int:
    """Point d'entrée : parse les arguments, lance l'extraction, affiche le résumé."""
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
        source=args.source,
    )
    print(f"OK — JSONL : {cj}")
    print(f"     Meta : {cm}")
    print(f"     posts = {n_posts} | requêtes HTTP = {n_req}")
    print(f"     {note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
