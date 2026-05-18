# Points à clarifier — scorer sentiment RoBERTa (`subreddit_scorer`)

Ce document reprend des questions sur l’**étape scorer** (polarité positive / négative des posts) et le choix du modèle. Le code cible vit dans [`subreddit_scorer/`](../subreddit_scorer/) (à créer) ; le pipeline historique utilise encore **VADER** dans [`ostomy_common.py`](../ostomy_common.py).

---

## Objectif : un score « plus ou moins positif »

Pour l’étude, l’intérêt principal n’est pas seulement d’étiqueter un post en *negative* / *neutral* / *positive*, mais d’obtenir une **valeur numérique** utilisable dans Excel ou des graphiques : « ce post est plutôt négatif (−0,6) ou plutôt positif (+0,4) ».

**Deux niveaux complémentaires :**

| Sortie | Rôle |
|--------|------|
| **Label** (`sentiment_label`) | Classe dominante — lecture humaine rapide |
| **Probabilités** (`sentiment_scores`) | Confiance par classe — détail méthodologique |
| **Index de polarité** (`sentiment_polarity_index`) | Score **continu entre −1 et +1**, dérivé des probas |

**Formule retenue pour l’index :**

```text
sentiment_polarity_index = P(positive) − P(negative)
```

- Proche de **+1** → plutôt positif ; proche de **−1** → plutôt négatif ; proche de **0** → neutre ou mixte (souvent quand *neutral* est fort).
- Ce n’est **pas** le score **compound** de VADER : même échelle (−1…+1), mais calcul et biais différents. Pour le mémoire, ne pas les présenter comme interchangeables sans comparaison sur un sous-échantillon.

Posts sans texte (`title` + `selftext` vides) : pas d’appel au modèle ; index et label à `null`, avec une note explicite (`empty_text`).

---

## Pourquoi y a-t-il plusieurs modèles « RoBERTa » sur Hugging Face ?

**RoBERTa** désigne une **architecture** (famille de transformeurs), pas un fichier unique.

Chaque dépôt sur Hugging Face correspond en général à :

1. Un **pré-entraînement** sur un grand corpus (souvent anglais général).
2. Un **fine-tuning** sur une **tâche** précise (sentiment, émotions, Q&A…).
3. Un **jeu de données** métier (Twitter, avis clients, films, texte clinique…).
4. Parfois une **taille** différente (`base` vs `large`).

Il n’existe donc pas « le » meilleur RoBERTa en absolu, mais celui le plus **aligné** avec le type de texte (ici : posts Reddit, registre social, parfois ironique ou médical mélangé au quotidien).

---

## Comment choisir un modèle pour r/ostomy ?

Checklist simple :

1. **Tâche** : polarité (négatif / neutre / positif) → pipeline `sentiment-analysis`, pas un modèle « émotions fines » sauf si l’hypothèse de recherche change.
2. **Genre de texte** : Reddit ≈ texte social court → modèles entraînés sur **Twitter** ou réseaux sociaux plutôt que sur Wikipedia seul ou des comptes rendus hospitaliers purs.
3. **Ressources machine** : `base` suffit en général pour un mémoire ; `large` est plus lourd (RAM, temps CPU/GPU).
4. **Validation qualitative** : lire 20–30 posts classés à la main (tristesse, humour, ironie, jargon médical) avant de figer le choix dans le rapport.

### Choix par défaut retenu pour ce dépôt

**`cardiffnlp/twitter-roberta-base-sentiment-latest`**

- Fine-tuné sur du texte type **Twitter** (proche de Reddit).
- Trois classes : negative, neutral, positive.
- Bien documenté, intégration simple via `transformers`.

**Alternatives possibles** (hors scope initial, utiles pour une section « limites ») :

| Modèle (exemple) | Entraînement typique | Intérêt / limite |
|------------------|----------------------|------------------|
| `siebert/sentiment-roberta-large-english` | avis / opinions | Parfois meilleur sur opinions explicites ; plus lourd |
| Modèles « clinical » | texte médical | Pertinent si le corpus est très clinique ; Reddit mélange vécu, humour, quotidien |
| **VADER** (lexique) | règles + lexique | Rapide, explicable ; moins sensible au contexte que RoBERTa |

---

## Que retenir pour le mémoire (phrase type)

> Nous utilisons un classifieur RoBERTa fine-tuné sur du texte social court (Twitter), proche du registre Reddit. Nous enregistrons la classe dominante et un indice de polarité `P(positive) − P(negative)` sur l’échelle [−1, +1], distinct du score compound VADER utilisé dans le pipeline historique du dépôt.

---

## Limites et biais à mentionner

- **Domaine** : le modèle n’a pas été entraîné spécifiquement sur ostomy / stoma ; même prudence que pour VADER (voir [`VARIANTES_ET_BIAIS.md`](../VARIANTES_ET_BIAIS.md)).
- **Troncature** : textes très longs sont coupés à la limite du tokenizer (~512 tokens) — le score ne porte que sur le début du post.
- **Ironie / sarcasme** : erreurs fréquentes sur les modèles sentiment généralistes.
- **Anglais** : corpus et modèle en anglais ; posts multilingues mal couverts.

---

## Validation recommandée avant de figer le protocole

1. Lancer le scorer sur un petit run (`--limit 20` ou 30).
2. Ouvrir le rapport Excel sous `scorer/` (ou le JSONL) et comparer **texte ↔ label ↔ `sentiment_polarity_index`**.
3. Noter les cas systématiquement faux (ironie, détresse masquée, humour communautaire).
4. *(Optionnel)* Comparer quelques lignes avec **VADER** du pipeline historique sur les **mêmes** posts.

---

## Liens

- Plan d’implémentation : étape `subreddit_scorer/` (package autonome, entrée `extract/posts.jsonl`, sortie `scorer/posts.sentiment.jsonl`).
- Arborescence des runs : [`results/README.md`](../results/README.md).
- Commandes (une fois le package créé) : [`subreddit_scorer/COMMANDES.md`](../subreddit_scorer/COMMANDES.md).
