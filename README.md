# Visualiseur du marché de l'emploi US & France

Outil de recherche pour explorer visuellement les données professionnelles et l'exposition à l'IA, couvrant les marchés du travail **américain** (Bureau of Labor Statistics) et **français** (France Travail / ROME).

**Démo US : [karpathy.ai/jobs](https://karpathy.ai/jobs/)**

---

## Contenu

### Pipeline US (342 métiers)

Le BLS OOH couvre **342 métiers** couvrant l'ensemble de l'économie américaine, avec des données détaillées sur les tâches, l'environnement de travail, le niveau d'études, la rémunération et les projections d'emploi. Tout est scrapé et présenté dans un treemap interactif où la **surface** de chaque rectangle est proportionnelle au nombre d'emplois et la **couleur** affiche la métrique sélectionnée — basculez entre les projections BLS (outlook), le salaire médian, le niveau d'études et l'exposition IA.

### Pipeline français (métiers ROME)

Un pipeline parallèle analyse les **métiers français** du [répertoire ROME](https://francetravail.io/) de France Travail. Il utilise l'API France Travail (OAuth2) pour récupérer les données structurées de chaque métier : fiches métier, compétences, salaires, demandeurs d'emploi, offres et tensions de recrutement. Chaque métier est ensuite scoré pour l'exposition IA selon la même méthodologie, adaptée au contexte français.

## Coloriage par LLM

Le dépôt inclut des scrapers, parsers et un pipeline pour écrire des prompts LLM personnalisés qui scorent et colorient les métiers selon n'importe quel critère. Vous écrivez un prompt, le LLM score chaque métier, et le treemap se colorie en conséquence. La couche « Exposition IA numérique » en est un exemple — elle estime dans quelle mesure l'IA actuelle (principalement numérique) va transformer chaque métier. Vous pourriez écrire un prompt différent pour toute autre question — exposition à la robotique humanoïde, risque de délocalisation, impact climatique — et relancer le pipeline pour obtenir un autre coloriage. Voir `score.py` (US) ou `score_fr.py` (France) pour le prompt et le pipeline de scoring.

**Ce que « l'exposition IA » n'est PAS :**
- Ce n'est **pas** une prédiction de disparition du métier. Les développeurs scorent 9/10 parce que l'IA transforme leur travail — mais la demande en logiciels pourrait facilement *augmenter* à mesure que chaque développeur devient plus productif.
- Ce n'est **pas** un ajustement pour l'élasticité de la demande, la demande latente, les barrières réglementaires ou les préférences sociales pour les travailleurs humains.
- Les scores sont des estimations approximatives par LLM (Gemini Flash via OpenRouter), pas des prédictions rigoureuses. Beaucoup de métiers très exposés seront transformés, pas remplacés.

## Pipelines de données

### Pipeline US

1. **Scrape** (`scrape.py`) — Playwright (non-headless, le BLS bloque les bots) télécharge le HTML brut des 342 pages de métiers dans `html/`.
2. **Parse** (`parse_detail.py`, `process.py`) — BeautifulSoup convertit le HTML brut en fichiers Markdown propres dans `pages/`.
3. **Tabulation** (`make_csv.py`) — Extrait les champs structurés (salaire, éducation, nombre d'emplois, projections de croissance, code SOC) dans `occupations.csv`.
4. **Score** (`score.py`) — Envoie la description Markdown de chaque métier à un LLM avec une grille de scoring. Chaque métier reçoit un score d'exposition IA de 0-10 avec une justification. Résultats dans `scores.json`.
5. **Construction des données** (`build_site_data.py`) — Fusionne les stats CSV et les scores d'exposition IA dans un `site/data.json` compact pour le frontend.
6. **Site web** (`site/index.html`) — Treemap interactif avec quatre couches couleur : BLS Outlook, Salaire médian, Éducation et Exposition IA numérique.

### Pipeline français

1. **Scrape** (`scrape_fr.py`) — Appels API authentifiés OAuth2 à France Travail, récupèrent 6 types de données par métier (fiche métier, compétences, salaires, demandeurs, offres, tensions) dans `html_fr/` en JSON. Gestion des rate limits (1 req/s ROME, 10 req/s marché du travail), rafraîchissement de token et retry avec backoff exponentiel.
2. **Parse** (`process_fr.py`) — Convertit les JSON France Travail en descriptions Markdown propres dans `pages_fr/`.
3. **Tabulation** (`make_csv_fr.py`) — Extrait : salaire moyen (net annuel, moyenne des FAP), demandeurs d'emploi (catégories ABC), offres, tensions (PERSPECTIVE 1-5), niveau d'éducation (parsé depuis le texte « accès au métier »). Résultat : `occupations_fr.csv`.
4. **Score** (`score_fr.py`) — Scoring asynchrone via OpenRouter avec concurrence configurable. Prompt contextualisé pour le marché français évaluant l'exposition *technique* sans gonfler/dégonfler pour les protections du droit du travail français. Résultat : `scores_fr.json`.
5. **Construction des données** (`build_site_data_fr.py`) — Fusionne les stats CSV, les scores et la hiérarchie des domaines ROME dans `site_fr/data.json`.
6. **Prompt** (`make_prompt_fr.py`) — Génère `prompt_fr.md` avec toutes les données pour analyse LLM.
7. **Site web** (`site_fr/index.html`) — Treemap français avec drill-down hiérarchique par domaine ROME, navigation fil d'Ariane, et quatre couches couleur : Tension marché, Salaire médian, Niveau d'études et Exposition IA.

## Fichiers principaux

### US

| Fichier | Description |
|---------|-------------|
| `occupations.json` | Liste maîtresse des 342 métiers avec titre, URL, catégorie, slug |
| `occupations.csv` | Stats résumées : salaire, éducation, nombre d'emplois, projections de croissance |
| `scores.json` | Scores d'exposition IA (0-10) avec justifications pour les 342 métiers |
| `prompt.md` | Toutes les données dans un seul fichier, conçu pour être collé dans un LLM |
| `html/` | Pages HTML brutes du BLS (source de vérité, ~40 Mo) |
| `pages/` | Versions Markdown propres de chaque page de métier |
| `site/` | Site web statique (treemap) |

### France

| Fichier | Description |
|---------|-------------|
| `occupations_fr.json` | Liste des 1 584 métiers ROME avec titre, code ROME, domaine, slug |
| `occupations_fr.csv` | Statistiques : salaire, éducation, demandeurs, offres, tensions |
| `scores_fr.json` | Scores d'exposition IA (0-10) avec justifications |
| `prompt_fr.md` | Toutes les données dans un seul fichier pour analyse LLM |
| `html_fr/` | JSON bruts de l'API France Travail (source de vérité) |
| `pages_fr/` | Descriptions Markdown de chaque métier |
| `site_fr/` | Site web statique (treemap français avec drill-down) |

## Correspondance des couches de données US / France

| Couche | Source US (BLS) | Source FR (France Travail) |
|--------|-----------------|---------------------------|
| **Perspectives d'emploi** | BLS Outlook (% croissance projetée 2024-2034) | Indicateur PERSPECTIVE (tension 1-5, de très défavorable à très favorable) |
| **Salaire médian** | BLS median pay (annuel/horaire, en $) | API marché du travail (brut annuel moyen, en €) |
| **Niveau d'études** | BLS entry-level education (8 niveaux) | Parsing texte « accès au métier » (7 niveaux : Sans diplôme → Doctorat) |
| **Nombre d'emplois** | BLS employment 2024 + projections 2034 | DEFM catégories ABC (demandeurs d'emploi) + offres |
| **Exposition IA** | Gemini Flash via OpenRouter | Idem, prompt adapté au contexte français |

## Interprétation des résultats

### Méthodologie de scoring

Chaque métier est évalué sur une échelle unique de 0 à 10 mesurant **l'exposition technique à l'IA** — c'est-à-dire dans quelle mesure les capacités actuelles de l'IA peuvent transformer les tâches de ce métier. Le scoring est identique pour les US et la France :

| Score | Niveau | Description | Exemples FR |
|-------|--------|-------------|-------------|
| 0-1 | Minimale | Travail quasi-entièrement physique ou en environnement imprévisible | Couvreur, maçon, paysagiste |
| 2-3 | Faible | Travail principalement physique/relationnel, IA sur tâches périphériques | Électricien, plombier, pompier |
| 4-5 | Modérée | Mélange travail physique et intellectuel | Infirmier, policier, vétérinaire |
| 6-7 | Élevée | Travail principalement intellectuel, IA déjà utile | Enseignant, comptable, journaliste |
| 8-9 | Très élevée | Travail quasi-entièrement sur ordinateur | Développeur, graphiste, traducteur |
| 10 | Maximale | Traitement routinier d'informations, entièrement numérique | Opérateur de saisie, télévendeur |

### Heuristique clé

> Si le travail peut être entièrement réalisé depuis un bureau à domicile sur un ordinateur — écrire, coder, analyser, communiquer — alors l'exposition à l'IA est intrinsèquement élevée (7+).

### Ce que le score n'est PAS

- **Ce n'est pas une prédiction de disparition.** Un développeur à 9/10 ne signifie pas que le métier disparaît : la demande peut *augmenter* avec les gains de productivité.
- **Ce n'est pas un indice de vitesse d'adoption.** Le droit du travail français (CDI, conventions collectives, obligations de reclassement) ralentit l'adoption mais ne change pas l'exposition technique.
- **Ce n'est pas ajusté pour les protections sociales.** Les scores US et FR utilisent les mêmes ancres de calibration pour permettre la comparaison.

### Lecture du treemap

- **Surface** = nombre de demandeurs d'emploi (FR) ou nombre d'emplois (US)
- **Couleur** = métrique sélectionnée (tension marché, salaire, éducation, exposition IA)
- **Drill-down** (FR uniquement) : cliquez sur un domaine ROME pour explorer les métiers, Échap pour remonter
- Les rectangles les plus grands représentent les professions avec le plus de personnes concernées

## Prompt LLM

[`prompt.md`](prompt.md) (US) et [`prompt_fr.md`](prompt_fr.md) (France) regroupent toutes les données dans des fichiers uniques conçus pour être collés dans un LLM. Cela permet d'avoir une conversation fondée sur les données concernant l'impact de l'IA sur le marché du travail sans avoir besoin d'exécuter de code.

## Installation

```
uv sync
uv run playwright install chromium
```

Variables requises dans `.env` :
```
# Pipeline US (OpenRouter pour le scoring LLM)
OPENROUTER_API_KEY=votre_clé_ici

# Pipeline français (API France Travail)
FRANCE_TRAVAIL_CLIENT_ID=votre_client_id
FRANCE_TRAVAIL_CLIENT_SECRET=votre_client_secret
```

Inscrivez-vous sur [francetravail.io](https://francetravail.io/) pour obtenir les credentials de l'API France Travail.

## Utilisation

### Pipeline US

```bash
uv run python scrape.py           # Scraper les pages BLS
uv run python process.py          # Générer le Markdown depuis le HTML
uv run python make_csv.py         # Générer le CSV résumé
uv run python score.py            # Scorer l'exposition IA
uv run python build_site_data.py  # Construire les données du site
cd site && python -m http.server 8000
```

### Pipeline français

```bash
uv run python scrape_fr.py           # Scraper l'API France Travail
uv run python process_fr.py          # Générer le Markdown depuis les JSON
uv run python make_csv_fr.py         # Générer le CSV résumé
uv run python score_fr.py            # Scorer l'exposition IA (async)
uv run python build_site_data_fr.py  # Construire les données du site
uv run python make_prompt_fr.py      # Générer le prompt LLM
cd site_fr && python -m http.server 8001
```
