# Points à clarifier — extraction Reddit (`subreddit_extract`)

Ce document reprend des questions fréquentes sur le **script** [`subreddit_extract/extract_subreddit.py`](../subreddit_extract/extract_subreddit.py) et le format des fichiers produits (`posts.jsonl`, `posts.meta.json`).

---

## Faut-il « nettoyer » le JSONL pour ne garder que l’id, la date et le contenu ?

**Non, ce n’est pas obligatoire à l’étape extract.**

Le fichier brut contient :

- `id`
- `created_utc` (timestamp Unix en secondes, UTC)
- `title` et `selftext` (sur Reddit, le titre et le corps du post sont deux champs distincts)

Ensemble, **titre + corps** constituent le contenu du fil. Le pipeline d’analyse existant (`ostomy_common` / `ostomy_analyze`) **reconstruit** une colonne type « titre + message » à partir de `title` et `selftext` si besoin, avant VADER / lemmatisation, etc.

Une étape ultérieure peut ajouter une date lisible (ISO), une seule colonne `texte`, ou du nettoyage (liens, anonymisation) selon le protocole de recherche — ce n’est pas une exigence de l’extraction elle-même. Garder le brut reste utile pour la **traçabilité** et la **reproductibilité**.

---

## C’est quoi `queries_search_utilisees` dans `posts.meta.json` ?

C’est la liste des **requêtes texte** utilisées pendant la phase **`/search`** sur l’API publique Reddit (`…/r/<subreddit>/search.json?q=…`).

**Rôle :** après la phase **`/new`**, le script enchaîne plusieurs recherches (par défaut sur r/ostomy : lettres `a`–`z` + mots comme `ostomy`, `stoma`, etc.) pour **découvrir d’autres posts** que la seule pagination `/new` n’amène pas toujours suffisamment loin dans le temps.

**Pourquoi c’est dans le meta :** pour documenter **comment** le corpus a été élargi (reproductibilité, biais possibles liés à la recherche).

- Avec **`--no-search`** : pas de phase `/search` ; la liste correspondante dans le meta est vide.
- Avec **`--search-queries generic`** : seulement `a`–`z` (sans les mots domaine forcés pour ostomy).

---

## Je croyais que c’était « les commentaires d’une période », pas des mots-clés

Trois précisions importantes :

### 1. Ce ne sont pas les **commentaires** Reddit

L’extracteur ne récupère que des **soumissions** (posts du fil : `t3` dans l’API), pas les **commentaires** sous les fils (`t1`). Donc pas « tous les commentaires d’une période », mais des **posts** dont la date de création est dans la fenêtre demandée.

### 2. La **période** reste le critère du corpus

Chaque post candidat est retenu seulement si son **`created_utc`** est entre `--start` et `--end` (bornes UTC). C’est bien le **cadre temporel** qui définit ce qui entre dans le fichier.

### 3. Les « mots-clés » ne remplacent pas la période

Les chaînes (`a`, `b`, …, `ostomy`, …) ne servent **pas** à dire « le texte doit contenir ce mot pour être inclus ». Elles servent de **paramètres de recherche** pour que Reddit renvoie **plus de posts candidats** ; ensuite chaque résultat est **toujours** filtré par la **même** plage de dates.

En bref : **période = définition du corpus** ; **queries `/search` = moyen technique pour mieux le remplir** qu’avec `/new` seul.

---

## Liens utiles dans le dépôt

- [README racine](../README.md) — contexte projet et démarrage (venv, PEP 668).
- [subreddit_extract/COMMANDES.md](../subreddit_extract/COMMANDES.md) — commandes du script.
- [VARIANTES_ET_BIAIS.md](../VARIANTES_ET_BIAIS.md) — limites méthodologiques (pagination, exhaustivité, etc.).
