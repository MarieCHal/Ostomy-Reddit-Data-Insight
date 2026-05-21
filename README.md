# Ostomy Reddit Data Insight

Projet de recherche visant à **collecter et structurer** des données issues de Reddit (en particulier le subreddit **r/ostomy**), puis à les exploiter pour une étude (thématisation, polarité, livrable lisible pour des humains).

Ce dépôt est organisé autour d’un pipeline léger type **ETL** : extraction → traitements analytiques → export (par ex. tableur).

## Objectif métier

1. **Extraire** les soumissions (posts) d’un subreddit cible sur une **plage de dates** donnée, avec possibilité de **limite** sur le nombre de posts, et stocker le brut de façon **reproductible** (fichiers locaux, sans refetch obligatoire pour retravailler les données).
2. **Attribuer** des contenus à des thèmes définis en entrée (p.ex. modèles type **BART** pour classification zero-shot, si l’environnement le permet).
3. **Scorer** le ton positif / négatif (p.ex. **RoBERTa** sentiment, ou autres modèles — le code historique du dépôt utilise aussi des outils type VADER pour une première passe).
4. **Livrer** un **fichier Excel** (ou équivalent) pour une lecture humaine et une exploitation dans un mémoire ou une étude.

**Avertissement** : il ne s’agit pas d’un outil médical ou de conseil en santé ; uniquement d’une analyse de contenus publics en ligne, avec des biais méthodologiques documentés.

## Structure du dépôt (aperçu)

| Élément | Rôle |
|---------|------|
| [`subreddit_extract/extract_subreddit.py`](subreddit_extract/extract_subreddit.py) | **Script** d’extraction autonome (`requests` seul) : logs terminal, sortie sous `results/`. Voir [`subreddit_extract/COMMANDES.md`](subreddit_extract/COMMANDES.md). |
| [`subreddit_themes/`](subreddit_themes/COMMANDES.md) | **Thèmes (BART-MNLI)** : classification zero-shot **multi-label** (taxonomie MSC, 13 catégories, seuil 0.40) sur un `posts.jsonl` extrait → `posts.themes.jsonl` + Excel. Voir [`subreddit_themes/COMMANDES.md`](subreddit_themes/COMMANDES.md) et [`draft_guide_themes/`](draft_guide_themes/). |
| [`subreddit_scorer/`](subreddit_scorer/COMMANDES.md) | **Sentiment (RoBERTa)** : polarité + index −1…+1 sur `posts.jsonl`, sorties `posts.sentiment.jsonl` + rapport Excel corpus. Voir [`subreddit_scorer/COMMANDES.md`](subreddit_scorer/COMMANDES.md). |
| [`reddit_extract.py`](reddit_extract.py), [`ostomy_common.py`](ostomy_common.py) | Pipeline **historique** inchangé : extraction + analyse dans un même module partagé (charge spaCy, NLTK, VADER à l’import). |
| [`ostomy_analyze.py`](ostomy_analyze.py) | Analyse sur JSONL déjà téléchargé (réseau non requis). |
| [`VARIANTES_ET_BIAIS.md`](VARIANTES_ET_BIAIS.md) | Variantes d’extraction, biais, limites Reddit (pagination, exhaustivité, etc.). |
| [`METHODES_ET_TECHNOLOGIES.md`](METHODES_ET_TECHNOLOGIES.md) | Cadrage méthodologique aligné sur le code historique. |

## Démarrage rapide — extraction seule

Sur macOS avec Python **Homebrew**, `python3 -m pip install …` sur le Python système échoue souvent avec **`externally-managed-environment`** (norme PEP 668) : il ne faut pas y installer des paquets à la main. **Créez un environnement virtuel** dans le dépôt, puis installez `requests` dedans :

```bash
cd /chemin/vers/Ostomy-Reddit-Data-Insight
python3 -m venv .venv
source .venv/bin/activate          # Windows : .venv\Scripts\activate
pip install -r requirements-extract.txt
```

Ensuite, toujours avec le venv **activé**, lancez le script depuis la racine du dépôt :

```bash
python3 subreddit_extract/extract_subreddit.py --help
python3 subreddit_extract/extract_subreddit.py -s ostomy --start 2025-01-01 --end 2025-01-31
```

Sans venv, utilisez explicitement le pip du venv : `.venv/bin/pip install -r requirements-extract.txt`, ou appelez le script avec `.venv/bin/python3 subreddit_extract/extract_subreddit.py …`.

Les fichiers sont créés par défaut sous `results/<subreddit>/<date_debut>_<date_fin>/` (voir `--help` pour `--limit`, `--out-prefix`, `--no-search`).

## Étape 2 — thèmes (BART-MNLI), hors pipeline historique

Après extraction, un environnement séparé peut charger PyTorch et le modèle `facebook/bart-large-mnli` :

```bash
python3 -m venv .venv-themes && source .venv-themes/bin/activate
pip install -r subreddit_themes/requirements.txt
python3 subreddit_themes/classify_subreddit_posts.py -i results/.../extract/posts.jsonl
python3 subreddit_themes/report_workbook.py --run-dir results/.../limit_N
```

Détails, options (`--device`, `--threshold`, `--max-chars`, taxonomie YAML) : [`subreddit_themes/COMMANDES.md`](subreddit_themes/COMMANDES.md). Taxonomie de référence : [`draft_guide_themes/taxonomy_ostomy_roberta.md`](draft_guide_themes/taxonomy_ostomy_roberta.md).

## Étape 3 — sentiment (RoBERTa), hors pipeline historique

Après extraction, un environnement PyTorch peut charger le modèle Twitter-RoBERTa sentiment :

```bash
python3 -m venv .venv-scorer && source .venv-scorer/bin/activate
pip install -r subreddit_scorer/requirements.txt
python3 subreddit_scorer/score_subreddit_posts.py -i results/.../extract/posts.jsonl
python3 subreddit_scorer/report_workbook.py --run-dir results/.../limit_N
```

Cadrage (choix du modèle, index de polarité) : [`points_a_clarifier/scorer_sentiment_roberta.md`](points_a_clarifier/scorer_sentiment_roberta.md). Options : [`subreddit_scorer/COMMANDES.md`](subreddit_scorer/COMMANDES.md).

## Dépendances complètes (analyse + Excel comme avant)

```bash
pip install -r requirements.txt
python3 -m spacy download en_core_web_sm
```

## Fichiers produits par l’extracteur moderne

- Sous **`extract/`** : `posts.jsonl`, `posts.meta.json` (étape extraction).
- Sous **`themes/`** (après classification) : `posts.themes.jsonl`, rapport Excel thèmes, etc.
- Sous **`scorer/`** (après sentiment) : `posts.sentiment.jsonl`, rapport Excel corpus, etc.

Arborescence détaillée : [`results/README.md`](results/README.md).

Le dossier `results/` est ignoré par Git (voir [`.gitignore`](.gitignore)) pour éviter de versionner des corpus volumineux ; conservez vos exports localement ou ailleurs selon votre politique de données.
