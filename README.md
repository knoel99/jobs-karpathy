# US & French Job Market Visualizer

A research tool for visually exploring occupational data and AI exposure, covering both the **US** (Bureau of Labor Statistics) and **French** (France Travail / ROME) labor markets.

**US Live demo: [karpathy.ai/jobs](https://karpathy.ai/jobs/)**

---

## What's here

### US Pipeline (342 occupations)

The BLS OOH covers **342 occupations** spanning every sector of the US economy, with detailed data on job duties, work environment, education requirements, pay, and employment projections. We scraped all of it and built an interactive treemap visualization where each rectangle's **area** is proportional to total employment and **color** shows the selected metric — toggle between BLS projected growth outlook, median pay, education requirements, and AI exposure.

### French Pipeline (métiers ROME)

A parallel pipeline analyzes **French occupations** from the [répertoire ROME](https://francetravail.io/) de France Travail. It uses the France Travail API (OAuth2) to fetch structured data for each métier: fiches métier, compétences, salaires, demandeurs d'emploi, offres et tensions de recrutement. Each occupation is scored for AI exposure using the same methodology adapted to the French context.

## LLM-powered coloring

The repo includes scrapers, parsers, and a pipeline for writing custom LLM prompts to score and color occupations by any criteria. You write a prompt, the LLM scores each occupation, and the treemap colors accordingly. The "Digital AI Exposure" layer is one example — it estimates how much current AI (which is primarily digital) will reshape each occupation. But you could write a different prompt for any question — e.g. exposure to humanoid robotics, offshoring risk, climate impact — and re-run the pipeline to get a different coloring. See `score.py` (US) or `score_fr.py` (France) for the prompt and scoring pipeline.

**What "AI Exposure" is NOT:**
- It does **not** predict that a job will disappear. Software developers score 9/10 because AI is transforming their work — but demand for software could easily *grow* as each developer becomes more productive.
- It does **not** account for demand elasticity, latent demand, regulatory barriers, or social preferences for human workers.
- The scores are rough LLM estimates (Gemini Flash via OpenRouter), not rigorous predictions. Many high-exposure jobs will be reshaped, not replaced.

## Data pipelines

### US Pipeline

1. **Scrape** (`scrape.py`) — Playwright (non-headless, BLS blocks bots) downloads raw HTML for all 342 occupation pages into `html/`.
2. **Parse** (`parse_detail.py`, `process.py`) — BeautifulSoup converts raw HTML into clean Markdown files in `pages/`.
3. **Tabulate** (`make_csv.py`) — Extracts structured fields (pay, education, job count, growth outlook, SOC code) into `occupations.csv`.
4. **Score** (`score.py`) — Sends each occupation's Markdown description to an LLM with a scoring rubric. Each occupation gets an AI Exposure score from 0-10 with a rationale. Results saved to `scores.json`.
5. **Build site data** (`build_site_data.py`) — Merges CSV stats and AI exposure scores into a compact `site/data.json` for the frontend.
6. **Website** (`site/index.html`) — Interactive treemap visualization with four color layers: BLS Outlook, Median Pay, Education, and Digital AI Exposure.

### French Pipeline

1. **Scrape** (`scrape_fr.py`) — OAuth2-authenticated API calls to France Travail fetch 6 data types per occupation (fiche métier, compétences, salaires, demandeurs, offres, tensions) into `html_fr/` as JSON. Implements rate limiting (1 req/sec ROME, 10 req/sec marché du travail), token refresh, and retry with exponential backoff.
2. **Parse** (`process_fr.py`) — Converts France Travail JSON into clean Markdown descriptions in `pages_fr/`.
3. **Tabulate** (`make_csv_fr.py`) — Extracts: salaire moyen (net annuel, avg across FAP), demandeurs d'emploi (catégories ABC), offres, tensions (PERSPECTIVE 1-5), niveau d'éducation (parsed from accès au métier text). Output: `occupations_fr.csv`.
4. **Score** (`score_fr.py`) — Async scoring via OpenRouter with configurable concurrency. French-contextualized prompt evaluating *technical* exposure without inflating/deflating for French labor protections. Output: `scores_fr.json`.
5. **Build site data** (`build_site_data_fr.py`) — Merges CSV stats, scores, and ROME domain hierarchy into `site_fr/data.json`.
6. **Prompt** (`make_prompt_fr.py`) — Generates `prompt_fr.md` with all data for LLM analysis.
7. **Website** (`site_fr/index.html`) — French treemap with hierarchical drill-down by ROME domain, breadcrumb navigation, and four color layers: Exposition IA, Salaire médian, Éducation, Tensions de recrutement.

## Key files

### US

| File | Description |
|------|-------------|
| `occupations.json` | Master list of 342 occupations with title, URL, category, slug |
| `occupations.csv` | Summary stats: pay, education, job count, growth projections |
| `scores.json` | AI exposure scores (0-10) with rationales for all 342 occupations |
| `prompt.md` | All data in a single file, designed to be pasted into an LLM for analysis |
| `html/` | Raw HTML pages from BLS (source of truth, ~40MB) |
| `pages/` | Clean Markdown versions of each occupation page |
| `site/` | Static website (treemap visualization) |

### France

| File | Description |
|------|-------------|
| `occupations_fr.json` | Liste des métiers ROME avec titre, code ROME, domaine, slug |
| `occupations_fr.csv` | Statistiques : salaire, éducation, demandeurs, offres, tensions |
| `scores_fr.json` | Scores d'exposition IA (0-10) avec justifications |
| `prompt_fr.md` | Toutes les données dans un seul fichier pour analyse LLM |
| `html_fr/` | JSON bruts de l'API France Travail (source de vérité) |
| `pages_fr/` | Descriptions Markdown de chaque métier |
| `site_fr/` | Site web statique (treemap en français avec drill-down) |

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

### Sources de données

| Donnée | Source US | Source FR |
|--------|-----------|-----------|
| Métiers | BLS Occupational Outlook Handbook (342) | France Travail ROME 4.0 |
| Salaires | BLS median pay (annual/hourly) | France Travail API marché du travail (brut annuel moyen) |
| Emploi | BLS employment 2024 + projections 2034 | DEFM catégories ABC (demandeurs d'emploi) |
| Perspectives | BLS outlook % (croissance projetée) | Indicateur PERSPECTIVE (tension 1-5) |
| Éducation | BLS entry-level education | Parsing texte « accès au métier » des fiches ROME |
| Scoring IA | Gemini Flash via OpenRouter | Idem, prompt adapté au contexte français |

### Lecture du treemap

- **Surface** = nombre de demandeurs d'emploi (FR) ou nombre d'emplois (US)
- **Couleur** = métrique sélectionnée (exposition IA, salaire, éducation, tensions)
- **Drill-down** (FR uniquement) : cliquez sur un domaine ROME pour voir les métiers, Échap pour remonter
- Les rectangles les plus grands représentent les professions avec le plus de personnes concernées

## LLM prompt

[`prompt.md`](prompt.md) (US) and [`prompt_fr.md`](prompt_fr.md) (France) package all the data into single files designed to be pasted into an LLM. This lets you have a data-grounded conversation about AI's impact on the job market without needing to run any code.

## Setup

```
uv sync
uv run playwright install chromium
```

Requires in `.env`:
```
# US pipeline (OpenRouter for LLM scoring)
OPENROUTER_API_KEY=your_key_here

# French pipeline (France Travail API)
FRANCE_TRAVAIL_CLIENT_ID=your_client_id
FRANCE_TRAVAIL_CLIENT_SECRET=your_client_secret
```

Register at [francetravail.io](https://francetravail.io/) to obtain France Travail API credentials.

## Usage

### US Pipeline

```bash
uv run python scrape.py           # Scrape BLS pages
uv run python process.py          # Generate Markdown from HTML
uv run python make_csv.py         # Generate CSV summary
uv run python score.py            # Score AI exposure
uv run python build_site_data.py  # Build website data
cd site && python -m http.server 8000
```

### French Pipeline

```bash
uv run python scrape_fr.py           # Scrape France Travail API
uv run python process_fr.py          # Generate Markdown from JSON
uv run python make_csv_fr.py         # Generate CSV summary
uv run python score_fr.py            # Score AI exposure (async)
uv run python build_site_data_fr.py  # Build website data
uv run python make_prompt_fr.py      # Generate LLM prompt
cd site_fr && python -m http.server 8001
```
