# Méthodes et technologies — Projet **OstomyRedditDataInsight**

Document de cadrage pour un tiers (recherche, reprise possible). Aligné sur le code du dépôt (scripts `reddit_extract.py`, `ostomy_analyze.py`, `ostomy_common.py`).

---

## 0. Architecture du pipeline

| Phase | Fichier(s) | Réseau |
|-------|------------|--------|
| Extraction seule | `reddit_extract.py` | Oui (Reddit) |
| Analyse seule (sur données déjà téléchargées) | `ostomy_analyze.py` | Non |
| Tout d’un coup (raccourci) | `ostomy_reddit_data_insight.py` | Oui puis local |

L’extraction enregistre un **fichier texte structuré** (JSON Lines, une ligne = un post) + un **fichier métadonnées** (`.meta.json`) : cela permet de refaire l’analyse (NLP, Excel) **sans** relancer la collecte.

**Terme technique** : pipeline ETL (Extract–Transform–Load) léger ; séparation *extract* / *load analytique*.

---

## 1. Collecte des données

**Termes / concepts à chercher** : Web API consumption, non-authenticated HTTP access, public JSON feed, throttling, pagination, *rate limiting*.

**Outils / méthodes (réalité du projet)**  
- Langage : **Python 3**  
- Librairie **requests** : requêtes HTTP `GET` vers les **points de terminaison publics** `https://www.reddit.com/r/ostomy/...` avec suffixe **`.json`**.  
- **User-Agent** explicite (en-tête HTTP) : sans cela, Reddit renvoie souvent des erreurs 429.  
- **Temporisation** : pause entre requêtes (`time.sleep`) + pauses allongées en cas de réponse 429, pour ne pas surcharger les serveurs.  
- Deux volets de collecte, toujours sur **reddit.com** (pas de compte développeur) :  
  1. **Flux `/new.json`** (pagination `after`, jusqu’au plaford pratique d’environ **~1000** posts côté API publique).  
  2. **Recherche `/search.json`** sur le même subreddit, avec une **liste de requêtes** (caractères + mots thématiques) et **déduplication** par `id` de post, afin d’**élargir** le corpus lorsque la période visée (ex. une année calendaire) se situe *au-delà* des seuls contenus atteignables par le seul `/new` (volumes élevés en 2026 par rapport à 2025, par exemple).  
- **Filtrage temporel** : appliqué côté client sur le champ `created_utc` (bornes UTC, typiquement une année calendaire).  
- Aucun téléchargement de **commentaires** (uniquement les soumissions : posts `t3`).

**Argument de choix**  
Les politiques d’accès (dont *Responsible Builder Policy*) rendent l’**API OAuth** peu accessible pour un court projet sans clé : le flux **JSON public** + bonnes pratiques (User-Agent, délais) offre un échantillon exploitable, **structuré** (champs : id, titre, corps, date) et reproductible à périmètre identique, avec les limites notées dans `VARIANTES_ET_BIAIS.md` (échantillon non exhaustif, dépend de l’activité du sub).

**Alternatives**  
- **PRAW** ou client officiel avec **clé / OAuth** si dérogation ou projet de recherche enregistré.  
- Archives tierces (ex. services type Pushshift) : hors périmètre actuel (le code ne les utilise pas).  
- *Scraping* HTML (BeautifulSoup) : ici **non retenu** (les endpoints `.json` suffisent).

---

## 2. Stockage intermédiaire et structuration

**Termes** : Data serialisation, JSON Lines, metadata sidecar, tabular data, reproducible research.

**Outils**  
- Fichier **JSONL** (un objet JSON par ligne) pour les posts.  
- Fichier **JSON** (`.meta.json`) pour la période, le nombre de requêtes, le code d’arrêt, etc.  
- **pandas** : construction des tableaux d’analyse (DataFrames) à partir des champs bruts, fusion `title` + `selftext` en une colonne d’analyse, export tableur.  
- **openpyxl** (via pandas) : export **Excel** `.xlsx` (plusieurs feuilles : index, étapes, synthèse, Top 100, etc., avec mises en forme pour la lecture humaine).

**Argument** : pandas + Excel restent le duo le plus partagé en science des données appliquée pour l’**audit** et l’**export pédagogique** ; le JSONL assure une **séparation** nette entre *donnée brute archivée* et *résultats d’analyse*.

**Alternatives** : Apache Parquet, base SQLite, ou chaîne **tidyverse** (R) si on refaisait le projet en R.

---

## 3. Nettoyage textuel / réduction de bruit linguistique

**Termes** : Text preprocessing, stopword removal, token filtering, noise reduction.

