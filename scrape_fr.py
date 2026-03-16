"""
Scrape French occupation data from France Travail API (ROME 4.0).

Uses OAuth2 client credentials to access the France Travail API and fetch
structured JSON data for each ROME occupation (fiches métier).

Usage:
    uv run python scrape_fr.py                      # scrape all
    uv run python scrape_fr.py --start 0 --end 10   # scrape first 10
    uv run python scrape_fr.py --force               # re-scrape ignoring cache

Requires FRANCE_TRAVAIL_CLIENT_ID and FRANCE_TRAVAIL_CLIENT_SECRET in .env.
Register at https://francetravail.io/ to obtain API credentials.
"""

import argparse
import json
import os
import time
import httpx
from dotenv import load_dotenv

load_dotenv()

# France Travail API endpoints
TOKEN_URL = "https://entreprise.francetravail.fr/connexion/oauth2/access_token"
ROME_BASE = "https://api.francetravail.io/partenaire/rome-fiches-metiers/v1/fiches_metiers"
ROME_METIERS_BASE = "https://api.francetravail.io/partenaire/rome-metiers/v1/metiers"
ROME_COMP_BASE = "https://api.francetravail.io/partenaire/rome-competences/v1/competences"
MARCHE_BASE = "https://api.francetravail.io/partenaire/stats-offres-demandes-emploi"

# Rate limits: ROME = 1 req/sec, Marché du travail = 10 req/sec
ROME_DELAY = 1.1
MARCHE_DELAY = 0.15


class TokenManager:
    """Handle OAuth2 token lifecycle with proactive refresh."""

    def __init__(self, client_id, client_secret):
        self.client_id = client_id
        self.client_secret = client_secret
        self.token = None
        self.expires_at = 0

    def get_token(self, client):
        """Get a valid token, refreshing if needed (tokens expire ~25 min)."""
        if self.token and time.time() < self.expires_at - 60:
            return self.token
        token_data = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": " ".join([
                "api_rome-metiersv1",
                "api_rome-fiches-metiersv1",
                "api_rome-competencesv1",
                "api_stats-offres-demandes-emploiv1",
                "offresetdemandesemploi",
                "nomenclatureRome",
            ]),
        }
        for attempt in range(3):
            response = client.post(
                TOKEN_URL,
                params={"realm": "/partenaire"},
                data=token_data,
            )
            if response.status_code == 200:
                break
            print(f"\n  [TOKEN] Attempt {attempt+1} failed: {response.status_code} {response.text[:200]}")
            if attempt < 2:
                time.sleep(2 ** attempt)
        response.raise_for_status()
        data = response.json()
        self.token = data["access_token"]
        self.expires_at = time.time() + data.get("expires_in", 1500)
        print(f"  [TOKEN] Refreshed (expires in {data.get('expires_in', '?')}s)")
        return self.token

    def headers(self, client):
        return {"Authorization": f"Bearer {self.get_token(client)}"}


def api_get(client, url, token_mgr, retries=3, delay=1.0):
    """GET with retry on 401/429/5xx."""
    for attempt in range(retries):
        try:
            resp = client.get(url, headers=token_mgr.headers(client), timeout=30)
            if resp.status_code == 401:
                token_mgr.token = None  # force refresh
                time.sleep(delay)
                continue
            if resp.status_code == 429:
                wait = float(resp.headers.get("Retry-After", delay * (2 ** attempt)))
                time.sleep(wait)
                continue
            if resp.status_code >= 500:
                time.sleep(delay * (2 ** attempt))
                continue
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()
        except httpx.TimeoutException:
            time.sleep(delay * (2 ** attempt))
    return None


def api_post(client, url, token_mgr, json_body, retries=3, delay=1.0):
    """POST with retry on 401/429/5xx."""
    for attempt in range(retries):
        try:
            resp = client.post(url, headers=token_mgr.headers(client), json=json_body, timeout=30)
            if resp.status_code == 401:
                token_mgr.token = None
                time.sleep(delay)
                continue
            if resp.status_code == 429:
                wait = float(resp.headers.get("Retry-After", delay * (2 ** attempt)))
                time.sleep(wait)
                continue
            if resp.status_code >= 500:
                time.sleep(delay * (2 ** attempt))
                continue
            if resp.status_code in (404, 400):
                return None
            resp.raise_for_status()
            return resp.json()
        except httpx.TimeoutException:
            time.sleep(delay * (2 ** attempt))
    return None


