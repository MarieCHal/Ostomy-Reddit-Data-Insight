# Commandes — extraction Reddit (`extract_subreddit.py`)

Un **seul script** : [`extract_subreddit.py`](extract_subreddit.py).

## macOS / Homebrew : erreur `externally-managed-environment`

Si `python3 -m pip install -r requirements-extract.txt` refuse d’installer (PEP 668), **ne forcez pas** le Python système : créez un **venv** dans le dépôt (voir ci-dessous), activez-le, puis `pip install` **à l’intérieur**.

## Installation (recommandé : venv)

```bash
cd /chemin/vers/Ostomy-Reddit-Data-Insight
python3 -m venv .venv
source .venv/bin/activate   # Windows : .venv\Scripts\activate
pip install -r requirements-extract.txt
```

Sans le venv activé : `ModuleNotFoundError: No module named 'requests'`.

**Aide intégrée** :

```bash
python3 subreddit_extract/extract_subreddit.py --help
```

## Extraction typique (résultats sous `results/`)

Structure par défaut (étape **extract** seule) :

`results/<subreddit>/<YYYY-MM-DD>_<YYYY-MM-DD>/extract/posts.jsonl` (+ `posts.meta.json`)  
Si `--limit N` avec N > 0 : `.../<plage>/limit_N/extract/posts.jsonl`.

Voir aussi [`results/README.md`](../results/README.md) pour l’arborescence complète (extract + themes).

```bash
python3 subreddit_extract/extract_subreddit.py -s ostomy --start 2025-01-01 --end 2025-01-31
```

Avec plafond de posts et logs détaillés :

```bash
python3 subreddit_extract/extract_subreddit.py -s ostomy --start 2025-01-01 --end 2025-12-31 --limit 500 -v
```

Sortie personnalisée (préfixe sans extension) :

```bash
python3 subreddit_extract/extract_subreddit.py -s ostomy --start 2025-06-01 --end 2025-06-30 \
  --out-prefix ./exports/mon_corpus --no-search
```

## Options utiles

| Option | Rôle |
|--------|------|
| `--no-search` | Désactive la phase `/search` (plus rapide, corpus souvent plus petit). |
| `--search-queries generic` | Force les requêtes `a`–`z` pour `/search`. |
| `--search-queries ostomy` | Force la liste « domaine » (ostomy, stoma, …) pour `/search`. |
| `--sleep SEC` | Pause entre requêtes HTTP (comportement Reddit / 429). |

## Analyse sur les fichiers déjà téléchargés

Le pipeline historique (`ostomy_analyze.py`, etc.) attend un `.jsonl` + `.meta.json`. Vous pouvez réutiliser les fichiers produits par ce script en passant le chemin du `.jsonl` à l’analyseur existant.

## Limites

Voir [VARIANTES_ET_BIAIS.md](../VARIANTES_ET_BIAIS.md) et le [README.md](../README.md) racine : API publique, non exhaustif, `/new` plafonné côté Reddit, etc.