**Outils (conforme au code actuel)**  
- **NLTK** : liste `stopwords` **en anglais** (`nltk.corpus.stopwords`, chargement géré par le script).  
- **Aucun dictionnaire d’exclusion “métier”** n’est appliqué dans la version actuelle du code (cette piste a été laissée de côté pour laisser apparaître le lexique complet utile, y compris des termes comme *ostomy*, *stoma*, etc., dans les fréquences) — ce choix est **documenté** et peut être discuté en méthodologie (biais de fréquence des termes techniques vs besoins thématiques plus fins).

**Argument** : stopwords classiques en anglais pour retirer les mots outils (the, and, I…) et réduire le bruit **général** ; le positionnement *sans* filtre thématique explicite privilégie la **transparence** des lemmes les plus comptés.

**Alternatives** : ajouter un petit set de termes à exclure (justifié dans le texte de recherche) ; outils R (**tm**, **tidytext**).

---

## 4. Normalisation du vocabulaire (lemmatisation)

**Termes** : Lemmatization, linguistic normalization, (à distinguer du **stemming**).

**Outils**  
- **spaCy 3** avec le modèle **en_core_web_sm** (anglais, petit modèle, chargé via `python -m spacy download en_core_web_sm`).  
- Pipeline réduit (désactivation de blocs inutiles pour ne garder l’essentiel vers la lemmatisation).

**Argument** : la lemmatisation ramène à une forme de dictionnaire (ex. *running* → *run*), de façon **linguistiquement** plus propre qu’un *stemmer* (Porter, etc.) qui tronque mécaniquement. Indiquer les **limites** : anglais *général*, pas un modèle spécialisé “santé / stomie”.

**Alternatives** : stemming (Porter, Snowball), modèles plus gros (en_core_web_md), pipelines **UDPipe** (R, multilingue), modèles domaine cliniques (hors objectif Bachelor ici).

---

## 5. “Thématique” : ce que le projet fait (et ne fait pas)

**Termes** : Lexical frequency, unigram counts, *bag-of-words* simplifié, **exploration lexicale** (à ne **pas** présenter comme *topic modeling*).

**Outils**  
- **`collections.Counter`** (bibliothèque standard Python) : comptage des lemmes sur la colonne texte **nettoyée + lemmatisée**, extraction du **Top 100** mots.  
- **Aucun** `CountVectorizer` (scikit-learn) **n’est utilisé** dans le dépôt (pas de dépendance scikit-learn) ; le comptage est explicite et reproductible ligne à ligne.

**Argument** : méthode **déterministe** et interprétable (“combien de fois ce lemme apparaît dans le corpus nettoyé”), adaptée à un **MVP** de Bachelor. Ce n’est **pas** de la modélisation de thèmes latents (LDA, NMF, BERT topic).

**Alternatives** : **LDA** / **STM** (R) / embeddings + clustering ; plus lourds en validation et en reporting.

---

## 6. Analyse de polarité (sentiment)

**Termes** : Lexicon-based sentiment analysis, VADER, compound / valence score.

**Outils (réalité du code)**  
- **Package Python `vaderSentiment`** (*Valence Aware Dictionary and sEntiment Reasoner*), instancié par `SentimentIntensityAnalyzer` — **et non** l’intégration VADER *via* NLTK seul. Le score retenu est le **`compound`** (synthèse –1…+1).  
- Scoring appliqué sur le texte **brut** fusionné (titre + message), afin de **conserver** ponctuation et emphase que VADER sait partiellement prendre en compte.

**Référence** : Hutto, C. J., & Gilbert, E. (2014). *VADER: A Parsimonious Rule-based Model for Sentiment Analysis of Social Media Text.*  
Indiquer la **limite** : VADER est calibré sur l’**anglais général** et le style “réseaux sociaux”, pas sur un corpus clinique : résultats à interpréter comme **indicateur**, pas comme mesure clinique de détresse.

**Alternatives** : dictionnaires AFINN, Bing, NRC ; **Transformers** (ClinicalBERT, etc.) : plus coûteux, moins “explicable” pour un rapport de fin d’études court.

---

## 7. Synthèse des dépendances (fichier `requirements.txt`)

| Technologie | Rôle |
|-------------|------|
| `requests` | HTTP |
| `pandas` | Tables, export Excel |
| `openpyxl` | Moteur Excel pour pandas |
| `spacy` + `en_core_web_sm` | Lemmatisation |
| `nltk` | Stopwords (anglais) |
| `vaderSentiment` | Analyse de sentiment (compound) |

**Standard library** (sans ligne dans *requirements*) : `json`, `re`, `time`, `collections`, `pathlib`, `argparse` (dans les scripts CLI), `datetime`, `typing`.

---

*Document adapté au dépôt Ostomy-Reddit-Data-Insight. À compléter au besoin (date de collecte, taille d’échantillon effective, subreddit, année cible) dans le manuscrit de Bachelor.*
