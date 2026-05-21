# Taxonomie r/ostomy — classification multi-label (BART-MNLI)

> Document de référence du **Groupe 40 — B3.6 MSC Immersion communautaire, UNIL 2025-2026**.  
> Fichier machine : [`taxonomy_ostomy_roberta.json`](taxonomy_ostomy_roberta.json)  
> Fichier opérationnel pipeline : [`../subreddit_themes/themes_ostomy.yaml`](../subreddit_themes/themes_ostomy.yaml)

---

## Métadonnées

| Clé | Valeur |
|-----|--------|
| Projet | Enjeux du retour à la communauté pour personnes stomisées (Suisse) |
| Source | Subreddit r/ostomy (Reddit), langue anglaise |
| Type | Classification **multi-label** |
| Périmètre | Stomies digestives (F0) ; exclure urostomie, trachéo, pub |
| Seuil zero-shot | score ≥ **0.40** par label |
| Troncature texte | **1000 caractères** |
| Modèle V0 | `facebook/bart-large-mnli` |

---

## Table récapitulative (13 catégories)

| ID | short_name | Dimension | Priorité recherche |
|----|------------|-----------|-------------------|
| F0 | `digestive_relevance` | FILTRE | — |
| A1 | `technical_stoma_care` | A — Besoins pratiques | |
| A2 | `diet_and_output` | A — Besoins pratiques | |
| A3 | `access_to_resources` | A — Besoins pratiques | **Oui** |
| B4 | `body_image_acceptance` | B — Vécu psychosocial | |
| B5 | `mental_health_emotional` | B — Vécu psychosocial | **Oui** |
| B6 | `relationships_sexuality` | B — Vécu psychosocial | |
| C7 | `social_stigma_participation` | C — Réinsertion sociale | |
| C8 | `return_to_work_activities` | C — Réinsertion sociale | |
| C9 | `hospital_to_home_transition` | C — Réinsertion sociale | **Priorité max** |
| D10 | `healthcare_experience` | D — Système de soins | **Oui** |
| D11 | `peer_support_community` | D — Système de soins | |
| CRISIS | `crisis_suicidal_ideation` | FILTRE / relecture | Exclure stats si flag |

---

## F0 — digestive_relevance

**Définition :** Post sur stomie digestive (colostomie, iléostomie, stomie intestinale), pas urostomie, trachéostomie ou sujet hors scope.

**Hypothèse NLI :**

> This post is about living with a colostomy, ileostomy, or intestinal stoma.

**Usage V0 :** filtrer dans Excel (`label_digestive_relevance = 1`), pas de pré-filtrage dans le pipeline.

---

## A1 — technical_stoma_care

**Définition :** Gestion technique de l'appareil, fuites, soins de la peau, complications, routines de self-care.

**Hypothèse NLI :**

> This post is about the physical management of the stoma appliance, skin care around the stoma, or technical problems like leaks and bag changes.

**Mots-clés indicatifs :** leaking, wafer, flange, bag change, peristomal skin, prolapse, pouch, seal…

---

## A2 — diet_and_output

**Définition :** Alimentation, transit, volume/consistance des effluents, déshydratation, occlusion.

**Hypothèse NLI :**

> This post is about diet, nutrition, food choices, or managing stoma output volume and consistency.

---

## A3 — access_to_resources

**Définition :** Accès matériel, assurance, coûts, infirmière stomie / WOC, barrières structurelles.

**Hypothèse NLI :**

> This post is about access to stoma supplies, insurance coverage, reimbursement costs, or difficulties accessing specialist stoma care.

---

## B4 — body_image_acceptance

**Définition :** Image corporelle, acceptation, deuil du corps, honte/fierté, identité.

**Hypothèse NLI :**

> This post is about body image, self-acceptance, or the emotional relationship to one's changed body and physical appearance with an ostomy.

---

## B5 — mental_health_emotional

**Définition :** Détresse psychologique, anxiété, dépression, espoir, résilience.

**Hypothèse NLI :**

> This post is about mental health, psychological distress, anxiety, depression, fear, or emotional wellbeing related to living with an ostomy.

---

## B6 — relationships_sexuality

**Définition :** Couple, sexualité, disclosure, dating, intimité.

**Hypothèse NLI :**

> This post is about romantic relationships, sexual intimacy, dating, or disclosing the ostomy to a partner or potential partner.

---

## C7 — social_stigma_participation

**Définition :** Stigmatisation, gêne en public, isolement, discrimination.

**Hypothèse NLI :**

> This post is about social stigma, embarrassment in public, fear of others noticing the ostomy, social isolation, or barriers to participating in social activities.

---

## C8 — return_to_work_activities

**Définition :** Retour travail, sport, voyage, reprise des activités quotidiennes.

**Hypothèse NLI :**

> This post is about returning to work, resuming physical activities, sports, travel, or re-engaging with daily life and hobbies after ostomy surgery.

---

## C9 — hospital_to_home_transition

**Définition :** Sortie d'hospitalisation, préparation insuffisante, suivi post-sortie, coordination ville–hôpital.

**Hypothèse NLI :**

> This post is about the experience of being discharged from hospital, preparation for returning home, post-discharge follow-up care, or gaps in care coordination after ostomy surgery.

**Complément corpus :** recherches ciblées `discharge`, `going home`, `nobody told me`, `community nurse`, `first week home`, `readmitted`…

---

## D10 — healthcare_experience

**Définition :** Qualité des soins, relation aux professionnels, lacunes informationnelles.

**Hypothèse NLI :**

> This post is about the quality of healthcare received, satisfaction or dissatisfaction with healthcare professionals, or gaps in information provided by the medical team.

---

## D11 — peer_support_community

**Définition :** Entraide, partage d'expérience, gratitude envers la communauté en ligne, associations.

**Hypothèse NLI :**

> This post is about peer support, sharing personal experience to help others, community solidarity, or the value of connecting with other ostomy patients.

---

## CRISIS — crisis_suicidal_ideation (V0 pipeline)

**Définition :** Idéation suicidaire ou crise aiguë. Relecture manuelle recommandée ; exclusion des analyses quantitatives sauf validation éthique.

**Hypothèse NLI :**

> This post expresses suicidal ideation, wanting to die, not worth living, or an acute mental health crisis.

---

## Notes d'implémentation

1. Classifier **tous** les posts avec les 13 labels (`multi_label=True`).
2. Appliquer le seuil **0.40** par label.
3. Dans Excel : filtrer `label_digestive_relevance = 1` pour le corpus digestif.
4. Exclure ou relire les posts `label_crisis_suicidal_ideation = 1`.
5. Valider manuellement un échantillon (~50 posts/catégorie).

Voir aussi : [`guide_utilisation_taxonomie_ostomy.md`](guide_utilisation_taxonomie_ostomy.md)
