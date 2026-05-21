# Thèmes BART-MNLI (`subreddit_themes/`)

Étape distincte de l’extraction ([`subreddit_extract/`](../subreddit_extract/COMMANDES.md)) : classification **zero-shot multi-label** avec **`facebook/bart-large-mnli`**, taxonomie MSC (13 catégories), puis rapport Excel.

Taxonomie de référence : [`draft_guide_themes/taxonomy_ostomy_roberta.md`](../draft_guide_themes/taxonomy_ostomy_roberta.md)

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

- `themes/posts.themes.jsonl` — une ligne par post avec `theme_labels`, `theme_scores`, `theme_label` (top-1).
- `themes/posts.themes.meta.json` — modèle, seuil, troncature, liste des catégories.

Options utiles :

| Option | Description |
|--------|-------------|
| `--themes PATH` | Fichier YAML des catégories (défaut : `subreddit_themes/themes_ostomy.yaml`). |
| `--threshold FLOAT` | Seuil par label (défaut : 0.40 depuis le YAML). |
| `--max-chars N` | Troncature title+body (défaut : 1000 depuis le YAML). |
| `--device auto\|cpu\|cuda\|mps` | Accélérateur (`auto` teste CUDA puis MPS puis CPU). |
| `--limit N` | Ne traiter que les N premiers posts (tests). |
| `-o PREFIX` | Préfixe sans extension pour les fichiers `.themes.jsonl` / `.themes.meta.json`. |

## 2. Rapport Excel

Après classification :

```bash
python3 subreddit_themes/report_workbook.py \
  --run-dir results/ostomy/2026-01-01_2026-05-14/limit_10
```

Sorties par défaut sous **`themes/`** :

- `themes/posts_Themes_Report.xlsx` — feuilles `Posts_themes`, `Theme_distribution`, `Run_info`.
- `themes/posts_Themes_Report.report_meta.json` — métadonnées posts + thèmes.

### Colonnes Excel

Pour chaque catégorie (`short_name`, ex. `hospital_to_home_transition`) :

- `score_{short_name}` — score brut 0–1
- `label_{short_name}` — 1 si score ≥ seuil, 0 sinon

**Filtrage analyste (V0) :**

- Corpus stomie digestive : `label_digestive_relevance = 1`
- Posts sensibles : repérer `label_crisis_suicidal_ideation = 1` ; exclure des stats quantitatives ou relire manuellement

La feuille `Theme_distribution` compte les posts par label (multi-label : la somme des % peut dépasser 100 %).

## Fichier des catégories

Éditer [`themes_ostomy.yaml`](themes_ostomy.yaml) : 13 catégories avec `hypothesis`, `keywords`, `examples` (doc), `definition`.

**Version 3** : les `keywords` enrichissent l'hypothèse NLI et appliquent un léger boost de score (+0,03 par mot-clé trouvé, plafond +0,12). F0 pénalise les `exclusion_signals` (urostomie, pub…). Les `examples` servent à la relecture humaine, pas au modèle directement.

Pour **reclassifier** après modification du YAML, relancer `classify_subreddit_posts.py` sur le même `posts.jsonl`.
