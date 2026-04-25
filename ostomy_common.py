"""
OstomyRedditDataInsight — logique partagée (extraction Reddit, analyse, Excel).

Installation :

    python3 -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt
    python -m spacy download en_core_web_sm

Exécution (au choix) :

    python reddit_extract.py --annee 2025 -o data_brutes/ostomy_2025   # seulement Reddit
    python ostomy_analyze.py -i data_brutes/ostomy_2025.jsonl            # seulement analyse
    python ostomy_reddit_data_insight.py                                 # les deux, d’un coup

L’année par défaut pour la config se règle avec `ANNEE_CIBLE` dans ce module.
"""

from __future__ import annotations

import json
import re
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import nltk
import pandas as pd
import requests
import spacy
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter
from nltk.corpus import stopwords
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

# ---------------------------------------------------------------------------
# Paramètres (période en UTC, année [ANNEE_CIBLE, ANNEE_CIBLE])
# ---------------------------------------------------------------------------
ANNEE_CIBLE: int = 2025
# Limite de sécurité : nombre max de posts conservés pour la période (0 = illimité)
PLAFOND_POSTS_PERIODE: int = 10_000
# Pause entre requêtes HTTP (cahier des charges : 2 s). Les 429 déclenchent une pause longue à part.
SLEEP_ENTRE_REQUETES_S: float = 2.0
TIMEOUT_S: int = 45
MAX_TENTATIVES_HTTP: int = 6
ATTENTE_S_SUR_429: float = 90.0
N_TOP_LEMMES: int = 100
SORT_FICHIER_EXCEL: str = "OstomyRedditDataInsight_Resultats.xlsx"
# Second fichier optionnel (vue épurée + top mots uniquement) pour partage / lecture
FICHIER_VUE_LECTURE: str = "OstomyRedditDataInsight_Vue_lecture.xlsx"
ECRIRE_FICHIER_VUE_LECTURE: bool = True
SUBREDDIT: str = "ostomy"

USER_AGENT: str = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# Le flux /new.json est plafonné (~1000 posts) et peut ne pas atteindre une année passée.
# En complément (toujours sur reddit.com, *.json), on interroge /search avec plusieurs requêtes.
ELARGISSEMENT_SEARCH: bool = True
# Lettres + quelques termes domaine (ajustable ; chaque requête = plusieurs pages possibles)
LISTE_QUERIES_RECHERCHE: list[str] = list("abcdefghijklmnopqrstuvwxyz") + [
    "ostomy",
    "stoma",
    "ileostomy",
    "colostomy",
]

# Chargement NLTK (stopwords) une seule fois
nltk.download("stopwords", quiet=True)
_STOPWORDS: set[str] = set(stopwords.words("english"))

# spaCy
_NLP: Any = spacy.load("en_core_web_sm", disable=["ner", "parser"])

# VADER
_VADER: SentimentIntensityAnalyzer = SentimentIntensityAnalyzer()


