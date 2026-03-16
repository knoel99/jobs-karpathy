"""
Build a compact JSON for the French website by merging CSV stats with AI exposure scores.

Reads occupations_fr.csv and scores_fr.json, writes site_fr/data.json.

Usage:
    uv run python build_site_data_fr.py
"""

import csv
import json
import os


def main():
    # Load occupation metadata (for domain/subdomain hierarchy)
    with open("occupations_fr.json") as f:
        occ_list = json.load(f)
    occ_meta = {o["slug"]: o for o in occ_list}

    # Load AI exposure scores
    with open("scores_fr.json") as f:
        scores_list = json.load(f)
    scores = {s["slug"]: s for s in scores_list}

    # Load CSV stats (may not exist yet if pipeline not fully run)
    csv_rows = {}
    if os.path.exists("occupations_fr.csv"):
        with open("occupations_fr.csv", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                csv_rows[row["slug"]] = row

    # Merge
    data = []
    stats = {"salary": 0, "demandeurs": 0, "offres": 0, "tension": 0, "exposure": 0}

    for occ in occ_list:
        slug = occ["slug"]
        row = csv_rows.get(slug, {})
        score = scores.get(slug, {})
        meta = occ_meta.get(slug, {})

        salary = None
        if row.get("median_salary_annual"):
            try:
                salary = int(float(row["median_salary_annual"]))
                stats["salary"] += 1
            except ValueError:
                pass

        demandeurs = None
        if row.get("demandeurs"):
            try:
                demandeurs = int(row["demandeurs"])
                stats["demandeurs"] += 1
            except ValueError:
                pass

        offres = None
        if row.get("offres"):
            try:
                offres = int(row["offres"])
                stats["offres"] += 1
            except ValueError:
                pass

        tension = None
        if row.get("tension"):
            try:
                tension = int(float(row["tension"]))
                stats["tension"] += 1
            except ValueError:
                pass

        exposure = score.get("exposure")
        if exposure is not None:
            stats["exposure"] += 1

        entry = {
            "title": occ["title"],
            "slug": slug,
            "rome_code": occ["rome_code"],
            "domain": meta.get("domain", ""),
            "domain_code": meta.get("domain_code", ""),
            "subdomain": meta.get("subdomain", ""),
            "salary": salary,
            "demandeurs": demandeurs,
            "offres": offres,
            "tension": tension,
            "education": row.get("niveau_education", ""),
            "exposure": exposure,
            "exposure_rationale": score.get("rationale", ""),
        }
        data.append(entry)

    os.makedirs("site_fr", exist_ok=True)
    with open("site_fr/data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)

    print(f"Wrote {len(data)} métiers to site_fr/data.json")
    print(f"\nCouverture :")
    for key, count in stats.items():
        print(f"  {key}: {count}/{len(data)} ({count/len(data)*100:.0f}%)")


if __name__ == "__main__":
    main()
