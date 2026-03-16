"""
Score French occupations' AI exposure using an LLM via OpenRouter.

Async implementation with configurable concurrency and incremental caching.

Usage:
    uv run python score_fr.py
    uv run python score_fr.py --model google/gemini-3-flash-preview
    uv run python score_fr.py --concurrency 10
    uv run python score_fr.py --start 0 --end 10
"""

import argparse
import asyncio
import json
import os
import httpx
from dotenv import load_dotenv

load_dotenv()

DEFAULT_MODEL = "google/gemini-3-flash-preview"
OUTPUT_FILE = "scores_fr.json"
API_URL = "https://openrouter.ai/api/v1/chat/completions"

SYSTEM_PROMPT = """\
Tu es un analyste expert évaluant l'exposition des métiers français à \
l'intelligence artificielle. On te donne une description détaillée d'un métier \
issu du répertoire ROME de France Travail.

Évalue l'**exposition à l'IA** de ce métier sur une échelle de 0 à 10.

L'exposition à l'IA mesure : dans quelle mesure l'IA va-t-elle transformer \
ce métier ? Considère à la fois les effets directs (l'IA automatisant des \
tâches actuellement faites par des humains) et les effets indirects (l'IA \
rendant chaque travailleur tellement productif que moins de personnes sont \
nécessaires).

Un signal clé est de savoir si le produit du travail est fondamentalement \
numérique. Si le travail peut être entièrement réalisé depuis un bureau à \
domicile sur un ordinateur — écrire, coder, analyser, communiquer — alors \
l'exposition à l'IA est intrinsèquement élevée (7+), car les capacités de \
l'IA dans les domaines numériques progressent rapidement. À l'inverse, les \
métiers nécessitant une présence physique, un savoir-faire manuel ou une \
interaction humaine en temps réel constituent une barrière naturelle.

Note importante : évalue l'exposition **technique** (ce que l'IA peut faire), \
pas la vitesse d'adoption. Le droit du travail français (CDI, conventions \
collectives, obligations de reclassement) ralentit l'adoption mais ne change \
pas l'exposition technique. Ne gonfle pas et ne réduis pas les scores à cause \
des protections sociales françaises.

Utilise ces ancres de calibration :

- **0–1 : Exposition minimale.** Travail presque entièrement physique, \
manuel, ou nécessitant une présence humaine en temps réel dans des \
environnements imprévisibles. L'IA n'a quasi aucun impact. \
Exemples : couvreur, paysagiste, maçon.

- **2–3 : Exposition faible.** Travail principalement physique ou \
relationnel. L'IA peut aider sur des tâches périphériques (planning, \
paperasse) mais ne touche pas le cœur du métier. \
Exemples : électricien, plombier, pompier, aide-soignant.

- **4–5 : Exposition modérée.** Mélange de travail physique/relationnel \
et de travail intellectuel. L'IA peut significativement aider sur les \
parties traitement de l'information. \
Exemples : infirmier, policier, vétérinaire.

- **6–7 : Exposition élevée.** Travail principalement intellectuel avec \
besoin de jugement humain, de relations ou de présence physique. Les \
outils IA sont déjà utiles et les travailleurs utilisant l'IA sont \
substantiellement plus productifs. \
Exemples : enseignant, manager, comptable, journaliste.

- **8–9 : Exposition très élevée.** Le travail se fait presque \
entièrement sur ordinateur. Toutes les tâches principales — écrire, \
coder, analyser, concevoir, communiquer — sont dans des domaines où \
l'IA progresse rapidement. Restructuration majeure du métier. \
Exemples : développeur, graphiste, traducteur, analyste de données, \
assistant juridique, rédacteur.

- **10 : Exposition maximale.** Traitement routinier d'informations, \
entièrement numérique, sans composante physique. L'IA peut déjà faire \
l'essentiel aujourd'hui. \
Exemples : opérateur de saisie, télévendeur.

Réponds avec UNIQUEMENT un objet JSON dans ce format exact, pas d'autre texte :
{
  "exposure": <0-10>,
  "rationale": "<2-3 phrases expliquant les facteurs clés>"
}\
"""


