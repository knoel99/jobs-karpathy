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
        for sal_key in ("salaire_median_annuel", "median_salary_annual"):
            if row.get(sal_key):
                try:
                    salary = int(float(row[sal_key]))
                    stats["salary"] += 1
                except ValueError:
                    pass
                break

        demandeurs = None
        for dem_key in ("nombre_demandeurs", "demandeurs"):
            if row.get(dem_key):
                try:
                    demandeurs = int(row[dem_key])
                    stats["demandeurs"] += 1
                except ValueError:
                    pass
                break

        offres = None
        for off_key in ("nombre_offres", "offres"):
            if row.get(off_key):
                try:
                    offres = int(row[off_key])
                    stats["offres"] += 1
                except ValueError:
                    pass
                break

        tension = None
        for ten_key in ("tension_pct", "tension"):
            if row.get(ten_key):
                try:
                    tension = int(float(row[ten_key]))
                    stats["tension"] += 1
                except ValueError:
                    pass
                break

        exposure = score.get("exposure")
        if exposure is not None:
            stats["exposure"] += 1

        tension_desc = row.get("tension_desc", "")
        entry = {
            "title": occ["title"],
            "slug": slug,
            "code_rome": occ["code_rome"],
            "domain_code": meta.get("domain_code", ""),
            "domain_name": meta.get("domain_name", meta.get("domain", "")),
            "subdomain_code": meta.get("subdomain_code", ""),
            "subdomain_name": meta.get("subdomain_name", meta.get("subdomain", "")),
            "category": meta.get("category", ""),
            "pay": salary,
            "demandeurs": demandeurs,
            "offres": offres,
            "tension": tension,
            "tension_desc": tension_desc,
            "education": row.get("niveau_education", ""),
            "exposure": exposure,
            "exposure_rationale": score.get("rationale", ""),
            "description": row.get("description", ""),
            "url": meta.get("url", row.get("url", "")),
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
