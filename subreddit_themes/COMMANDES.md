# Thèmes BART-MNLI (`subreddit_themes/`)

Étape distincte de l’extraction ([`subreddit_extract/`](../subreddit_extract/COMMANDES.md)) : classification **zero-shot** avec **`facebook/bart-large-mnli`**, puis rapport Excel allégé.

## Environnement

Depuis la racine du dépôt :

```bash
python3 -m venv .venv-themes
source .venv-themes/bin/activate
pip install -r subreddit_themes/requirements.txt
```

Le premier lancement télécharge le modèle (ordre de grandeur ~1,6 Go). Prévoir du temps en **CPU** ; **CUDA** ou **MPS** (Apple Silicon) accélère si disponible.

## 1. Classifier les posts

Entrée : un `posts.jsonl` produit par l’extracteur (même dossier que `posts.meta.json`).

```bash
python3 subreddit_themes/classify_subreddit_posts.py \
  -i results/ostomy/2026-01-01_2026-05-14/limit_10/extract/posts.jsonl
```

Sorties dans le sous-dossier **`themes/`** du même run (créé automatiquement si l’entrée est sous `extract/`) :

- `themes/posts.themes.jsonl` — une ligne par post avec `theme_label`, `theme_score`, `theme_scores`.
- `themes/posts.themes.meta.json` — modèle, liste des labels, instant UTC, etc.

Options utiles :

| Option | Description |
|--------|-------------|
| `--themes PATH` | Fichier YAML des sujets (défaut : `subreddit_themes/themes_ostomy.yaml`). |
| `--device auto\|cpu\|cuda\|mps` | Accélérateur (`auto` teste CUDA puis MPS puis CPU). |
| `--limit N` | Ne traiter que les N premiers posts (tests). |
| `-o PREFIX` | Préfixe sans extension pour les fichiers `.themes.jsonl` / `.themes.meta.json`. |

## 2. Rapport Excel

Après classification :

```bash
python3 subreddit_themes/report_workbook.py \
  --run-dir results/ostomy/2026-01-01_2026-05-14/limit_10
```

Équivalent explicite :

```bash
python3 subreddit_themes/report_workbook.py \
  -i results/ostomy/2026-01-01_2026-05-14/limit_10/extract/posts.jsonl \
  -t results/ostomy/2026-01-01_2026-05-14/limit_10/themes/posts.themes.jsonl
```

Sorties par défaut sous **`themes/`** :

- `themes/posts_Themes_Report.xlsx` — feuilles `Posts_themes`, `Theme_distribution`, `Run_info`.
- `themes/posts_Themes_Report.report_meta.json` — métadonnées posts + thèmes.

Option `-o chemin/rapport.xlsx` pour fixer le fichier Excel.

## Fichier des sujets

Éditer [`themes_ostomy.yaml`](themes_ostomy.yaml) : clé `labels` (liste de chaînes **en anglais**), option `hypothesis_template` (placeholders `{}` pour le label).
