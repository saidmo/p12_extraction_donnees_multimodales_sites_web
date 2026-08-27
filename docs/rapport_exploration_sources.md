# Rapport d'exploration de sources — CheckIt.AI

**Livrable :** Étape 1 — Exploration et qualification des sources
**Projet :** Acquisition de données multimodales (texte + image) pour la détection de fake news

---

## 1. Objectif

Identifier et qualifier des sources de données **multimodales** (texte + image)
pertinentes pour alimenter un détecteur de désinformation. Pour chaque source :
type de données, format, langue, qualité des labels, méthode d'extraction, droits d'usage.

## 2. Cas typiques de désinformation multimodale (cadrage métier)

La désinformation visée combine souvent texte et image. Cas récurrents :

1. **Mécontextualisation** : une image authentique réutilisée avec une légende trompeuse
   (ex. une photo d'inondation à Paris présentée comme étant à Valence). Cas le plus fréquent.
2. **Image truquée** : photomontage, retouche.
3. **Image générée par IA** accompagnant un faux récit.
4. **Discordance texte/image** : la légende affirme ce que l'image ne montre pas.
5. **Fausse capture** : faux tweet, faux bandeau de presse.

**Conséquence :** l'appariement texte↔image doit être garanti au niveau de l'enregistrement.
Une entrée sans les deux modalités n'a pas de valeur pour ce cas d'usage.

## 3. Distinction clé : opinion ≠ désinformation

- **Opinion controversée** : jugement subjectif qui divise, relevant de la liberté d'expression.
- **Désinformation** : information *objectivement fausse*, diffusée pour tromper.

Le schéma de données sépare ces cas (`label` : `opinion` distinct de `false`), et reste
`unknown` en cas de doute plutôt que de forcer un verdict.

## 4. Point de méthode : réputation ≠ label

La réputation d'une source **n'est pas** un label de véracité : un média fiable peut publier
une erreur, une source douteuse peut dire vrai. Un label fiable ne vient donc que d'un
**verdict explicite par publication** (fact-checker) ou d'un **dataset annoté**.

## 5. Sources qualifiées

| Source | Modalités | Format | Langue | Labels | Extraction | Droits |
|---|---|---|---|---|---|---|
| **NewsAPI** | texte + image | API REST / JSON | fr, en… | ❌ aucun | API REST + clé | gratuit non commercial |
| **Flux RSS fact-check** (Le Monde Décodeurs, Snopes…) | texte + image | RSS / XML | fr, en | ⚠️ verdict implicite | feedparser | usage raisonnable + attribution |
| **Fakeddit** | texte + image | TSV + images | en | ✅ 2/3/6 classes (distant supervision) | download + script | usage recherche (colonnes restreintes) |

### Fiches

**NewsAPI** — agrégateur de presse ; réponse JSON avec `title`, `description`, `url`,
`urlToImage`, `publishedAt`, `source`. Pas de label de véracité. Plan gratuit : ~100 req/j,
historique 1 mois, texte non intégral. **Rôle : source live principale** (flux frais).

**Flux RSS de fact-checkers** — sans clé ni authentification, robuste et adapté à l'exécution
sans intervention. Image via `media:content` / `enclosure`. Le verdict fournit un **label
implicite** (déduit prudemment par heuristique, `unknown` par défaut). **Rôle : source live
apportant un signal de véracité.** (Remarque : peu de fact-checkers exposent un flux RSS
propre et stable — AFP Factuel était cassé lors des tests.)

**Fakeddit** — dataset multimodal de référence : plus d'un million d'échantillons texte + image
issus de Reddit, labellisés en 2, 3 et 6 classes par distant supervision, livrés en TSV avec un
script de téléchargement d'images. Anglais. Licence : usage recherche, colonnes restreintes
(`clean_title`, `6_way_label`). **Rôle : socle labellisé (vérité terrain pour l'entraînement).**

*Méta-sources de découverte :* Google Dataset Search, Hugging Face Datasets, Kaggle,
public-apis. Autres datasets pertinents repérés : FakeNewsNet (PolitiFact + GossipCop),
MediaEval « Verifying Multimedia Use ».

## 6. Architecture retenue : hybride

Le projet exige à la fois des **labels fiables** (pour l'entraînement) et un **flux frais
orchestré** (pour la production). Ces deux qualités ne coexistent pas dans une même source :
les datasets annotés sont fiables mais figés ; les sources live sont fraîches mais non labellisées.

**Solution :** combiner les deux, pour deux rôles complémentaires —

- **Pipeline live** (NewsAPI + RSS) : données fraîches, orchestrées par Airflow.
- **Socle labellisé** (Fakeddit) : vérité terrain, chargée une fois.

## 7. Éléments indispensables & format de sortie

**Champs obligatoires par publication :** `id`, `title`, `content`, `image` (url + chemin local),
`source`, `url`, `language`, `label`, `published_at`, `fetched_at`.

**Stockage retenu :** base **PostgreSQL** (données requêtables et transactionnelles). Les images
sont stockées sur disque et référencées par chemin — jamais le binaire en base. Colonnes
dérivées ajoutées à la transformation (`content_length`, `word_count`).

## 8. Méthodes d'extraction

| Méthode | Usage | Décision |
|---|---|---|
| API REST (NewsAPI) | canal officiel, stable | ✅ retenu |
| RSS / feedparser | canal officiel d'un site | ✅ retenu |
| Download de dataset (Fakeddit) | socle labellisé | ✅ retenu |
| Scrapy | crawl si explicitement autorisé | ⚠️ au cas par cas |
| Selenium | rendu JS / anti-bot | ❌ écarté (fragile, lourd, souvent contraire aux CGU) |

Principe : **canaux officiels d'abord**, le scraping seulement s'il est autorisé.

## 9. Points de vigilance

- Ne pas confondre opinion controversée et désinformation (cf. §3).
- Garantir l'association texte↔image dans chaque entrée.
- Respecter les droits d'usage (licence Fakeddit, conditions NewsAPI).
- Fiabilité des labels, du plus au moins fiable : dataset annoté > verdict fact-check
  (implicite) > sources de presse (aucun label).
