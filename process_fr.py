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
    code_rome = occ_meta["code_rome"]
    md.append(f"# {title}")
    md.append(f"**Code ROME:** {code_rome}")
    md.append(f"**Domaine:** {occ_meta.get('domain_name', occ_meta.get('domain', ''))}")
    md.append("")

    # Fiche métier / Métier (v1 stores in "metier", v2 in "fiche")
    fiche = data.get("fiche", {})
    metier = data.get("metier", {})
    if not isinstance(fiche, dict):
        fiche = {}
    if not isinstance(metier, dict):
        metier = {}

    # Definition: try metier.definition, then fiche.definition
    definition = metier.get("definition", "") or fiche.get("definition", "")
    if definition:
        md.append("## Définition")
        md.append("")
        md.append(definition)
        md.append("")

    # Accès au métier
    acces = metier.get("accesEmploi", "") or fiche.get("accesEmploi", "") or fiche.get("conditionExercice", "")
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

    # Appellations — try metier then fiche
    appellations = metier.get("appellations", []) or fiche.get("appellations", [])
    if isinstance(appellations, list) and appellations:
        md.append("## Appellations courantes")
        md.append("")
        for app in appellations[:20]:
            if isinstance(app, dict):
                md.append(f"- {app.get('libelle', app.get('libelleCourt', str(app)))}")
            else:
                md.append(f"- {app}")
        md.append("")

    # Compétences mobilisées (v1 metier.competencesMobilisees) or separate key
    competences = data.get("competences", {})
    comp_mobilisees = metier.get("competencesMobilisees", [])
    if comp_mobilisees:
        md.append("## Compétences mobilisées")
        md.append("")
        for c in comp_mobilisees[:15]:
            if isinstance(c, dict):
                md.append(f"- {c.get('libelle', str(c))}")
            else:
                md.append(f"- {c}")
        md.append("")

    if competences:
        savoirs = competences.get("savoirEtre", []) or competences.get("savoirs", [])
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

    # Contextes de travail (v1 metier.contextesTravail)
    contextes = metier.get("contextesTravail", [])
    if contextes:
        md.append("## Contextes de travail")
        md.append("")
        for c in contextes[:10]:
            if isinstance(c, dict):
                md.append(f"- {c.get('libelle', str(c))}")
            else:
                md.append(f"- {c}")
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
        if isinstance(demandeurs, dict):
            # v1 format: listeValeursParPeriode
            periodes = demandeurs.get("listeValeursParPeriode", [])
            for p in periodes[:5]:
                code = p.get("codeNomenclature", "")
                nb = p.get("valeurPrincipaleNombre", "")
                if nb:
                    md.append(f"- Catégorie {code}: {nb} demandeurs")
            if not periodes:
                for key, val in demandeurs.items():
                    if val and key != "listeValeursParPeriode":
                        md.append(f"- {key}: {val}")
        elif isinstance(demandeurs, list):
            for entry in demandeurs[:5]:
                if isinstance(entry, dict):
                    cat = entry.get("categorie", entry.get("codeTypologie", ""))
                    nb = entry.get("nbDemandeurs", entry.get("valeur", ""))
                    if nb:
                        md.append(f"- Catégorie {cat}: {nb} demandeurs")
        md.append("")

    # Offres
    offres = data.get("offres", {})
    if offres:
        md.append("## Offres d'emploi")
        md.append("")
        if isinstance(offres, dict):
            # v1 format
            periodes = offres.get("listeValeursParPeriode", [])
            total = sum(p.get("valeurPrincipaleNombre", 0) for p in periodes if p.get("valeurPrincipaleNombre"))
            if total:
                md.append(f"- Total offres: {total:,}")
            if not periodes:
                for key, val in offres.items():
                    if val and key != "listeValeursParPeriode":
                        md.append(f"- {key}: {val}")
        elif isinstance(offres, list):
            total = sum(
                int(e.get("nbOffres", e.get("valeur", 0)))
                for e in offres
                if isinstance(e, dict) and (e.get("nbOffres") or e.get("valeur"))
            )
            if total:
                md.append(f"- Total offres: {total:,}")
        md.append("")

    # Tensions
    tensions = data.get("tensions", {})
    if tensions:
        md.append("## Tensions de recrutement")
        md.append("")
        descs = {1: "Très défavorable", 2: "Défavorable", 3: "Neutre",
                 4: "Favorable", 5: "Très favorable"}
        if isinstance(tensions, dict):
            # v1 format
            periodes = tensions.get("listeValeursParPeriode", [])
            for p in periodes[:5]:
                code = p.get("codeNomenclature", "")
                rang = p.get("valeurPrincipaleNombre")
                desc = descs.get(rang, "") if code == "PERSPECTIVE" else ""
                if rang is not None:
                    md.append(f"- {code}: {rang}/5 {desc}")
            if not periodes:
                for key, val in tensions.items():
                    if val and key != "listeValeursParPeriode":
                        md.append(f"- {key}: {val}")
        elif isinstance(tensions, list):
            for entry in tensions[:5]:
                if isinstance(entry, dict):
                    code = entry.get("codeTypologie", entry.get("code", ""))
                    val = entry.get("valeur", entry.get("rang", ""))
                    lib = entry.get("libelle", "")
                    md.append(f"- {code} ({lib}): {val}")
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
