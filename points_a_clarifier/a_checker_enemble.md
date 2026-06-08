

Phase 1. `extraction`:

1. Est ce que c'est ok d'avoir un set de donnée cherché comme cela:
/new     →  parcourir le flux « récent » du sub
/search  →  plusieurs petites recherches (a, b, …, ostomy, …) pour trouver d’autres posts
           →  tout est filtré par la période + dédupliqué par id
           →  écriture dans posts.jsonl + meta (dont queries_search_utilisees)



---

- V0 excel ( tu peux toujours en faire avec la donnée excel), V1 in verra pour un graph )
Retours `draft guide themes` — **implémenté (V0)** :- Modèle thèmes : **BART-MNLI** (`facebook/bart-large-mnli`) ; RoBERTa réservé au sentiment (`subreddit_scorer/`)
- Taxonomie MSC : **13 catégories** (F0 + A1–D11 + CRISIS) dans `subreddit_themes/themes_ostomy.yaml`
- **Multi-label**, seuil **0.40**, troncature **1000 caractères**
- Filtre F0 : tag Excel `label_digestive_relevance = 1` (pas de pré-filtrage pipeline)
- Crise : catégorie `crisis_suicidal_ideation` ; filtrer dans Excel pour les stats
- Sortie : **Excel** (`score_*`, `label_*` par catégorie) + JSONL
- Docs : `draft_guide_themes/guide_utilisation_taxonomie_ostomy.md`, `taxonomy_ostomy_roberta.md`, `.json`
- Fine-tuning RoBERTa : **hors scope V0**
- Validation manuelle : échantillon de test à partager

Sortie V1 (graphiques) : à voir plus tard.

---
Note perso:
- on parle de BART (dans le code et dans le guide ), le guide mentionne RoBERTA seulement pour le fine tuning

Pipeline et garde-fous:
- Flag crise (suicide…) -> V0 on ajoute au themes
- Validation manuelle -> je te paratage un fichier de test 

Sortie:
- V0 excel ( tu peux toujours en faire avec la donnée excel), V1 in verra pour un graph )

Questions: 
- Est ce que tu peu m'en dire plus sur le protocol MSC ? 

--

Note améliorations:
- enlever les commentaires pas en anglais
- trier les commentaire qui ne traitent pas du sujet
- score, tester un autre model ? 

Trouver une solution - mes problèmes:
- trop lent pour mon ordide mettre les thème à plus de 10 posts d'un coup, faire par batch ? 
- 

Note pour jonas:
- du au contournement de l'api Reddit ( ils ne sont plus public donc on fait du scrapping), on ne peut pas accéder à tout les posts d'un date range, on est obligé de d'agrandire notre pool et d'en prendre les posts qui matchent le date range. Question: est ce qu'on peut dire du coup qu'on veut 1000 posts de la periode 01-01-2025 à 31-12-2025 ? 
- Dans le data set que je t'ai donner il y le theme sucide, on peut refaire sans. 

A titre infomatif:
- on a utiliser pour les theme le model ... de BART, on peut en essayer d'autre - entrainné sur d'autres data set qui peuvent peu
- idem pour le score de sentiment RoBerta
- pour les thème, nous pouvons encore faire plusieurs chose pour améliorer les résultats (sans aller dans un delire de fine tuning)

Next step:
- check les x premiers commentaire du doc, ajoutes un column commentaires, et attribue toi même de thèmes ainsi que score de sentiment. 
- fait moi un retour sur la performance du theme 'digestive relevance', tu peux flitrer en haut pour voir que les 0 (pas dans le theme) ou que les 1 (dans le theme)


- enlever les posts qui sont de plus de 1000 charactères
- gérer les posts avec photos


Notes:
- essayer d'enlever les posts des besoins couverts -> baser sur des descriptions 


A faire:
- [ ] sortir 1000 com. faits en 2025 