def bornes_annee_utc(annee: int) -> tuple[float, float]:
    """Retourne (timestamp_debut, timestamp_fin) en secondes, UTC, inclusif."""
    debut = datetime(annee, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    fin = datetime(annee, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
    return (debut.timestamp(), fin.timestamp())


def _requete_reddit(
    url: str,
    params: dict[str, str | int | None],
) -> requests.Response:
    """GET avec User-Agent, pause entre appels, retry sur 429."""
    headers = {"User-Agent": USER_AGENT}
    for tentative in range(MAX_TENTATIVES_HTTP):
        r = requests.get(url, params=params, headers=headers, timeout=TIMEOUT_S)
        if r.status_code == 429:
            attente = ATTENTE_S_SUR_429 + 30.0 * tentative
            print(f"  HTTP 429 — pause {attente:.0f}s avant nouvelle tentative…")
            time.sleep(attente)
            continue
        r.raise_for_status()
        return r
    r.raise_for_status()
    raise RuntimeError("requête Reddit: échec inattendu")


def _entree_de_t3(d: dict[str, Any]) -> dict[str, Any] | None:
    """Construit une entrée à partir d'un post t3 ; None si données insuffisantes."""
    pid = d.get("id")
    if not pid:
        return None
    cu = d.get("created_utc")
    if cu is None:
        return None
    title = (d.get("title") or "") or ""
    selftext = (d.get("selftext") or "") or ""
    fusion = f"{title}\n{selftext}".strip()
    return {
        "id": pid,
        "created_utc": float(cu),
        "title": title,
        "selftext": selftext,
        "Titre_et_Message_Original": fusion,
    }


def _ajouter_si_periode(
    d: dict[str, Any],
    ts_deb: float,
    ts_fin: float,
    by_id: dict[str, dict[str, Any]],
) -> bool:
    """
    Ajoute le post s'il est dans la fenêtre temporelle. Retourne False si plafond atteint
    (arrêt demandé).
    """
    cu = d.get("created_utc")
    if cu is None:
        return True
    ft = float(cu)
    if not (ts_deb <= ft <= ts_fin):
        return True
    if PLAFOND_POSTS_PERIODE and len(by_id) >= PLAFOND_POSTS_PERIODE:
        return False
    ent = _entree_de_t3(d)
    if ent is None:
        return True
    by_id[ent["id"]] = ent
    return True


def nettoyer_lemmatiser(texte: str) -> str:
    """Minuscules, retrait stopwords/ponctuation/chiffres, lemmatisation via spaCy."""
    if not texte or not str(texte).strip():
        return ""
    doc = _NLP(str(texte).lower())
    mots: list[str] = []
    for t in doc:
        if t.is_punct or t.is_space or t.like_num:
            continue
        w = t.lemma_.lower().strip()
        if not w or w in _STOPWORDS or re.match(r"^[^a-z]+$", w):
            continue
        mots.append(w)
    return " ".join(mots)


def extraire_posts_periode(
    ts_deb: float,
    ts_fin: float,
) -> tuple[list[dict[str, Any]], int, int, str]:
    """
    1) /r/.../new.json : pagination (plafond Reddit ~1000) + filtre période.
    2) /r/.../search.json : requêtes multiples + pagination + filtre, déduplication par id.
    """
    by_id: dict[str, dict[str, Any]] = {}
    n_requetes = 0
    notes: list[str] = []
    tete_new = f"https://www.reddit.com/r/{SUBREDDIT}/new.json"
    params_new: dict[str, str | int] = {"limit": 100, "raw_json": 1}
    plafond_stop = False

    # —— Étape A : new.json (spécification initiale) ——
    after: str | None = None
    premiere_new = True
    note_new = "indefini"
    while not plafond_stop:
        if not premiere_new:
            time.sleep(SLEEP_ENTRE_REQUETES_S)
        premiere_new = False
        p = {**params_new, **({"after": after} if after else {})}
        n_requetes += 1
        r = _requete_reddit(tete_new, p)
        payload = r.json()
        data = payload.get("data") or {}
        children: list[dict[str, Any]] = data.get("children") or []

        for child in children:
            if child.get("kind") != "t3":
                continue
            d = child.get("data") or {}
            if not _ajouter_si_periode(d, ts_deb, ts_fin, by_id):
                plafond_stop = True
                note_new = f"arret_plafond_{PLAFOND_POSTS_PERIODE}"
                break
        if plafond_stop:
            break

        if PLAFOND_POSTS_PERIODE and len(by_id) >= PLAFOND_POSTS_PERIODE:
            note_new = f"arret_plafond_{PLAFOND_POSTS_PERIODE}"
            break

        if not children:
            note_new = "arret_liste_vide"
            break

        last = children[-1]
        if last.get("kind") == "t3" and (last.get("data") or {}).get("created_utc") is not None:
            plus_ancien = float((last.get("data") or {})["created_utc"])
            if plus_ancien < ts_deb:
                note_new = "arret_toutes_pages_apres_ancien_avant_debut_fenetre_ou_pas_d_after"
                break

        after = data.get("after")
        if not after:
            note_new = "arret_pas_d_after"
            break

    notes.append(f"new:{note_new},n_pertinents={len(by_id)}")

    # —— Étape B : search.json (élargissement, même subreddit) ——
    if ELARGISSEMENT_SEARCH and not plafond_stop:
        tete_search = f"https://www.reddit.com/r/{SUBREDDIT}/search.json"
        n_avant_search = len(by_id)
        n_q = len(LISTE_QUERIES_RECHERCHE)
        print(
            f"Phase recherche (search.json) : {n_q} requêtes, "
            f"{SLEEP_ENTRE_REQUETES_S:.0f}s entre appels (patience)…"
        )
        for i, requ in enumerate(LISTE_QUERIES_RECHERCHE, start=1):
            print(f"  [{i}/{n_q}] q={requ!r}", flush=True)
            if plafond_stop:
                break
            after_s: str | None = None
            premiere_s = True
            while not plafond_stop:
                if not premiere_s:
                    time.sleep(SLEEP_ENTRE_REQUETES_S)
                premiere_s = False
                n_requetes += 1
                p_s: dict[str, str | int | None] = {
                    "q": requ,
                    "restrict_sr": 1,
                    "sort": "new",
                    "limit": 100,
                    "raw_json": 1,
                    **({"after": after_s} if after_s else {}),
                }
                r2 = _requete_reddit(tete_search, p_s)
                pl = r2.json()
                d2 = pl.get("data") or {}
                ch2: list[dict[str, Any]] = d2.get("children") or []
                for child in ch2:
                    if child.get("kind") != "t3":
                        continue
                    d = child.get("data") or {}
                    if not _ajouter_si_periode(d, ts_deb, ts_fin, by_id):
                        plafond_stop = True
                        break
                if plafond_stop:
                    break
                after_s = d2.get("after")
                if not after_s:
                    break
        n_apres = len(by_id)
        notes.append(
            f"search:requetes={len(LISTE_QUERIES_RECHERCHE)},+posts={n_apres - n_avant_search}"
        )

    if plafond_stop and not any("plafond" in n for n in notes[-2:]):
        notes.append(f"arret_plafond_{PLAFOND_POSTS_PERIODE}")

    entrees = sorted(
        by_id.values(), key=lambda x: x["created_utc"], reverse=True
    )
    run_full = " | ".join(notes)
    return entrees, n_requetes, len(entrees), run_full


def _chemins_fichiers_bruts(chemin_base: str) -> tuple[Path, Path]:
    """`chemin_base` = sans extension, ou avec `.jsonl` → (jsonl, meta.json)."""
    p = Path(chemin_base)
    if p.suffix == ".jsonl":
        jsonl = p
    else:
        jsonl = p.with_suffix(".jsonl")
    meta = jsonl.parent / f"{jsonl.stem}.meta.json"
    return jsonl, meta


def sauvegarder_posts_bruts(
    chemin_base: str,
    entrees: list[dict[str, Any]],
    meta: dict[str, Any],
) -> tuple[str, str]:
    """
    Enregistre un JSONL (une ligne = un post : id, created_utc, title, selftext)
    et un fichier .meta.json (paramètres d’extraction).
    """
    jsonl, metaf = _chemins_fichiers_bruts(chemin_base)
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


def charger_posts_bruts(chemin_jsonl: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Charge le JSONL + le .meta.json du même nom (s’il existe)."""
    jsonl, metaf = _chemins_fichiers_bruts(chemin_jsonl)
    if not jsonl.is_file():
        raise FileNotFoundError(f"Fichier JSONL introuvable : {jsonl}")
    entrees: list[dict[str, Any]] = []
    with open(jsonl, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entrees.append(json.loads(line))
    meta: dict[str, Any] = {}
    if metaf.is_file():
        with open(metaf, encoding="utf-8") as f:
            meta = json.load(f)
    return entrees, meta


def analyser_entrees_vers_dataframe(
    entrees: list[dict[str, Any]],
    meta: dict[str, Any],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    À partir de posts bruts (ou JSONL) + meta : VADER, lemmatisation, Top 100, DataFrame complet.
    `meta` doit contenir au minimum période et infos d’extraction (voir `meta_extraction` dans extract).
    """
    p = meta.get("periode_utc") or {}
    ts_deb = p.get("debut_ts")
    ts_fin = p.get("fin_ts")
    n_req = meta.get("n_requetes", 0)
    n_posts = meta.get("n_posts", len(entrees))
    run_note = meta.get("code_arret", "")
    elarg = meta.get("elargissement_search", ELARGISSEMENT_SEARCH)
    inst_ext = meta.get("instant_extraction_utc", datetime.now(timezone.utc).isoformat())
    inst_analyse = datetime.now(timezone.utc).isoformat()

    if not entrees:
        df = pd.DataFrame(
            columns=[
                "id",
                "Date_Creation_UTC",
                "title",
                "selftext",
                "Titre_et_Message_Original",
                "Texte_Nettoye_et_Lemmatise",
                "Score_Sentiment_VADER",
            ]
        )
    else:
        rows: list[dict[str, Any]] = []
        for e in entrees:
            if "Titre_et_Message_Original" in e and e.get("Titre_et_Message_Original"):
                t = str(e["Titre_et_Message_Original"])
            else:
                title = (e.get("title") or "") or ""
                st = (e.get("selftext") or "") or ""
                t = f"{title}\n{st}".strip()
            score = _VADER.polarity_scores(t)["compound"]
            lem = nettoyer_lemmatiser(t)
            cu = e.get("created_utc")
            if cu is None:
                continue
            d_utc = pd.to_datetime(float(cu), unit="s", utc=True)
            rows.append(
                {
                    "id": e.get("id", ""),
                    "Date_Creation_UTC": d_utc,
                    "title": (e.get("title") or "") or "",
                    "selftext": (e.get("selftext") or "") or "",
                    "Titre_et_Message_Original": t,
                    "Texte_Nettoye_et_Lemmatise": lem,
                    "Score_Sentiment_VADER": score,
                }
            )
        df = pd.DataFrame(rows)

    meta_ligne: dict[str, Any] = {
        "Extraction_Periode_Deb_UTC": (
            pd.Timestamp(ts_deb, unit="s", tz="UTC") if ts_deb is not None else pd.NaT
        ),
        "Extraction_Periode_Fin_UTC": (
            pd.Timestamp(ts_fin, unit="s", tz="UTC") if ts_fin is not None else pd.NaT
        ),
        "Extraction_N_Requetes": n_req,
        "Extraction_N_Posts_Retenus": n_posts,
        "Extraction_Elargissement_Search": elarg,
        "Extraction_Code_Arret": str(run_note),
        "Extraction_Instant_UTC": inst_ext,
        "Analyse_Instant_UTC": inst_analyse,
    }
    for k, v in meta_ligne.items():
        df[k] = v
    ordre = list(meta_ligne.keys()) + [c for c in df.columns if c not in meta_ligne]
    df = df[ordre]

    cpt: Counter[str] = Counter()
    for s in df["Texte_Nettoye_et_Lemmatise"].dropna():
        for w in str(s).split():
            if w:
                cpt[w] += 1
    top_df = pd.DataFrame(
        cpt.most_common(N_TOP_LEMMES), columns=["mot", "occurrences"]
    )
    return df, top_df


def _datetime_pour_excel(df: pd.DataFrame) -> pd.DataFrame:
    """Excel / openpyxl : convertir les datetime tz-aware en UTC naïf."""
    out = df.copy()
    for col in out.columns:
        if not pd.api.types.is_datetime64_any_dtype(out[col]):
            continue
        s = out[col]
        try:
            if getattr(s.dt, "tz", None) is not None:
                out[col] = s.dt.tz_convert("UTC").dt.tz_localize(None)
        except (TypeError, AttributeError):
            pass
    return out


def analyser_depuis_fichier_brut(
    chemin_jsonl: str,
    sortie_excel: str,
    annee_affichage: int = 0,
) -> None:
    """
    Charge un export JSONL + .meta.json et génère les Excel (sans requêtes Reddit).
    `annee_affichage` : 0 = prendre l’année du .meta.json si possible, sinon `ANNEE_CIBLE`.
    """
    entrees, meta = charger_posts_bruts(chemin_jsonl)
    p = meta.get("periode_utc") or {}
    an = annee_affichage
    if an <= 0 and p.get("label"):
        try:
            an = int(str(p["label"]).split(".", maxsplit=1)[0])
        except (TypeError, ValueError):
            an = 0
    if an <= 0:
        an = ANNEE_CIBLE
    annee_affichage = an
    meta = {**meta, "n_posts": len(entrees)}
    df, top_df = analyser_entrees_vers_dataframe(entrees, meta)
    df_x = _datetime_pour_excel(df)
    pex = Path(sortie_excel)
    vue = str(pex.with_name(f"{pex.stem}_Vue_lecture{pex.suffix}"))
    ecrire_classeur_excel(
        sortie_excel,
        df_x,
        top_df,
        annee_affichage,
        chemin_vue_lecture=vue,
        nom_rapport_complet=sortie_excel,
    )
    print(
        f"Analyse terminée : {sortie_excel} ({len(entrees)} posts). "
        f"Source : {chemin_jsonl}"
    )
    if ECRIRE_FICHIER_VUE_LECTURE:
        print(f"Fichier lecture : {vue}")


def _titre_feuille(
    ws: Any,
    titre: str,
    description: str,
    n_cols: int,
    ligne_entete: int = 3,
) -> None:
    """Lignes 1 et 2 : titre et description (fusionnés) ; `ligne_entete` = ligne des intitulés de colonnes."""
    fin = get_column_letter(n_cols)
    ws.merge_cells(f"A1:{fin}1")
    c1 = ws["A1"]
    c1.value = titre
    c1.font = Font(bold=True, size=13)
    c1.alignment = Alignment(wrap_text=True, vertical="top")
    ws.merge_cells(f"A2:{fin}2")
    c2 = ws["A2"]
    c2.value = description
    c2.alignment = Alignment(wrap_text=True, vertical="top")
    ws.row_dimensions[1].height = 32
    ws.row_dimensions[2].height = min(150, 36 + 14 * (len(description) // 90))
    for co in range(1, n_cols + 1):
        h = ws.cell(row=ligne_entete, column=co)
        if h.value is not None:
            h.font = Font(bold=True)
            h.alignment = Alignment(wrap_text=True, vertical="top")


def _retour_ligne_plage(
    ws: Any,
    cols: list[int],
    ligne_1: int,
    ligne_n: int,
) -> None:
    for lig in range(ligne_1, ligne_n + 1):
        for co in cols:
            cell = ws.cell(row=lig, column=co)
            if cell.value is not None and str(cell.value) != "nan":
                cell.alignment = Alignment(wrap_text=True, vertical="top")


def _colonnes_texte_larges(ws: Any, mapping: dict[str, float]) -> None:
    for lettre, w in mapping.items():
        ws.column_dimensions[lettre].width = w


def ecrire_classeur_excel(
    chemin: str,
    df_x: pd.DataFrame,
    top_df: pd.DataFrame,
    annee: int,
    chemin_vue_lecture: str | None = None,
    nom_rapport_complet: str | None = None,
) -> None:
    """
    Un seul fichier : index, étapes 1–2, données complètes, synthèse lisible, top 100 mots.
    Titre + descriptif en tête de chaque feuille de tableau ; retours à la ligne pour les longs textes.
    """
    vides = df_x.empty
    if not vides:
        d1 = df_x[
            ["id", "Date_Creation_UTC", "title", "selftext"]
        ].rename(
            columns={
                "id": "Identifiant post (Reddit)",
                "Date_Creation_UTC": "Date de publication (UTC)",
                "title": "Titre seul",
                "selftext": "Corps du message (selftext ; peut être vide si lien)",
            }
        )
        d2 = df_x[
            [
                "id",
                "Date_Creation_UTC",
                "Titre_et_Message_Original",
                "Texte_Nettoye_et_Lemmatise",
            ]
        ].rename(
            columns={
                "id": "Identifiant post (Reddit)",
                "Date_Creation_UTC": "Date de publication (UTC)",
                "Titre_et_Message_Original": "Titre + message (texte d’origine, non nettoyé)",
                "Texte_Nettoye_et_Lemmatise": "Texte après nettoyage (stopwords) et lemmatisation (spaCy)",
            }
        )
        d_synt = df_x[
            [
                "id",
                "Date_Creation_UTC",
                "Titre_et_Message_Original",
                "Texte_Nettoye_et_Lemmatise",
                "Score_Sentiment_VADER",
            ]
        ].rename(
            columns={
                "id": "Identifiant",
                "Date_Creation_UTC": "Date (UTC)",
                "Titre_et_Message_Original": "Titre et message (lisible, retours à la ligne)",
                "Texte_Nettoye_et_Lemmatise": "Lemmes (mots retenus pour le lexique)",
                "Score_Sentiment_VADER": "Score VADER, compound (entre −1 et +1)",
            }
        )
    else:
        d1 = pd.DataFrame(
            columns=[
                "Identifiant post (Reddit)",
                "Date de publication (UTC)",
                "Titre seul",
                "Corps du message (selftext ; peut être vide si lien)",
            ]
        )
        d2 = pd.DataFrame(
            columns=[
                "Identifiant post (Reddit)",
                "Date de publication (UTC)",
                "Titre + message (texte d’origine, non nettoyé)",
                "Texte après nettoyage (stopwords) et lemmatisation (spaCy)",
            ]
        )
        d_synt = pd.DataFrame(
            columns=[
                "Identifiant",
                "Date (UTC)",
                "Titre et message (lisible, retours à la ligne)",
                "Lemmes (mots retenus pour le lexique)",
                "Score VADER, compound (entre −1 et +1)",
            ]
        )

    d1b = _datetime_pour_excel(d1) if not vides else d1
    d2b = _datetime_pour_excel(d2) if not vides else d2
    d3b = _datetime_pour_excel(d_synt) if not vides else d_synt

    top_aff = top_df.rename(
        columns={
            "mot": "Lemme (forme de base)",
            "occurrences": "Nombre d’occurrences (tout le corpus)",
        }
    )

    guide = (
        f"OstomyRedditDataInsight — année cible {annee} (UTC). "
        "Lisez ce guide puis consultez chaque onglet.\n\n"
        "• « 00_Index » : ce texte d’aide.\n"
        "• « 01_Extraction » : contenu tel que reçu de Reddit (titre + corps séparés). "
        "Une ligne = un post, sans score ni lemmatisation.\n"
        "• « 02_Texte_prepare » : fusion titre+corps, puis lemmatisation (analyse) ; c’est l’étape d’où vient le Top 100.\n"
        "• « 03_Donnees_completes » : toute la base + colonnes d’extraction (requêtes, période, etc.).\n"
        "• « 04_Synthese_lecture » : vue allégée pour lire ; les cellules de texte sont cadrées avec retours à la ligne.\n"
        "• « 05_Top_100_mots » : les 100 lemmes les plus fréquents sur l’ensemble des textes nettoyés, avec effectifs."
    )

    start = 2  # en-têtes de tableau à la ligne 3 (1-based) ; 2 = 0-based pour pandas
    with pd.ExcelWriter(chemin, engine="openpyxl") as writer:
        # Index (une seule cellule, sans ligne d’en-tête de colonne parasite)
        pd.DataFrame([[guide]]).to_excel(
            writer, sheet_name="00_Index", index=False, header=False, startrow=0
        )
        w0 = writer.sheets["00_Index"]
        w0.merge_cells("A1:F1")
        w0["A1"].alignment = Alignment(wrap_text=True, vertical="top")
        w0["A1"].font = Font(bold=True, size=11)
        w0.column_dimensions["A"].width = 95
        w0.row_dimensions[1].height = 220

        def _w(
            sh: str,
            dfb: pd.DataFrame,
            titre: str,
            desc: str,
            largeurs: dict[str, float] | None = None,
        ) -> None:
            dfb.to_excel(
                writer, sheet_name=sh, index=False, startrow=start, header=True
            )
            ws_ = writer.sheets[sh]
            nc = max(1, dfb.shape[1])
            _titre_feuille(ws_, titre, desc, nc, ligne_entete=3)
            if not dfb.empty:
                l_last = 3 + len(dfb)
                _retour_ligne_plage(
                    ws_, list(range(1, nc + 1)), 4, l_last
                )
            if largeurs:
                _colonnes_texte_larges(ws_, largeurs)
            else:
                _colonnes_texte_larges(
                    ws_,
                    {get_column_letter(i + 1): 18.0 for i in range(nc)},
                )
            try:
                ws_.freeze_panes = "A4"
            except Exception:
                pass

        _w(
            "01_Extraction",
            d1b,
            f"Étape 1 — Extraction Reddit (r/{SUBREDDIT})",
            "Données brutes : identifiant, date, titre seul, corps. Aucun score de sentiment ni lemmatisation. "
            "C’est la sortie directe de l’API JSON (hors commentaires).",
            largeurs={"A": 12, "B": 20, "C": 40, "D": 55},
        )
        _w(
            "02_Texte_prepare",
            d2b,
            f"Étape 2 — Texte fusionné, puis préparé pour l’analyse",
            "Colonne « Titre + message » : concaténation pour le reste du pipeline. "
            "Colonne de droite : mots vides (anglais) retirés, lemmatisation spaCy, pour le décompte lexical et l’illustration des thèmes fréquents.",
            largeurs={"A": 12, "B": 20, "C": 55, "D": 50},
        )

        # Données complètes
        df_x.to_excel(
            writer,
            sheet_name="03_Donnees_completes",
            index=False,
            startrow=start,
        )
        wdc = writer.sheets["03_Donnees_completes"]
        nc = max(1, df_x.shape[1])
        _titre_feuille(
            wdc,
            "Table principale — toutes les colonnes, avec paramètres d’exécution",
            "Métadonnées d’abord (période UTC, nombre de requêtes, etc.), puis champs par post. "
            "VADER a été appliqué sur « Titre_et_Message_Original ». Les colonnes longues s’affichent sur plusieurs lignes si vous élargissez la vue.",
            nc,
        )
        if not df_x.empty:
            hmap = {wdc.cell(3, j).value: j for j in range(1, nc + 1) if wdc.cell(3, j).value}
            wrap_cols: list[int] = []
            for name in (
                "title",
                "selftext",
                "Titre_et_Message_Original",
                "Texte_Nettoye_et_Lemmatise",
                "Extraction_Code_Arret",
            ):
                if name in hmap:
                    wrap_cols.append(hmap[name])
            if not wrap_cols:
                wrap_cols = list(range(1, nc + 1))
            _retour_ligne_plage(wdc, wrap_cols, 4, 3 + len(df_x))
        for j in range(1, nc + 1):
            name = wdc.cell(3, j).value
            nstr = str(name) if name is not None else ""
            wcol = 16.0
            if any(
                k in nstr
                for k in (
                    "Titre",
                    "selftext",
                    "Message",
                    "Lemmat",
                    "Extraction_Code",
                )
            ):
                wcol = 44.0
            elif nstr.startswith("Extraction_"):
                wcol = 22.0
            wdc.column_dimensions[get_column_letter(j)].width = wcol
        try:
            wdc.freeze_panes = "A4"
        except Exception:
            pass

        # Synthèse lecture (colonnes resserrées, texte riche)
        d3b.to_excel(
            writer,
            sheet_name="04_Synthese_lecture",
            index=False,
            startrow=start,
        )
        wsy = writer.sheets["04_Synthese_lecture"]
        nsy = max(1, d3b.shape[1])
        _titre_feuille(
            wsy,
            "Synthèse — lecture confortable",
            "Vue réduite : identifiant, date, texte d’origine, lemmes, score. "
            "Les longs textes respectent les retours à la ligne (option Retour à la ligne automatique appliquée).",
            nsy,
        )
        if not d3b.empty:
            _retour_ligne_plage(
                wsy, [3, 4], 4, 3 + len(d3b)
            )  # C, D = titre+message, lemmes
        _colonnes_texte_larges(
            wsy,
            {
                "A": 12,
                "B": 18,
                "C": 60,
                "D": 45,
                "E": 14,
            },
        )
        try:
            wsy.freeze_panes = "A4"
        except Exception:
            pass

        # Top 100
        top_aff.to_excel(
            writer, sheet_name="05_Top_100_mots", index=False, startrow=start
        )
        wtp = writer.sheets["05_Top_100_mots"]
        ntc = max(1, top_aff.shape[1])
        _titre_feuille(
            wtp,
            "Agrégat lexical — 100 mots (lemmes) les plus fréquents",
            "Décompte sur la colonne « texte nettoyé + lemmatisé » (tous les posts confondus). "
            "Les mots vides en anglais (stopwords NLTK) ont été retirés avant lemmatisation. Ce n’est pas un modèle de thèmes (LDA) ; c’est un classement d’occurrences.",
            ntc,
        )
        if not top_aff.empty:
            _retour_ligne_plage(wtp, [1, 2], 4, 3 + len(top_aff))
        wtp.column_dimensions["A"].width = 28
        wtp.column_dimensions["B"].width = 32
        try:
            wtp.freeze_panes = "A4"
        except Exception:
            pass

    if ECRIRE_FICHIER_VUE_LECTURE:
        pvue = chemin_vue_lecture
        if not pvue:
            pc = Path(chemin)
            pvue = str(pc.with_name(f"{pc.stem}_Vue_lecture{pc.suffix}"))
        _ecrire_fichier_vue_lecture(
            pvue,
            d3b,
            top_aff,
            annee,
            start,
            nom_rapport_complet or chemin,
        )


def _ecrire_fichier_vue_lecture(
    chemin: str,
    d3b: pd.DataFrame,
    top_aff: pd.DataFrame,
    annee: int,
    start: int,
    nom_rapport_complet: str,
) -> None:
    """Deux feuilles (synthèse + top mots) + note, pour lecture ou envoi ciblé."""
    intro = (
        f"Vue extraite — OstomyRedditDataInsight, année cible {annee} (UTC).\n"
        "Contenu : « Synthèse » (identifiant, date, textes, score VADER) et « Top_100_mots ». "
        f"Fichier jumeau allégé du rapport complet ({nom_rapport_complet})."
    )
    with pd.ExcelWriter(chemin, engine="openpyxl") as writer:
        pd.DataFrame([[intro]]).to_excel(
            writer, sheet_name="00_Note", index=False, header=False, startrow=0
        )
        wn = writer.sheets["00_Note"]
        wn.merge_cells("A1:E1")
        wn["A1"].alignment = Alignment(wrap_text=True, vertical="top")
        wn["A1"].font = Font(size=11)
        wn.column_dimensions["A"].width = 85
        wn.row_dimensions[1].height = 60

        d3b.to_excel(
            writer, sheet_name="01_Synthese", index=False, startrow=start
        )
        wsy = writer.sheets["01_Synthese"]
        nsy = max(1, d3b.shape[1])
        _titre_feuille(
            wsy,
            "Lecture des posts — texte + lemmes + sentiment",
            "Une ligne = un fil Reddit. Colonnes C–D : retours à la ligne activés. "
            "Score VADER sur le texte d’origine (titre + message).",
            nsy,
        )
        if not d3b.empty:
            _retour_ligne_plage(wsy, [3, 4], 4, 3 + len(d3b))
        _colonnes_texte_larges(
            wsy, {"A": 12, "B": 18, "C": 60, "D": 45, "E": 14}
        )
        wsy.freeze_panes = "A4"

        top_aff.to_excel(
            writer, sheet_name="02_Top_100_mots", index=False, startrow=start
        )
        wtp = writer.sheets["02_Top_100_mots"]
        ntc = max(1, top_aff.shape[1])
        _titre_feuille(
            wtp,
            "Lemmes les plus fréquents (classement)",
            "Les 100 formes de base (lemmes) les plus comptées sur tout le corpus, après retrait des mots vides (NLTK) et lemmatisation (spaCy).",
            ntc,
        )
        if not top_aff.empty:
            _retour_ligne_plage(wtp, [1, 2], 4, 3 + len(top_aff))
        wtp.column_dimensions["A"].width = 30
        wtp.column_dimensions["B"].width = 34
        wtp.freeze_panes = "A4"


def run() -> None:
    """Ancien comportement : extraction Reddit + analyse + Excel (une seule commande)."""
    ts_deb, ts_fin = bornes_annee_utc(ANNEE_CIBLE)
    entrees, n_req, n_posts, run_note = extraire_posts_periode(ts_deb, ts_fin)
    maintenant = datetime.now(timezone.utc).isoformat()
    if not entrees:
        print(
            f"Aucun post collecté pour {ANNEE_CIBLE} (UTC). "
            f"Requêtes: {n_req}, code arrêt: {run_note}."
        )
    posts = [
        {k: e[k] for k in ("id", "created_utc", "title", "selftext") if k in e}
        for e in entrees
    ]
    meta = {
        "version": 1,
        "periode_utc": {
            "debut_ts": ts_deb,
            "fin_ts": ts_fin,
            "label": str(ANNEE_CIBLE),
        },
        "n_requetes": n_req,
        "n_posts": n_posts,
        "code_arret": run_note,
        "elargissement_search": ELARGISSEMENT_SEARCH,
        "instant_extraction_utc": maintenant,
    }
    df, top_df = analyser_entrees_vers_dataframe(posts, meta)
    df_x = _datetime_pour_excel(df)
    pex = Path(SORT_FICHIER_EXCEL)
    vue = str(pex.with_name(f"{pex.stem}_Vue_lecture{pex.suffix}"))
    ecrire_classeur_excel(
        SORT_FICHIER_EXCEL,
        df_x,
        top_df,
        ANNEE_CIBLE,
        chemin_vue_lecture=vue,
        nom_rapport_complet=SORT_FICHIER_EXCEL,
    )
    print(
        f"Classeur principal: {SORT_FICHIER_EXCEL} (onglets 00→05). "
        f"Posts: {n_posts} | requêtes: {n_req} | {run_note}"
    )
    if ECRIRE_FICHIER_VUE_LECTURE:
        print(f"Fichier lecture seule: {vue}")


def extraire_vers_fichiers_bruts(chemin_base: str, annee: int) -> tuple[str, str, int, int, str]:
    """
    Télécharge depuis Reddit, enregistre .jsonl + .meta.json. Ne lance pas spaCy / VADER.
    Retourne (chemin_jsonl, chemin_meta, n_req, n_posts, run_note).
    """
    ts_deb, ts_fin = bornes_annee_utc(annee)
    entrees, n_req, n_posts, run_note = extraire_posts_periode(ts_deb, ts_fin)
    maintenant = datetime.now(timezone.utc).isoformat()
    meta = {
        "version": 1,
        "subreddit": SUBREDDIT,
        "periode_utc": {
            "debut_ts": ts_deb,
            "fin_ts": ts_fin,
            "label": str(annee),
        },
        "n_requetes": n_req,
        "n_posts": n_posts,
        "code_arret": run_note,
        "elargissement_search": ELARGISSEMENT_SEARCH,
        "instant_extraction_utc": maintenant,
    }
    cj, cm = sauvegarder_posts_bruts(chemin_base, entrees, meta)
    return cj, cm, n_req, n_posts, run_note


if __name__ == "__main__":
    run()
