# Guide d'utilisation — Taxonomie r/ostomy pour classification BART-MNLI

> Document de référence du **Groupe 40 — B3.6 MSC Immersion communautaire, UNIL 2025-2026**.  
> L'implémentation opérationnelle du pipeline est dans [`subreddit_themes/`](../subreddit_themes/) (`themes_ostomy.yaml`, `classify_subreddit_posts.py`).

**Note :** le titre original mentionne RoBERTa pour le **fine-tuning supervisé** (Option B, hors scope V0). L'Option A zero-shot utilise **`facebook/bart-large-mnli`**, comme notre code.

---

## Ce que contient la taxonomie

Le fichier [`taxonomy_ostomy_roberta.json`](taxonomy_ostomy_roberta.json) (et le YAML opérationnel) contient :

1. **1 filtre préalable (F0)** : pertinence stomie digestive (colostomie, iléostomie)
2. **11 catégories d'intérêt (A1 à D11)** alignées sur le protocole de recherche
3. **1 catégorie crise (CRISIS)** : idéation suicidaire / détresse aiguë (V0 pipeline)
4. Pour chaque catégorie : identifiant, nom, définition, hypothèse NLI, mots-clés et exemples (dans la version complète du groupe)
5. Notes d'implémentation : ordre des étapes, seuils, distribution attendue

---

## Étape 0 — Prérequis techniques

```bash
pip install transformers torch pandas
```

Pour GPU (fortement recommandé) :

```bash
pip install torch --index-url https://download.pytorch.org/whl/cu118
```

Dans ce dépôt, utiliser l'environnement dédié :

```bash
python3 -m venv .venv-themes
source .venv-themes/bin/activate
pip install -r subreddit_themes/requirements.txt
```

---

## Option A — Zero-shot (aucun entraînement)

### Paramètres V0 (implémentés)

| Paramètre | Valeur |
|-----------|--------|
| Modèle | `facebook/bart-large-mnli` |
| Mode | **multi-label** |
| Seuil | **0.40** par label |
| Troncature | **1000 caractères** (title + selftext) |
| Filtre F0 | Tag Excel `label_digestive_relevance = 1` (pas de pré-filtrage pipeline) |
| Crise | Tag `label_crisis_suicidal_ideation` — exclure des stats quantitatives si besoin |

### Commandes (ce dépôt)

```bash
python3 subreddit_themes/classify_subreddit_posts.py \
  -i results/ostomy/.../extract/posts.jsonl

python3 subreddit_themes/report_workbook.py --run-dir results/ostomy/.../limit_N
```

### Sorties

- `themes/posts.themes.jsonl` — scores et labels par post
- `themes/posts.themes.meta.json` — modèle, seuil, catégories
- `themes/posts_Themes_Report.xlsx` — feuilles `Posts_themes`, `Theme_distribution`, `Run_info`

### Format JSONL (par post)

| Champ | Description |
|-------|-------------|
| `theme_scores` | `{ "digestive_relevance": 0.82, "hospital_to_home_transition": 0.55, ... }` |
| `theme_labels` | Liste des `short_name` avec score ≥ seuil |
| `theme_label` | Label au score max (lecture rapide) |
| `theme_score` | Score du label principal |

### Format Excel

Pour chaque catégorie (`short_name`) :

- `score_{short_name}` — float 0–1
- `label_{short_name}` — 1 si score ≥ seuil, 0 sinon

**Filtrage analyste :**

- Corpus digestif : `label_digestive_relevance = 1`
- Exclure posts sensibles : `label_crisis_suicidal_ideation = 0` (ou relecture manuelle)

---

## Option B — Fine-tuning supervisé RoBERTa (hors scope V0)

Principe : annoter ~400 posts manuellement (Label Studio), entraîner `roberta-base` en multi-label. Performances attendues ~88 % F1 vs ~75 % en zero-shot.

Non implémenté dans ce dépôt pour l'instant. RoBERTa est utilisé ici pour le **sentiment** (`subreddit_scorer/`), pas pour les thèmes.

---

## Recherche ciblée pour C9 (priorité recherche)

La catégorie **C9 (transition hôpital–domicile)** est centrale pour la question de recherche mais sous-représentée dans un corpus général.

Termes à chercher dans r/ostomy (via extracteur ou requêtes dédiées) :

- `discharge`, `going home`, `nobody told me`, `community nurse`
- `first week home`, `sent home`, `readmitted`, `abandoned`
- `early discharge`, `ERAS`, `left hospital`

---

## Distribution attendue (indicative, multi-label)

Les pourcentages peuvent se cumuler au-delà de 100 % (un post peut avoir plusieurs labels).

| Catégorie | Part attendue |
|-----------|---------------|
| A1 technical_stoma_care | 30–40 % |
| A2 diet_and_output | 15–25 % |
| A3 access_to_resources | 5–10 % |
| B4 body_image | 10–15 % |
| B5 mental_health | 20–30 % |
| B6 relationships_sexuality | 8–15 % |
| C7 social_stigma | 10–20 % |
| C8 return_to_work | 10–20 % |
| C9 hospital_transition | 5–12 % (sous-représenté) |
| D10 healthcare_experience | 10–20 % |
| D11 peer_support | 20–35 % |

---

## Code de référence (guide original — pseudo-code)

Le snippet ci-dessous illustre l'approche du groupe ; le pipeline de ce dépôt est dans `classify_subreddit_posts.py`.

```python
import json
import pandas as pd
from transformers import pipeline

with open("taxonomy_ostomy_roberta.json", "r") as f:
    taxonomy = json.load(f)

categories = taxonomy["categories"]
classifier = pipeline("zero-shot-classification", model="facebook/bart-large-mnli", device=0)

df = pd.read_csv("ostomy_posts.csv")
df["full_text"] = (df["title"].fillna("") + " " + df["selftext"].fillna("")).str.strip().str[:1000]

working = categories
hypotheses = [c["hypothesis_template"] for c in working]
THRESHOLD = 0.40

for idx, text in enumerate(df["full_text"]):
    result = classifier(text, hypotheses, hypothesis_template="{}", multi_label=True)
    # mapper scores → short_name, appliquer seuil, exporter
```
