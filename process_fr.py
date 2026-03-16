"""
Process scraped France Travail JSON files into Markdown descriptions.

Reads from html_fr/<slug>.json, writes to pages_fr/<slug>.md.
These Markdown files are used by score_fr.py for LLM scoring.

Usage:
    uv run python process_fr.py
    uv run python process_fr.py --force
"""

import argparse
import json
import os


def json_to_markdown(data, occ_meta):
    """Convert France Travail API JSON into a readable Markdown document."""
    md = []

    title = occ_meta["title"]
    rome_code = occ_meta["rome_code"]
    md.append(f"# {title}")
    md.append(f"**Code ROME:** {rome_code}")
    md.append(f"**Domaine:** {occ_meta.get('domain', '')}")
    md.append("")

    # Fiche métier (main description)
    fiche = data.get("fiche", {})
    if fiche:
        definition = fiche.get("definition", "")
        if not definition:
            # Try nested structure
            for key in ("metier", "appellations"):
                if isinstance(fiche.get(key), dict):
                    definition = fiche[key].get("definition", "")
                    if definition:
                        break
        if definition:
            md.append("## Définition")
            md.append("")
            md.append(definition)
            md.append("")

        # Accès au métier
        acces = fiche.get("accesEmploi", "")
        if not acces:
            acces = fiche.get("conditionExercice", "")
        if acces:
            md.append("## Accès au métier")
            md.append("")
            md.append(acces)
            md.append("")

        # Conditions d'exercice
        conditions = fiche.get("conditionExercice", "")
        if conditions and conditions != acces:
            md.append("## Conditions d'exercice")
            md.append("")
            md.append(conditions)
            md.append("")

        # Appellations
        appellations = fiche.get("appellations", [])
        if isinstance(appellations, list) and appellations:
            md.append("## Appellations courantes")
            md.append("")
            for app in appellations[:20]:
                if isinstance(app, dict):
                    md.append(f"- {app.get('libelle', app.get('libelleCourt', str(app)))}")
                else:
                    md.append(f"- {app}")
            md.append("")

    # Compétences
    competences = data.get("competences", {})
    if competences:
        savoirs = competences.get("savoirEtre", [])
        if not savoirs:
            savoirs = competences.get("savoirs", [])
        savoir_faire = competences.get("savoirFaire", [])

        if savoir_faire:
            md.append("## Compétences (savoir-faire)")
            md.append("")
            for sf in savoir_faire[:15]:
                if isinstance(sf, dict):
                    md.append(f"- {sf.get('libelle', str(sf))}")
                else:
                    md.append(f"- {sf}")
            md.append("")

        if savoirs:
            md.append("## Compétences (savoir-être)")
            md.append("")
            for s in savoirs[:10]:
                if isinstance(s, dict):
                    md.append(f"- {s.get('libelle', str(s))}")
                else:
                    md.append(f"- {s}")
            md.append("")

    # Salaires
    salaires = data.get("salaires", {})
    if salaires:
        md.append("## Données salariales")
        md.append("")
        if isinstance(salaires, list):
            for entry in salaires[:5]:
                if isinstance(entry, dict):
                    fap = entry.get("codeFap", entry.get("libelleFap", ""))
                    sal = entry.get("salaireBrutMedian", entry.get("SAL3", ""))
                    if sal:
                        md.append(f"- {fap}: {sal} € brut/an (médian)")
        elif isinstance(salaires, dict):
            for key, val in salaires.items():
                if val and key not in ("codeRome",):
                    md.append(f"- {key}: {val}")
        md.append("")

    # Demandeurs d'emploi
    demandeurs = data.get("demandeurs", {})
    if demandeurs:
        md.append("## Demandeurs d'emploi")
        md.append("")
        if isinstance(demandeurs, list):
            for entry in demandeurs[:5]:
                if isinstance(entry, dict):
                    cat = entry.get("categorie", entry.get("codeTypologie", ""))
                    nb = entry.get("nbDemandeurs", entry.get("valeur", ""))
                    if nb:
                        md.append(f"- Catégorie {cat}: {nb} demandeurs")
        elif isinstance(demandeurs, dict):
            for key, val in demandeurs.items():
                if val:
                    md.append(f"- {key}: {val}")
        md.append("")

    # Offres
    offres = data.get("offres", {})
    if offres:
        md.append("## Offres d'emploi")
        md.append("")
        if isinstance(offres, list):
            total = sum(
                int(e.get("nbOffres", e.get("valeur", 0)))
                for e in offres
                if isinstance(e, dict) and (e.get("nbOffres") or e.get("valeur"))
            )
            if total:
                md.append(f"- Total offres: {total:,}")
        elif isinstance(offres, dict):
            for key, val in offres.items():
                if val:
                    md.append(f"- {key}: {val}")
        md.append("")

    # Tensions
    tensions = data.get("tensions", {})
    if tensions:
        md.append("## Tensions de recrutement")
        md.append("")
        if isinstance(tensions, list):
            for entry in tensions[:5]:
                if isinstance(entry, dict):
                    code = entry.get("codeTypologie", entry.get("code", ""))
                    val = entry.get("valeur", entry.get("rang", ""))
                    lib = entry.get("libelle", "")
                    md.append(f"- {code} ({lib}): {val}")
        elif isinstance(tensions, dict):
            for key, val in tensions.items():
                if val:
                    md.append(f"- {key}: {val}")
        md.append("")

    return "\n".join(md)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    os.makedirs("pages_fr", exist_ok=True)

    with open("occupations_fr.json") as f:
        occupations = json.load(f)

    processed = skipped = missing = 0

    for occ in occupations:
        slug = occ["slug"]
        json_path = f"html_fr/{slug}.json"
        md_path = f"pages_fr/{slug}.md"

        if not os.path.exists(json_path):
            missing += 1
            continue

        if not args.force and os.path.exists(md_path):
            skipped += 1
            continue

        with open(json_path) as f:
            data = json.load(f)

        md = json_to_markdown(data, occ)
        with open(md_path, "w") as f:
            f.write(md)
        processed += 1

    print(f"Processed: {processed}, Skipped (cached): {skipped}, Missing JSON: {missing}")


if __name__ == "__main__":
    main()