async def score_one(client, text, model, semaphore, api_key):
    """Score one occupation with retry on 403/429."""
    async with semaphore:
        for attempt in range(4):
            try:
                response = await client.post(
                    API_URL,
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "model": model,
                        "messages": [
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": text},
                        ],
                        "temperature": 0.2,
                    },
                    timeout=60,
                )
                if response.status_code in (429, 403):
                    wait = 2 ** attempt
                    await asyncio.sleep(wait)
                    continue
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"]
                content = content.strip()
                if content.startswith("```"):
                    content = content.split("\n", 1)[1]
                    if content.endswith("```"):
                        content = content[:-3]
                    content = content.strip()
                return json.loads(content)
            except Exception as e:
                if attempt < 3:
                    await asyncio.sleep(2 ** attempt)
                else:
                    raise e
    return None


async def main_async():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--end", type=int, default=None)
    parser.add_argument("--concurrency", type=int, default=5)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print("ERROR: Set OPENROUTER_API_KEY in .env")
        return

    with open("occupations_fr.json") as f:
        occupations = json.load(f)

    subset = occupations[args.start:args.end]

    # Load existing scores
    scores = {}
    if os.path.exists(OUTPUT_FILE) and not args.force:
        with open(OUTPUT_FILE) as f:
            for entry in json.load(f):
                scores[entry["slug"]] = entry

    print(f"Scoring {len(subset)} French occupations with {args.model}")
    print(f"Already cached: {len(scores)}, concurrency: {args.concurrency}")

    semaphore = asyncio.Semaphore(args.concurrency)
    errors = []

    async with httpx.AsyncClient() as client:
        tasks = []
        task_meta = []

        for occ in subset:
            slug = occ["slug"]
            if slug in scores:
                continue

            # Try pages_fr/ first, then html_fr/
            md_path = f"pages_fr/{slug}.md"
            json_path = f"html_fr/{slug}.json"

            if os.path.exists(md_path):
                with open(md_path) as f:
                    text = f.read()
            elif os.path.exists(json_path):
                with open(json_path) as f:
                    data = json.load(f)
                text = json.dumps(data, ensure_ascii=False, indent=2)[:8000]
            else:
                continue

            tasks.append(score_one(client, text, args.model, semaphore, api_key))
            task_meta.append(occ)

        if not tasks:
            print("All occupations already scored.")
        else:
            print(f"Scoring {len(tasks)} remaining occupations...")
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for occ, result in zip(task_meta, results):
                slug = occ["slug"]
                if isinstance(result, Exception):
                    print(f"  ERROR {occ['title']}: {result}")
                    errors.append(slug)
                elif result:
                    scores[slug] = {
                        "slug": slug,
                        "title": occ["title"],
                        "code_rome": occ["code_rome"],
                        **result,
                    }
                    print(f"  {occ['title']}: exposure={result.get('exposure', '?')}")

            # Save checkpoint
            with open(OUTPUT_FILE, "w") as f:
                json.dump(list(scores.values()), f, indent=2, ensure_ascii=False)

    print(f"\nDone. Scored {len(scores)} occupations, {len(errors)} errors.")
    if errors:
        print(f"Errors: {errors}")

    # Summary stats
    vals = [s for s in scores.values() if "exposure" in s]
    if vals:
        avg = sum(s["exposure"] for s in vals) / len(vals)
        by_score = {}
        for s in vals:
            bucket = s["exposure"]
            by_score[bucket] = by_score.get(bucket, 0) + 1
        print(f"\nMoyenne exposition sur {len(vals)} métiers : {avg:.1f}")
        print("Distribution :")
        for k in sorted(by_score):
            print(f"  {k}: {'█' * by_score[k]} ({by_score[k]})")


def main():
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
