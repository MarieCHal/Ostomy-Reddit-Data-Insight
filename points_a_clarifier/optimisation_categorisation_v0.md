# Optimisation de la catégorisation thématique — V0 (sans fine-tuning)

Notes pour améliorer la qualité des labels **sans entraîner un modèle** (fine-tuning RoBERTa = hors scope bachelor).

**Pipeline actuel :** BART-MNLI zero-shot, multi-label, seuil 0,40, 1000 caractères max.  
**Fichiers clés :** `subreddit_themes/themes_ostomy.yaml`, `classify_subreddit_posts.py`, `themes_config.py`

---

## Ce qui influence déjà les labels

| Levier | Fichier | Effet |
|--------|---------|-------|
| Phrase NLI par catégorie | `hypothesis` | Signal principal BART |
| Mots-clés dans l'hypothèse | `keywords` (10 max) | Enrichit la phrase envoyée à BART |
| Boost si mot présent dans le post | `keywords` | +0,03 par match, plafond +0,12 |
| Pénalité F0 | `exclusion_signals` | −0,35 sur `digestive_relevance` |
| Seuil binaire | `threshold: 0.4` | Détermine `label_* = 1` ou `0` |
| Longueur du texte | `max_text_chars: 1000` | Troncature avant classification |

**Non utilisés par le classifieur (doc / relecture seulement) :** `definition`, `examples`, `display_name`, `short_name`, `id`.

---

## Piste 1 — Affiner le YAML (effort faible, impact moyen)

### Hypothèses (`hypothesis`)

- Rédiger une phrase **courte, concrète, en anglais** (langue des posts Reddit).
- Décrire **ce que le post parle**, pas le code MSC (ex. A1, C9).
- Éviter les chevauchements : si deux catégories partagent les mêmes mots, BART les confondra.
- Catégories souvent difficiles en zero-shot : **C9** (transition hôpital-domicile), **A3** (accès ressources), **C7** (stigmatisation).

**Action :** relire ~20 posts mal classés par catégorie → reformuler l'hypothèse de la catégorie concernée.

### Mots-clés (`keywords`)

- Reprendre le **vocabulaire réel** des posts (pas seulement le guide MSC).
- Ajouter les **variantes orthographiques** :
  - `follow-up` **et** `follow up`
  - `post-op` **et** `post op`
  - `high-output` **et** `high output`
- Expressions multi-mots utiles : `nobody told me`, `sent home`, `bag change`.
- Ne pas surcharger : 10–20 mots-clés pertinents > 50 mots génériques.

### Signaux d'exclusion F0 (`exclusion_signals`)

- Utile pour exclure urostomie, vente de matériel, hors-sujet.
- Compléter si des faux positifs F0 apparaissent à la relecture Excel.

---

## Piste 2 — Ajuster le seuil (effort minimal)

Le seuil 0,40 est un compromis du guide MSC, pas une vérité absolue.

| Seuil | Effet |
|-------|-------|
| **Plus bas** (ex. 0,35) | Plus de labels par post, plus de rappel, plus de bruit |
| **Plus haut** (ex. 0,45–0,50) | Moins de labels, plus de précision, risque de posts « vides » |

**Action :**

1. Exporter un échantillon de ~30 posts avec les `score_*`.
2. Noter à la main si chaque catégorie devrait être 1 ou 0.
3. Tester `--threshold 0.35`, `0.40`, `0.45` sur le même échantillon.
4. Choisir le seuil global **ou** documenter qu'un seuil différent par catégorie serait souhaitable (V1).

```bash
python3 subreddit_themes/classify_subreddit_posts.py \
  -i "$RUN_DIR/extract/posts.jsonl" \
  --threshold 0.45
```

---

## Piste 3 — Relecture manuelle ciblée (effort moyen, sans entraînement)

Ce n'est **pas** du fine-tuning : c'est du contrôle qualité pour le mémoire.

1. Tirer **30–50 posts** au hasard dans l'Excel corpus.
2. Pour chaque post : valider / corriger les labels (oui/non par catégorie).
3. Calculer un taux d'accord approximatif par catégorie.
4. Documenter les **patterns d'erreur** → retour vers Piste 1 (YAML).

Colonnes utiles dans Excel : `label_*`, `score_*`, texte complet du post.

**Livrable bachelor :** « validation manuelle sur N posts, précision estimée ~X % sur la catégorie Y ».

---

## Piste 4 — Similarité sémantique avec les `examples` (effort moyen, code à ajouter)

Alternative au fine-tuning : utiliser les `examples` du YAML comme **références**, pas comme données d'entraînement.

**Principe :**