def scrape_occupation(client, token_mgr, rome_code, slug):
    """Fetch all data for one ROME occupation."""
    result = {}

    # 1. Fiche métier complète (ROME Fiches métiers v1 : 1 req/s)
    fiche = api_get(client, f"{ROME_BASE}/fiche_metier/{rome_code}", token_mgr)
    if fiche:
        result["fiche"] = fiche
    time.sleep(ROME_DELAY)

    # 2. Métier info (ROME Métiers v1 : 1 req/s)
    metier = api_get(client, f"{ROME_METIERS_BASE}/metier/{rome_code}", token_mgr)
    if metier:
        result["metier"] = metier
    time.sleep(ROME_DELAY)

    # 3. Salaires nationaux par ROME (Marché du travail : 10 req/s)
    salaires = api_get(
        client,
        f"{MARCHE_BASE}/v1/indicateur/salaire-rome-fap/NAT/FR?codeRome={rome_code}",
        token_mgr,
    )
    if salaires:
        result["salaires"] = salaires
    time.sleep(MARCHE_DELAY)

    # 4. Demandeurs d'emploi nationaux (POST, Marché du travail : 10 req/s)
    demandeurs = api_post(
        client,
        f"{MARCHE_BASE}/v1/indicateur/stat-demandeurs",
        token_mgr,
        json_body={
            "codeTypeTerritoire": "NAT",
            "codeTerritoire": "FR",
            "codeTypeActivite": "ROME",
            "codeActivite": rome_code,
            "codeTypePeriode": "TRIMESTRE",
            "codeTypeNomenclature": "CATCAND",
            "dernierePeriode": True,
        },
    )
    if demandeurs:
        result["demandeurs"] = demandeurs
    time.sleep(MARCHE_DELAY)

    # 5. Offres d'emploi (POST, Marché du travail : 10 req/s)
    offres = api_post(
        client,
        f"{MARCHE_BASE}/v1/indicateur/stat-offres",
        token_mgr,
        json_body={
            "codeTypeTerritoire": "NAT",
            "codeTerritoire": "FR",
            "codeTypeActivite": "ROME",
            "codeActivite": rome_code,
            "codeTypePeriode": "TRIMESTRE",
            "codeTypeNomenclature": "ORIGINEOFF",
            "dernierePeriode": True,
        },
    )
    if offres:
        result["offres"] = offres
    time.sleep(MARCHE_DELAY)

    # 6. Tensions de recrutement (POST, Marché du travail : 10 req/s)
    tensions = api_post(
        client,
        f"{MARCHE_BASE}/v1/indicateur/stat-perspective-employeur",
        token_mgr,
        json_body={
            "codeTypeTerritoire": "NAT",
            "codeTerritoire": "FR",
            "codeTypeActivite": "ROME",
            "codeActivite": rome_code,
            "codeTypePeriode": "ANNEE",
            "codeTypeNomenclature": "TYPE_TENSION",
            "dernierePeriode": True,
        },
    )
    if tensions:
        result["tensions"] = tensions
    time.sleep(MARCHE_DELAY)

    return result


def main():
    parser = argparse.ArgumentParser(description="Scrape France Travail ROME data")
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--end", type=int, default=None)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    client_id = os.environ.get("FRANCE_TRAVAIL_CLIENT_ID")
    client_secret = os.environ.get("FRANCE_TRAVAIL_CLIENT_SECRET")
    if not client_id or not client_secret:
        print("ERROR: Set FRANCE_TRAVAIL_CLIENT_ID and FRANCE_TRAVAIL_CLIENT_SECRET in .env")
        print("Register at https://francetravail.io/ to get API credentials.")
        return

    with open("occupations_fr.json") as f:
        occupations = json.load(f)

    end = args.end if args.end is not None else len(occupations)
    subset = occupations[args.start:end]

    os.makedirs("html_fr", exist_ok=True)

    to_scrape = []
    for i, occ in enumerate(subset, start=args.start):
        path = f"html_fr/{occ['slug']}.json"
        if not args.force and os.path.exists(path):
            continue
        to_scrape.append((i, occ))

    if not to_scrape:
        print("Nothing to scrape — all cached.")
        return

    est_time = len(to_scrape) * 6 * ROME_DELAY  # ~6 API calls per occupation
    print(f"Scraping {len(to_scrape)} occupations ({est_time/60:.0f} min estimated)")

    token_mgr = TokenManager(client_id, client_secret)
    client = httpx.Client()

    for idx, (i, occ) in enumerate(to_scrape):
        slug = occ["slug"]
        rome_code = occ["code_rome"]
        path = f"html_fr/{slug}.json"

        print(f"  [{i+1}/{len(occupations)}] {occ['title']} ({rome_code})...", end=" ", flush=True)

        try:
            data = scrape_occupation(client, token_mgr, rome_code, slug)
            with open(path, "w") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            sections = [k for k in data if data[k]]
            print(f"OK ({len(sections)} sections)")
        except Exception as e:
            print(f"ERROR: {e}")

    client.close()

    cached = len([f for f in os.listdir("html_fr") if f.endswith(".json")])
    print(f"\nDone. {cached}/{len(occupations)} JSON files in html_fr/")


if __name__ == "__main__":
    main()
