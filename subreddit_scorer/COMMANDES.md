# Scorer sentiment RoBERTa (`subreddit_scorer/`)

Étape distincte de l’extraction ([`subreddit_extract/`](../subreddit_extract/COMMANDES.md)) et des thèmes ([`subreddit_themes/`](../subreddit_themes/COMMANDES.md)) : **sentiment** avec **`cardiffnlp/twitter-roberta-base-sentiment-latest`**, puis rapport Excel corpus (posts + sentiment + thèmes si disponibles).

Cadrage méthodo (choix RoBERTa, alternatives à tester, phrases pour le mémoire) : [`points_a_clarifier/scorer_sentiment_roberta.md`](../points_a_clarifier/scorer_sentiment_roberta.md).

## Environnement

Depuis la racine du dépôt :

```bash
python3 -m venv .venv-scorer
source .venv-scorer/bin/activate
pip install -r subreddit_scorer/requirements.txt
```

Vous pouvez réutiliser **`.venv-themes`** si déjà créé (mêmes dépendances PyTorch / transformers).

Le premier lancement télécharge le modèle (~500 Mo). Prévoir du temps en **CPU** ; **CUDA** ou **MPS** (Apple Silicon) accélère si disponible.

## 1. Scorer les posts

Entrée : un `posts.jsonl` produit par l’extracteur.

```bash
python3 subreddit_scorer/score_subreddit_posts.py \
  -i results/ostomy/2026-01-01_2026-05-14/limit_10/extract/posts.jsonl
```

Sorties dans le sous-dossier **`scorer/`** du même run (si l’entrée est sous `extract/`) :

- `scorer/posts.sentiment.jsonl` — `sentiment_label`, `sentiment_score`, `sentiment_scores`, `sentiment_polarity_index`
- `scorer/posts.sentiment.meta.json` — modèle, formule d’index, instant UTC, etc.

**Index de polarité** (échelle −1…+1) : `sentiment_polarity_index = P(positive) − P(negative)`.

Options utiles :

| Option | Description |
|--------|-------------|
| `--model ID` | Modèle Hugging Face (défaut : `cardiffnlp/twitter-roberta-base-sentiment-latest`). Autres idées : voir le tableau dans `points_a_clarifier/scorer_sentiment_roberta.md`. |
| `--device auto\|cpu\|cuda\|mps` | Accélérateur. |
| `--batch-size N` | Taille de lot (défaut : 8). |
| `--limit N` | Ne traiter que les N premiers posts (tests). |
| `-o PREFIX` | Préfixe sans extension pour `.sentiment.jsonl` / `.sentiment.meta.json`. |

**Troncature** : les textes très longs sont coupés au `max_length` du tokenizer (~512 tokens).

## 2. Rapport Excel corpus

Après scoring (idéalement aussi après thèmes, mais pas obligatoire pour scorer) :

```bash
python3 subreddit_scorer/report_workbook.py \
  --run-dir results/ostomy/2026-01-01_2026-05-14/limit_10
```

Si `themes/posts.themes.jsonl` existe, les colonnes thème sont remplies ; sinon elles restent vides.

Sorties par défaut sous **`scorer/`** :

- `scorer/posts_Corpus_Report.xlsx` — feuilles `Posts_corpus`, `Sentiment_distribution`, `Theme_distribution` (si thèmes), `Run_info`
- `scorer/posts_Corpus_Report.report_meta.json`

Le rapport **thèmes seuls** reste produit par [`subreddit_themes/report_workbook.py`](../subreddit_themes/report_workbook.py) sous `themes/`.

## Ordre des étapes

`extract` → puis **`themes` et/ou `scorer` en parallèle** (les deux lisent `extract/posts.jsonl`) → rapport corpus scorer.