1. Encoder le post + les examples avec un modèle d'embeddings (`sentence-transformers`, ex. `all-MiniLM-L6-v2`).
2. Par catégorie : score = similarité moyenne (ou max) post ↔ examples.
3. Combiner avec BART :  
   `score_final = 0.7 × score_BART + 0.3 × score_examples`

**Avantages :** les examples du guide servent enfin ; pas d'annotation massive.  
**Limites :** examples artificiels ; dev supplémentaire ; temps de run un peu plus long.

**Priorité :** seulement si la Piste 1 ne suffit pas sur C9 ou une catégorie problématique.

---

## Piste 5 — Performance / batch (effort faible)

Classification lente sur gros corpus (CPU surtout).

- Traiter par **batch** (plusieurs posts à la fois) si le script le permet ou en l'ajoutant.
- Limiter le sample (`limit_100` vs `limit_300`) pour les itérations de test.
- GPU / MPS si disponible (`--device cuda` ou `mps`).
- Ne relancer le classifieur **qu'après** modification du YAML, pas à chaque étape du pipeline.

---

## Piste 6 — Autres modèles zero-shot (effort moyen, expérimental)

Remplacer `facebook/bart-large-mnli` par un autre modèle NLI zero-shot, sans fine-tuning :

| Modèle | Intérêt |
|--------|---------|
| `MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7` | Meilleur sur texte multilingue |
| `cross-encoder/nli-deberta-v3-base` | Parfois plus précis, plus lent |
| Modèles NLI plus récents sur Hugging Face | À tester sur le même échantillon de 30 posts |

**Méthode :** même YAML, même posts, comparer les désaccords entre modèles + relecture humaine.

**Note mémoire :** « BART-MNLI retenu pour V0 ; alternative X testée sur N posts, résultats comparables / légèrement meilleurs sur Y ».

---

## Piste 7 — Règles post-classification (effort faible)

Heuristiques **après** BART, dans le code ou via filtres Excel :

- Si `exclusion_signals` détectés → forcer `label_digestive_relevance = 0`.
- Si score crise > 0,5 → flag prioritaire pour relecture (déjà taggé `crisis_suicidal_ideation`).
- Posts très courts (< 50 caractères) → exclure ou marquer `low_confidence`.
- Filtrer les posts non anglais si bruit (optionnel, détection langue).

---

## Piste 8 — Longueur du texte (`max_text_chars`)

- **1000 caractères** : bon compromis vitesse / contexte.
- Posts longs : le début contient souvent le sujet principal ; la fin = commentaires implicites.
- Test : `--max-chars 1500` sur posts mal classés où le sujet arrive tard.

---

## Ce qui n'est PAS dans le scope bachelor (rappel)

| Approche | Pourquoi hors scope |
|----------|---------------------|
| Fine-tuning RoBERTa | Nécessite ~80–400 posts annotés à la main + infra entraînement |
| Few-shot massif dans l'hypothèse | Limite tokens, instable |
| Label Studio + jeu d'entraînement | Projet annotation à part entière |

Les `examples` du YAML **ne remplacent pas** l'annotation sur vrais posts Reddit tant qu'il n'y a pas de fine-tuning ou de Piste 4 (embeddings).

---

## Ordre de priorité recommandé

1. **Relecture Excel** sur 30 posts → identifier 2–3 catégories problématiques.
2. **Ajuster `hypothesis` + `keywords`** pour ces catégories.
3. **Tester le seuil** (0,35 / 0,40 / 0,45) sur le même échantillon.
4. **Variantes de mots-clés** (tirets, espaces).
5. **Batch / device** si la lenteur bloque les itérations.
6. **Autre modèle zero-shot** ou **embeddings + examples** seulement si le temps le permet.

---

## Commandes utiles

```bash
RUN_DIR="results/ostomy/2025-01-01_2025-12-31/limit_100"

# Re-classifier après modification du YAML
python3 subreddit_themes/classify_subreddit_posts.py -i "$RUN_DIR/extract/posts.jsonl"

# Seuil personnalisé
python3 subreddit_themes/classify_subreddit_posts.py \
  -i "$RUN_DIR/extract/posts.jsonl" \
  --threshold 0.45

# Regénérer l'Excel corpus (thèmes + sentiment)
python3 subreddit_scorer/report_workbook.py --run-dir "$RUN_DIR"
```

---

## Références internes

- Taxonomie : `subreddit_themes/themes_ostomy.yaml`
- Guide MSC : `draft_guide_themes/guide_utilisation_taxonomie_ostomy.md`
- Marche à suivre pipeline : `points_a_clarifier/marche_a_suivre_sample_300_2025.md`
- Checklist groupe : `points_a_clarifier/a_checker_enemble.md`
