"""
Build a CSV summary of French occupations from scraped France Travail API data.

Reads from html_fr/<slug>.json, writes to occupations_fr.csv.

Usage:
    uv run python make_csv_fr.py
"""

import csv
import json
import os
import re


def extract_salary(data):
    """Extract average annual net salary from France Travail salary data.

    Averages SAL3 (or SAL1 fallback) values across all FAP entries.
    Returns (annual, hourly) using 1607 hours/year (French legal standard).
    """
    salaires = data.get("salaires")
    if not salaires:
        return "", ""

    values = []
    entries = salaires if isinstance(salaires, list) else [salaires]
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        # Try SAL3 first (experienced), then SAL1 (entry-level)
        for key in ("SAL3", "salaireBrutMedian", "SAL1"):
            val = entry.get(key)
            if val:
                try:
                    values.append(float(val))
                except (ValueError, TypeError):
                    pass
                break

    if not values:
        return "", ""

    avg_annual = sum(values) / len(values)
    hourly = avg_annual / 1607  # 1607h = durée légale annuelle en France
    return str(round(avg_annual)), f"{hourly:.2f}"


def extract_demandeurs(data):
    """Extract jobseeker count (categories ABC = DEFM officiel)."""
    demandeurs = data.get("demandeurs")
    if not demandeurs:
        return ""

    entries = demandeurs if isinstance(demandeurs, list) else [demandeurs]
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        # Look for ABC category (official DEFM figure)
        cat = str(entry.get("categorie", entry.get("codeTypologie", "")))
        if cat.upper() in ("ABC", "A,B,C", "DEFM_ABC"):
            val = entry.get("nbDemandeurs", entry.get("valeur", ""))
            if val:
                return str(val)

    # Fallback: sum categories A, B, C
    total = 0
    found = False
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        cat = str(entry.get("categorie", entry.get("codeTypologie", ""))).upper()
        if cat in ("A", "B", "C"):
            val = entry.get("nbDemandeurs", entry.get("valeur", 0))
            try:
                total += int(val)
                found = True
            except (ValueError, TypeError):
                pass
    return str(total) if found else ""


def extract_offres(data):
    """Sum total job postings across all periods."""
    offres = data.get("offres")
    if not offres:
        return ""

    entries = offres if isinstance(offres, list) else [offres]
    total = 0
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        val = entry.get("nbOffres", entry.get("valeur", 0))
        try:
            total += int(val)
        except (ValueError, TypeError):
            pass
    return str(total) if total else ""


def extract_tensions(data):
    """Extract primary tension indicator (PERSPECTIVE code, scale 1-5).

    Falls back to INT_EMB (hiring intensity) if PERSPECTIVE not found.
    Returns (tension_pct, tension_desc).
    """
    tensions = data.get("tensions")
    if not tensions:
        return "", ""

    entries = tensions if isinstance(tensions, list) else [tensions]
    descs = {1: "Très défavorable", 2: "Défavorable", 3: "Neutre",
             4: "Favorable", 5: "Très favorable"}

    # Look for PERSPECTIVE code first (rang 1-5)
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        code = str(entry.get("codeTypologie", entry.get("code", "")))
        if "PERSPECTIVE" in code.upper():
            val = entry.get("valeur", entry.get("rang", ""))
            if val:
                try:
                    return str(val), descs.get(int(float(val)), "")
                except (ValueError, TypeError):
                    return str(val), ""

    # Fallback: INT_EMB or any tension indicator
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        code = str(entry.get("codeTypologie", entry.get("code", "")))
        if "INT_EMB" in code.upper() or "TENSION" in code.upper():
            val = entry.get("valeur", entry.get("rang", ""))
            if val:
                return str(val), "Intensité embauche"

    return "", ""


def extract_niveau_education(data):
    """Parse education level from fiche métier access text.

    Prioritizes highest qualification mentioned (Bac+8 down to sans diplôme).
    """
    fiche = data.get("fiche", {})
    acces = fiche.get("accesEmploi", "")
    if not acces:
        acces = str(fiche)

    text = acces.lower()

    levels = [
        ("Bac+8 (Doctorat)", r"bac\s*\+\s*8|doctorat"),
        ("Bac+5 (Master/Ingénieur)", r"bac\s*\+\s*5|master|ingénieur|diplôme d'ingénieur"),
        ("Bac+3 (Licence)", r"bac\s*\+\s*3|licence|but\b"),
        ("Bac+2 (BTS/DUT)", r"bac\s*\+\s*2|bts|dut|deust"),
        ("Bac (Baccalauréat)", r"bac\b(?!\s*\+)|baccalauréat|bac pro|bac techno"),
        ("CAP/BEP", r"cap\b|bep\b|certificat d'aptitude"),
        ("Sans diplôme", r"sans diplôme|aucun diplôme|pas de diplôme|accessible sans"),
    ]

    for label, pattern in levels:
        if re.search(pattern, text):
            return label

    return ""


def extract_description(data):
    """Get job definition from fiche métier."""
    fiche = data.get("fiche", {})
    definition = fiche.get("definition", "")
    if definition:
        return definition[:200]
    return ""


def main():
    with open("occupations_fr.json") as f:
        occupations = json.load(f)

    fieldnames = [
        "title", "category", "slug", "code_rome",
        "salaire_median_annuel", "salaire_median_horaire",
        "niveau_education",
        "nombre_demandeurs", "nombre_offres",
        "tension_pct", "tension_desc",
        "description", "url",
    ]

    rows = []
    stats = {"salary": 0, "demandeurs": 0, "offres": 0, "tension": 0, "education": 0}
    missing = 0

    for occ in occupations:
        json_path = f"html_fr/{occ['slug']}.json"
        if not os.path.exists(json_path):
            missing += 1
            continue

        with open(json_path) as f:
            data = json.load(f)

        annual, hourly = extract_salary(data)
        demandeurs = extract_demandeurs(data)
        offres = extract_offres(data)
        tension_pct, tension_desc = extract_tensions(data)
        education = extract_niveau_education(data)

        if annual:
            stats["salary"] += 1
        if demandeurs:
            stats["demandeurs"] += 1
        if offres:
            stats["offres"] += 1
        if tension_pct:
            stats["tension"] += 1
        if education:
            stats["education"] += 1

        rows.append({
            "title": occ["title"],
            "category": occ.get("category", ""),
            "slug": occ["slug"],
            "code_rome": occ["code_rome"],
            "salaire_median_annuel": annual,
            "salaire_median_horaire": hourly,
            "niveau_education": education,
            "nombre_demandeurs": demandeurs,
            "nombre_offres": offres,
            "tension_pct": tension_pct,
            "tension_desc": tension_desc,
            "description": extract_description(data),
            "url": occ.get("url", ""),
        })

    with open("occupations_fr.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} rows to occupations_fr.csv (missing JSON: {missing})")
    print(f"\nCoverage:")
    for key, count in stats.items():
        print(f"  {key}: {count}/{len(rows)} ({count/len(rows)*100:.0f}%)")


if __name__ == "__main__":
    main()
