# Points à clarifier — scorer sentiment RoBERTa (`subreddit_scorer`)

Ce document reprend des questions sur l’**étape scorer** (polarité positive / négative des posts) et le **choix du modèle RoBERTa**. Le code vit dans [`subreddit_scorer/`](../subreddit_scorer/) ; le pipeline historique utilise encore **VADER** dans [`ostomy_common.py`](../ostomy_common.py).

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

## Pourquoi RoBERTa pour cette étude ?

| Critère | VADER (pipeline historique) | RoBERTa fine-tuné (étape `subreddit_scorer`) |
|---------|----------------------------|-----------------------------------------------|
| **Principe** | Lexique + règles (compound −1…+1) | Réseau de neurones, contexte des mots |
| **Forces** | Rapide, léger, explicable, pas de GPU | Mieux sur formulations indirectes, négations, tournures conversationnelles |
| **Faiblesses** | Ironie, jargon, formulations atypiques | Lourd (PyTorch), « boîte noire », biais du jeu d’entraînement |
| **Registre r/ostomy** | Score sur texte brut | Modèle social (Twitter) choisi pour se rapprocher du **fil Reddit** |

**RoBERTa** (Robustly Optimized BERT Pretraining) est retenu ici parce que :

1. **Alignement avec le corpus** : posts Reddit = texte social, souvent court, oral, parfois émotionnel — proche des **tweets** plutôt que d’articles encyclopédiques ou de comptes rendus cliniques formels.
2. **Score continu pour l’analyse** : les probabilités de classes permettent un **index de polarité** exploitable en tableur (voir ci-dessus), en plus du label.
3. **Standard de fait** : modèles Cardiff NLP et SiEBERT largement cités en analyse de sentiment sur texte anglais informel.
4. **Séparation des étapes** : l’extract et le scorer restent reproductibles (JSONL + meta) sans recharger tout le pipeline historique (spaCy, NLTK, etc.).

Ce choix ne remplace pas une **validation humaine** sur un sous-échantillon ; il complète VADER plutôt qu’il ne le rend obsolète pour une section « comparaison / limites » du mémoire.

---

## Choix par défaut retenu : `cardiffnlp/twitter-roberta-base-sentiment-latest`

**Identifiant Hugging Face :** `cardiffnlp/twitter-roberta-base-sentiment-latest`  
(configurable via `--model` dans [`score_subreddit_posts.py`](../subreddit_scorer/score_subreddit_posts.py))

### Justification méthodologique

| Point | Détail |
|-------|--------|
| **Corpus d’entraînement** | Fine-tuning sur des **tweets** anglais (version « latest » : corpus TweetEval / TimeLMs, tweets 2018–2021 — voir fiche HF du modèle). |
| **Proximité Reddit** | Même genre de messages : questions, détresse, humour, abbreviations, mélange registre médical / vécu quotidien. |
| **Classes** | **3 classes** : negative, neutral, positive — utile quand un post est factuel ou ambigu (ex. question technique sans charge émotionnelle forte). |
| **Taille** | **`base`** (~125 M paramètres) : compromis acceptable CPU/MPS pour un mémoire ; pas besoin de `large` en première passe. |
| **Intégration** | Pipeline Hugging Face `sentiment-analysis`, même stack que l’étape thèmes (PyTorch / `transformers`). |
| **Reproductibilité** | Modèle versionné sur HF ; `posts.sentiment.meta.json` enregistre l’id du modèle et la formule d’index. |

### Ce que ce modèle ne garantit pas

- Compréhension **médicale** fine (symptômes, procédures) : il lit du **ton**, pas la véracité clinique.
- Posts **multilingues** (ex. portugais dans le corpus) : entraînement anglais → scores peu fiables.
- **Ironie** communautaire ou détresse minimisée (« I’m fine :) ») : erreurs possibles sur tout modèle sentiment généraliste.

---

## Autres modèles RoBERTa (ou proches) intéressants à essayer

Tous se testent avec la **même commande**, en changeant `--model` (même venv `.venv-scorer` / `.venv-themes`) :

```bash
python3 subreddit_scorer/score_subreddit_posts.py \
  -i results/.../extract/posts.jsonl \
  --model IDENTIFIANT_HF \
  -o results/.../scorer/posts_roberta_siebert   # préfixe distinct pour ne pas écraser le run par défaut
```

