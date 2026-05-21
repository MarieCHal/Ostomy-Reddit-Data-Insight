# Marche à suivre — sample 300 posts r/ostomy (2025)

Corpus cible : **300 posts** du subreddit **r/ostomy**, période **2025-01-01 → 2025-12-31** (UTC).

Sortie finale recommandée : **`scorer/posts_Corpus_Report.xlsx`** (texte + thèmes multi-label + sentiment).

---

## Prérequis

Depuis la racine du dépôt :

```bash
cd /Users/mariechalard/Desktop/Ostomy-Reddit-Data-Insight
```

Environnements (une fois) :

```bash
python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements-extract.txt
python3 -m venv .venv-themes && source .venv-themes/bin/activate && pip install -r subreddit_themes/requirements.txt
# .venv-scorer optionnel si .venv-themes déjà prêt (mêmes deps PyTorch)
```

Variables communes pour la suite :

```bash
RUN_DIR="results/ostomy/2025-01-01_2025-12-31/limit_300"
POSTS_JSONL="$RUN_DIR/extract/posts.jsonl"
```

---

## Étape 1 — Extraction (~5–20 min selon réseau Reddit)

```bash
source .venv/bin/activate

python3 subreddit_extract/extract_subreddit.py \
  -s ostomy \
  --start 2025-01-01 \
  --end 2025-12-31 \
  --limit 300 \
  -v
```

**Sorties :**

- `results/ostomy/2025-01-01_2025-12-31/limit_300/extract/posts.jsonl`
- `…/extract/posts.meta.json` (requêtes search, dates, etc.)

**Vérification rapide :**

```bash
wc -l "$POSTS_JSONL"
# → doit afficher 300 (ou moins si Reddit n’a pas assez de posts dans la plage)
```

---

## Étape 2 — Thèmes BART multi-label (~30–90 min sur 300 posts, MPS/CPU)

```bash
source .venv-themes/bin/activate

python3 subreddit_themes/classify_subreddit_posts.py \
  -i "$POSTS_JSONL"
```

Paramètres par défaut (YAML) : 13 catégories, seuil **0.40**, troncature **1000 car.**

**Sorties :**

- `…/themes/posts.themes.jsonl`
- `…/themes/posts.themes.meta.json`

**Rapport thèmes seul (optionnel) :**

```bash
python3 subreddit_themes/report_workbook.py --run-dir "$RUN_DIR"
# → …/themes/posts_Themes_Report.xlsx
```

---

## Étape 3 — Sentiment RoBERTa (~5–15 min sur 300 posts)

```bash
source .venv-themes/bin/activate   # ou .venv-scorer

python3 subreddit_scorer/score_subreddit_posts.py \
  -i "$POSTS_JSONL"
```

**Sorties :**

- `…/scorer/posts.sentiment.jsonl`
- `…/scorer/posts.sentiment.meta.json`

---

## Étape 4 — Tableau combiné (quelques secondes)

```bash
python3 subreddit_scorer/report_workbook.py --run-dir "$RUN_DIR"
```

**Livrable principal :**

- `…/scorer/posts_Corpus_Report.xlsx`

Feuilles :

| Feuille | Contenu |
|---------|---------|
| **Guide** | Mode d’emploi |
| **Posts_corpus** | 1 ligne / post : texte, sentiment, `label_*`, `score_*` |
| **Sentiment_distribution** | positive / negative / neutral |
| **Theme_distribution** | fréquence par catégorie (multi-label) |
| **Run_info** | modèles, seuils |

---

## Relecture manuelle (équipe)

1. Ouvrir **`Posts_corpus`**
2. **Données → Filtre**
3. `label_digestive_relevance = 1` → corpus stomie digestive
4. `label_crisis_suicidal_ideation = 0` (ou relire les `= 1`)
5. Explorer C9 : `label_hospital_to_home_transition = 1`
6. Lire **`text_for_review`**, valider / corriger les `label_*` à la main si besoin
7. Croiser avec **`sentiment_polarity_index`** (−1…+1)

---

## Bloc copier-coller (tout enchaîner)

```bash
cd /Users/mariechalard/Desktop/Ostomy-Reddit-Data-Insight
RUN_DIR="results/ostomy/2025-01-01_2025-12-31/limit_300"
POSTS_JSONL="$RUN_DIR/extract/posts.jsonl"

# 1. Extract
source .venv/bin/activate
python3 subreddit_extract/extract_subreddit.py \
  -s ostomy --start 2025-01-01 --end 2025-12-31 --limit 300 -v

# 2. Thèmes
source .venv-themes/bin/activate
python3 subreddit_themes/classify_subreddit_posts.py -i "$POSTS_JSONL"

# 3. Sentiment
python3 subreddit_scorer/score_subreddit_posts.py -i "$POSTS_JSONL"

# 4. Excel combiné
python3 subreddit_scorer/report_workbook.py --run-dir "$RUN_DIR"

echo "→ Ouvrir : $RUN_DIR/scorer/posts_Corpus_Report.xlsx"
```

---

## Arborescence finale

```
results/ostomy/2025-01-01_2025-12-31/limit_300/
  extract/
    posts.jsonl
    posts.meta.json
  themes/
    posts.themes.jsonl
    posts_Themes_Report.xlsx          (optionnel)
  scorer/
    posts.sentiment.jsonl
    posts_Corpus_Report.xlsx          ← livrable principal
```

---

## Notes méthodo (mémoire)

- Corpus **non exhaustif** (Reddit API, `/new` + `/search`, limite 300).
- Thèmes : zero-shot BART, multi-label, seuil 0.40 — validation manuelle recommandée (~50 posts).
- Sentiment : RoBERTa Twitter, index = P(pos) − P(neg).
- Fichiers sous `results/` **non versionnés Git** — partager l’Excel par Drive / SharePoint.
