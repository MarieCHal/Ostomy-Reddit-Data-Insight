# Variantes d’extraction, biais et alternatives méthodologiques

Document de cadrage pour le projet **OstomyRedditDataInsight** (Bachelor, analyse de r/ostomy). Compléter par les choix retenus dans le mémoire.

## Workflow en deux scripts (recommandé)

- **`reddit_extract.py`** : uniquement des requêtes vers Reddit ; produit un **`.jsonl`** (un post par ligne) et un **`.meta.json`** (période, nombre de requêtes, etc.). Aucun spaCy / VADER.
- **`ostomy_analyze.py`** : lit le `.jsonl` (+ `.meta.json` du même nom) **sans réseau** ; produit les Excel d’analyse.
- **`ostomy_reddit_data_insight.py`** : raccourci qui enchaîne extraction + analyse (comportement historique “une commande”).

Fichiers bruts : par défaut préfixe `data_brutes/ostomy` → `ostomy.jsonl` + `ostomy.meta.json`. Utiliser un préfixe explicite par corpus, ex. `-o data_brutes/ostomy_2025`.

## Endpoints de tri (JSON public `.json`, sans clé API)

| Variante | Description | Avantages | Biais / limites |
|----------|-------------|-----------|-----------------|
| **`new`** (implémenté par défaut) | Posts en ordre **antichronologique** (les plus récents d’abord). Filtre **période** (ex. année 2025) appliqué **côté client** sur `created_utc`. | Corpus calé sur une **fenêtre temporelle** claire (ex. toute l’année 2025) ; reproductible si on enregistre la date d’extraction. | N’alimente pas un classement de **popularity** : un post rarement upvoté compte autant qu’un autre, du moment qu’il est dans la période. Le tri `new` remonte l’histoire : il faut **paginer** jusqu’à sortir de l’année cible. |
| **`hot`** (variante possible) | Posts actuellement **mis en avant** par l’algorithme « chaud » de Reddit. | Met en avant ce que la **communauté consulte/engage** en ce moment. | Algorithme **non transparent** ; mélange récence et engagement. **Incompatible** avec une période fixe (ex. seule l’année 2025) de façon stable : l’échantillon est **dynamique** et change si on relance le script. |
| **`top`** (variante possible) | Posts classés par **score (votes)**, souvent avec `t=day|week|month|year|all`. | Met l’accent sur l’**approbation** des votes ; l’échantillon se compare mieux sur « sujets notables ». | **Sous-représentation** des posts faiblement notés (questions isolées, nouveaux comptes) ; période dépend de `t` côté Reddit, pas d’un filtre arbitraire post par post. |

**Synthèse** : pour un **câdre temporel** (ex. année 2025) et un traitement reproductible, **`new` + filtre `created_utc`** est l’option la plus directe. `hot` / `top` répondent à d’**autres questions de recherche** (visibilité, consensus), pas à la même.

## Filtre par période (ex. 2025)

- **Avantage** : cadre temporel explicite pour le mémoire, comparabilité des analyses (VADER, fréquence lexicale) sur le même type de débit discursif.
- **Limite** : si l’activité du sub varie, la **taille n** n’est **pas** contrôlée a priori (beaucoup ou peu de fils en 2025). Noter le **n obtenu** et la **date d’extraction** dans le rapport.
- **Reproductibilité** : l’API JSON ne fournit pas un export « toutes les publications 2025 en une requête » : la collecte repose sur la **pagination** ; une nouvelle exécution en 2026 récupère la même période **si** l’URL et les bornes UTC sont identiques, mais l’infrastructure Reddit peut évoluer (rate limit, etc.). Le script insère des **pauses** entre requêtes et une **reprise** si Reddit répond `429 Too Many Requests` (pause longue puis nouvelle tentative).

## Limitation technique critique : flux `/new` et année calendaire

- Sur l’URL publique `…/r/…/new.json`, Reddit n’autorise en pratique qu’une **profondeur d’environ 1000 posts** (pagination avec `after` puis plus de page). Les posts sont retournés du **plus récent au plus ancien**.
- Si le sub est actif, ces ~1000 entrées peuvent **toutes** être **postérieures** à l’année visée (ex. fin 2025 / 2026 alors que vous ciblez 2025) : le filtre par date retourne alors **0 post**, sans qu’il y ait un bug de code.
- **Stratégie implémentée** (toujours sur des **endpoints** `*.json` de **reddit.com**) : en plus du prélèvement `new`, le script enchaîne des requêtes **`/r/ostomy/search.json`** avec une **liste de requêtes** (caractères + mots outils) et **dédoublonne par `id`**, afin d’**élargir** le réservoir de posts visibles côté moteur de recherche du sous-forum. Cela ne garantit **pas** l’exhaustivité, mais améliore le recouvrement d’une **année passée** par rapport au seul `new`.
- Pour un recueil **exhaustif** ou très volumineux, seuls des **moyens** en dehors du MVP (API OAuth, dumps tiers, saisie manuelle) sont réalistes — à cadrer en méthodologie.

## Sentiment : VADER

- **Rôle** : le script utilise **VADER** (`vaderSentiment`) sur le texte **brut** (titre + message) et enregistre le score **compound** (global).
- **Positionnement** : VADER est **défendu** en analyse de texte **socio-numérique** (lexique + règles) à condition d’en **discuter les limites** dans le mémoire (santé, **ironie**, négations complexes, biais du lexique **anglais** généraliste).
- **Pistes d’**approfondissement** (hors MVP) : (1) **annotation** manuelle d’un sous-échantillon (référence qualitative / inter-annotateurs) ; (2) autre outil de polarité (comparaison sur un **même** sous-ensemble) ; (3) modèles **contextuels** (Transformers) si ressources et compétences disponibles, avec prudence sur la **généralisation** au domaine stoma/ostomie.

## « Thèmes » : fréquence lexicale (Top 100 lemmes)

- Le script dénombre les **lemmes** (après nettoyage + stopwords NLTK) : cela **ne** vaut **pas** pour un modèle de thèmes latents (LDA, NMF, BERT topic). C’est un **MVP** cohérent pour un **Bachelor** ; le mémoire peut le présenter comme **exploration lexicale** plutôt que « détection de thèmes » au sens sémantique.

## Rappel éthique

- Contenu issu d’un subreddit **public** ; citer la **source** (Reddit, r/ostomy) et la finalité (recherche, Bachelor). **Ne pas** réidentifier les personnes ; l’**identifiant de post** sert plutôt à l’**audit** et à l’**alignement** avec l’export.