Comparer ensuite les colonnes `sentiment_label` et `sentiment_polarity_index` sur 20–30 posts lus manuellement (Excel corpus ou JSONL).

### Tableau des alternatives

| Modèle Hugging Face | Taille | Classes | Entraînement / public | Intérêt pour r/ostomy | Limite principale |
|---------------------|--------|---------|------------------------|------------------------|-------------------|
| **`cardiffnlp/twitter-roberta-base-sentiment-latest`** *(défaut)* | base | neg / neu / pos | Tweets récents (TweetEval) | Meilleur défaut « social » | Pas neutre clinique |
| `cardiffnlp/twitter-roberta-base-sentiment` | base | neg / neu / pos | Tweets (~58 M), version antérieure | Comparer avec « latest » (évolution temporelle du modèle) | Corpus tweets plus ancien |
| `cardiffnlp/roberta-base-tweet-sentiment-en` | base | 3 classes | Tweets (Cardiff NLP) | Variante tweet ; utile si résultats discordants avec `latest` | Même famille, redondant sauf pour robustesse |
| `siebert/sentiment-roberta-large-english` | **large** | **pos / neg** (binaire) | 15 jeux de données variés (avis, tweets, etc.) | Bonne **généralisation** multi-sources ; opinions explicites | Pas de classe *neutral* ; plus lent et plus de RAM |
| `j-hartmann/emotion-english-distilroberta-base` | distil | joie, colère, peur… | Émotions fines | Si l’hypothèse devient « émotion » et non polarité | **Pas** un score pos/neg ; autre question de recherche |
| Modèles « clinical » (ex. BioClinicalBERT fine-tunés) | variable | variable | Notes / littérature médicale | Corpus très technique hospitalier | Reddit = trop de vécu perso / humour pour être le défaut |

### Hors RoBERTa mais utiles en comparaison (mémoire)

| Outil | Type | Quand l’envisager |
|-------|------|------------------|
| **VADER** ([`ostomy_common.py`](../ostomy_common.py)) | Lexique, compound −1…+1 | Référence historique du dépôt ; rapide ; section « accord / désaccord » avec RoBERTa |
| `nlptown/bert-base-multilingual-uncased-sentiment` | BERT multilingue, 1–5 étoiles | Si beaucoup de posts **non anglais** ; autre échelle (à recoder en polarité) |

### Binaire vs 3 classes et index de polarité

- Avec **3 classes** (défaut Cardiff) : `sentiment_polarity_index = P(positive) − P(negative)` ; le *neutral* réduit les deux probas → index proche de 0.
- Avec **binaire** (ex. SiEBERT) : seules `positive` et `negative` dans `sentiment_scores` ; la formule reste valide ; pas de troisième classe pour les questions factuelles.

Documenter dans le mémoire **quel modèle** a servi au corpus final ; si tu en testes plusieurs, garder des préfixes de sortie distincts (`-o …/scorer/posts_siebert`).

---

## Synthèse pour le rapport / mémoire

**Choix retenu :** RoBERTa fine-tuné sur tweets (`cardiffnlp/twitter-roberta-base-sentiment-latest`), car le registre des posts Reddit (social, conversationnel, parfois médical mais non clinique) est plus proche de ce corpus que d’un modèle purement hospitalier ou lexicographique.

**Pistes de robustesse** (optionnel) : répliquer sur `siebert/sentiment-roberta-large-english` ou comparer avec VADER sur un même sous-échantillon annoté grossièrement à la main.

---

## Phrases types pour le mémoire

**Choix du modèle :**

> La polarité est estimée par un classifieur RoBERTa (architecture transformer) fine-tuné sur un corpus de tweets anglais (`cardiffnlp/twitter-roberta-base-sentiment-latest`), choisi pour sa proximité avec le registre conversationnel des posts Reddit, par opposition à un modèle exclusivement clinique ou à une approche purement lexicale (VADER).

**Score continu :**

> Pour chaque post, nous conservons la classe dominante (negative / neutral / positive) et un indice de polarité `P(positive) − P(negative)` sur [−1, +1], distinct du score compound VADER du pipeline historique ; les deux approches ne sont pas présentées comme équivalentes sans analyse comparative sur un sous-échantillon.

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
