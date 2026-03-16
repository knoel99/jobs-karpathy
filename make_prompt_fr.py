"""
Generate prompt_fr.md — all French occupation data in a single file for LLM analysis.

Usage:
    uv run python make_prompt_fr.py
"""

import csv
import json


def fmt_salary(sal):
    if sal is None:
        return "?"
    return f"{sal:,} €".replace(",", " ")


def fmt_number(n):
    if n is None:
        return "?"
    if n >= 1_000_000:
        return f"{n / 1e6:.1f}M"
    if n >= 1_000:
        return f"{n / 1e3:.0f}K"
    return str(n)


def main():
    with open("occupations_fr.json") as f:
        occupations = json.load(f)

    csv_rows = {}
    try:
        with open("occupations_fr.csv", encoding="utf-8") as f:
            csv_rows = {row["slug"]: row for row in csv.DictReader(f)}
    except FileNotFoundError:
        pass

    scores = {}
    try:
        with open("scores_fr.json") as f:
            scores = {s["slug"]: s for s in json.load(f)}
    except FileNotFoundError:
        pass

    # Merge records
    records = []
    for occ in occupations:
        slug = occ["slug"]
        row = csv_rows.get(slug, {})
        score = scores.get(slug, {})
        salary = int(float(row["median_salary_annual"])) if row.get("median_salary_annual") else None
        demandeurs = int(row["demandeurs"]) if row.get("demandeurs") else None
        offres = int(row["offres"]) if row.get("offres") else None
        records.append({
            "title": occ["title"],
            "slug": slug,
            "code_rome": occ["code_rome"],
            "domain": occ.get("domain", ""),
            "salary": salary,
            "demandeurs": demandeurs,
            "offres": offres,
            "tension": row.get("tension", ""),
            "education": row.get("niveau_education", ""),
            "exposure": score.get("exposure"),
            "rationale": score.get("rationale", ""),
        })

    records.sort(key=lambda r: (-(r["exposure"] or 0), -(r["demandeurs"] or 0)))

    lines = []

    # Header
    lines.append("# Exposition des métiers français à l'IA")
    lines.append("")
    lines.append("Ce document contient les données structurées sur les métiers français issus du répertoire ROME de France Travail, chacun noté pour son exposition à l'IA sur une échelle de 0 à 10 par un LLM (Gemini Flash). Utilisez ces données pour analyser et discuter de l'impact de l'IA sur le marché du travail français.")
    lines.append("")

    # Scoring methodology
    lines.append("## Méthodologie de notation")
    lines.append("")
    lines.append("Chaque métier est noté sur un axe unique d'exposition à l'IA de 0 à 10, mesurant dans quelle mesure l'IA va transformer ce métier. Le score considère à la fois l'automatisation directe et les effets indirects de productivité.")
    lines.append("")
    lines.append("Heuristique clé : si le travail peut être entièrement réalisé depuis un bureau à domicile sur un ordinateur — écrire, coder, analyser, communiquer — alors l'exposition est intrinsèquement élevée (7+).")
    lines.append("")
    lines.append("Ancres de calibration :")
    lines.append("- 0-1 Minimale : couvreurs, maçons, paysagistes")
    lines.append("- 2-3 Faible : électriciens, plombiers, pompiers, aides-soignants")
    lines.append("- 4-5 Modérée : infirmiers, policiers, vétérinaires")
    lines.append("- 6-7 Élevée : enseignants, managers, comptables, journalistes")
    lines.append("- 8-9 Très élevée : développeurs, graphistes, traducteurs, analystes de données")
    lines.append("- 10 Maximale : opérateurs de saisie, télévendeurs")
    lines.append("")

    # Aggregate statistics
    lines.append("## Statistiques agrégées")
    lines.append("")

    total_demandeurs = sum(r["demandeurs"] or 0 for r in records)
    total_offres = sum(r["offres"] or 0 for r in records)
    scored = [r for r in records if r["exposure"] is not None]
    avg_exposure = sum(r["exposure"] for r in scored) / len(scored) if scored else 0

    lines.append(f"- Total métiers : {len(records)}")
    lines.append(f"- Total demandeurs d'emploi : {total_demandeurs:,}".replace(",", " "))
    lines.append(f"- Total offres d'emploi : {total_offres:,}".replace(",", " "))
    lines.append(f"- Exposition moyenne à l'IA : {avg_exposure:.1f}/10")
    lines.append("")

    # Tier breakdown
    tiers = [
        ("Minimale (0-1)", 0, 1),
        ("Faible (2-3)", 2, 3),
        ("Modérée (4-5)", 4, 5),
        ("Élevée (6-7)", 6, 7),
        ("Très élevée (8-10)", 8, 10),
    ]
    lines.append("### Répartition par niveau d'exposition")
    lines.append("")
    lines.append("| Niveau | Métiers | Demandeurs | % demandeurs |")
    lines.append("|--------|---------|------------|--------------|")
    for name, lo, hi in tiers:
        group = [r for r in records if r["exposure"] is not None and lo <= r["exposure"] <= hi]
        dem = sum(r["demandeurs"] or 0 for r in group)
        pct = dem / total_demandeurs * 100 if total_demandeurs else 0
        lines.append(f"| {name} | {len(group)} | {fmt_number(dem)} | {pct:.1f}% |")
    lines.append("")

    # By salary band
    lines.append("### Exposition moyenne par tranche salariale")
    lines.append("")
    salary_bands = [
        ("<25K €", 0, 25000),
        ("25-35K €", 25000, 35000),
        ("35-50K €", 35000, 50000),
        ("50K+ €", 50000, float("inf")),
    ]
    lines.append("| Tranche | Exposition moy. | Métiers |")
    lines.append("|---------|----------------|---------|")
    for name, lo, hi in salary_bands:
        group = [r for r in records if r["salary"] and lo <= r["salary"] < hi and r["exposure"] is not None]
        if group:
            avg = sum(r["exposure"] for r in group) / len(group)
            lines.append(f"| {name} | {avg:.1f} | {len(group)} |")
    lines.append("")

    # By education
    lines.append("### Exposition moyenne par niveau d'éducation")
    lines.append("")
    edu_groups = [
        ("Sans diplôme / CAP-BEP", ["Sans diplôme", "CAP/BEP"]),
        ("Bac", ["Bac (Baccalauréat)"]),
        ("Bac+2", ["Bac+2 (BTS/DUT)"]),
        ("Bac+3", ["Bac+3 (Licence)"]),
        ("Bac+5 et plus", ["Bac+5 (Master/Ingénieur)", "Bac+8 (Doctorat)"]),
    ]
    lines.append("| Éducation | Exposition moy. | Métiers |")
    lines.append("|-----------|----------------|---------|")
    for name, matches in edu_groups:
        group = [r for r in records if r["education"] in matches and r["exposure"] is not None]
        if group:
            avg = sum(r["exposure"] for r in group) / len(group)
            lines.append(f"| {name} | {avg:.1f} | {len(group)} |")
    lines.append("")

    # Full table
    lines.append(f"## Tous les {len(records)} métiers")
    lines.append("")
    lines.append("Triés par exposition à l'IA (décroissant).")
    lines.append("")

    for score_val in range(10, -1, -1):
        group = [r for r in records if r["exposure"] == score_val]
        if not group:
            continue
        lines.append(f"### Exposition {score_val}/10 ({len(group)} métiers)")
        lines.append("")
        lines.append("| # | Métier | Salaire | Demandeurs | Offres | Éducation | Explication |")
        lines.append("|---|--------|---------|------------|--------|-----------|-------------|")
        for i, r in enumerate(group, 1):
            edu = r["education"] if r["education"] else "?"
            rationale = r["rationale"].replace("|", "/").replace("\n", " ")
            lines.append(f"| {i} | {r['title']} | {fmt_salary(r['salary'])} | {fmt_number(r['demandeurs'])} | {fmt_number(r['offres'])} | {edu} | {rationale} |")
        lines.append("")

    text = "\n".join(lines)
    with open("prompt_fr.md", "w", encoding="utf-8") as f:
        f.write(text)

    print(f"Wrote prompt_fr.md ({len(text):,} chars, {len(lines):,} lines)")


if __name__ == "__main__":
    main()
