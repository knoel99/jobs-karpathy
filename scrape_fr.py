"""
Scrape French occupation data from France Travail API (ROME 4.0).

Async implementation with rate-limited concurrency. ROME endpoints are limited
to 1 req/s, Marché du travail endpoints to 10 req/s. Multiple occupations are
fetched concurrently within these global rate limits.

Usage:
    uv run python scrape_fr.py                      # scrape all
    uv run python scrape_fr.py --start 0 --end 10   # scrape first 10
    uv run python scrape_fr.py --force               # re-scrape ignoring cache
    uv run python scrape_fr.py --concurrency 20      # max parallel occupations

Requires FRANCE_TRAVAIL_CLIENT_ID and FRANCE_TRAVAIL_CLIENT_SECRET in .env.
Register at https://francetravail.io/ to obtain API credentials.
"""

import argparse
import asyncio
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


class RateLimiter:
    """Token-bucket rate limiter for asyncio."""

    def __init__(self, rate: float):
        """rate: max requests per second."""
        self._min_interval = 1.0 / rate
        self._lock = asyncio.Lock()
        self._last = 0.0

    async def acquire(self):
        async with self._lock:
            now = asyncio.get_event_loop().time()
            wait = self._last + self._min_interval - now
            if wait > 0:
                await asyncio.sleep(wait)
            self._last = asyncio.get_event_loop().time()


# Global rate limiters (created in main)
rome_limiter: RateLimiter  # 1 req/s
marche_limiter: RateLimiter  # ~8 req/s (safe margin from 10)


class TokenManager:
    """Handle OAuth2 token lifecycle with proactive refresh."""

    def __init__(self, client_id, client_secret):
        self.client_id = client_id
        self.client_secret = client_secret
        self.token = None
        self.expires_at = 0.0
        self._lock = asyncio.Lock()

    async def get_token(self, client):
        """Get a valid token, refreshing if needed (tokens expire ~25 min)."""
        if self.token and time.time() < self.expires_at - 60:
            return self.token
        async with self._lock:
            # Double-check after acquiring lock
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
                response = await client.post(
                    TOKEN_URL,
                    params={"realm": "/partenaire"},
                    data=token_data,
                )
                if response.status_code == 200:
                    break
                print(f"\n  [TOKEN] Attempt {attempt+1} failed: {response.status_code} {response.text[:200]}")
                if attempt < 2:
                    await asyncio.sleep(2 ** attempt)
            response.raise_for_status()
            data = response.json()
            self.token = data["access_token"]
            self.expires_at = time.time() + data.get("expires_in", 1500)
            print(f"  [TOKEN] Refreshed (expires in {data.get('expires_in', '?')}s)")
            return self.token

    async def headers(self, client):
        return {
            "Authorization": f"Bearer {await self.get_token(client)}",
            "Accept": "application/json",
        }


def _parse_response(resp, url):
    """Parse JSON response, returning None on empty body."""
    if not resp.text.strip():
        return None
    try:
        return resp.json()
    except Exception:
        print(f"\n    [WARN] Non-JSON response from {url}: {resp.status_code} {resp.text[:200]}")
        return None


async def api_get(client, url, token_mgr, limiter, retries=3, delay=1.0):
    """GET with rate limiting and retry on 401/429/5xx."""
    for attempt in range(retries):
        try:
            await limiter.acquire()
            resp = await client.get(url, headers=await token_mgr.headers(client), timeout=30)
            if resp.status_code == 401:
                token_mgr.token = None
                await asyncio.sleep(delay)
                continue
            if resp.status_code == 429:
                wait = float(resp.headers.get("Retry-After", delay * (2 ** attempt)))
                await asyncio.sleep(wait)
                continue
            if resp.status_code >= 500:
                await asyncio.sleep(delay * (2 ** attempt))
                continue
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return _parse_response(resp, url)
        except httpx.TimeoutException:
            await asyncio.sleep(delay * (2 ** attempt))
    return None


async def api_post(client, url, token_mgr, json_body, limiter, retries=3, delay=1.0):
    """POST with rate limiting and retry on 401/429/5xx."""
    for attempt in range(retries):
        try:
            await limiter.acquire()
            resp = await client.post(url, headers=await token_mgr.headers(client), json=json_body, timeout=30)
            if resp.status_code == 401:
                token_mgr.token = None
                await asyncio.sleep(delay)
                continue
            if resp.status_code == 429:
                wait = float(resp.headers.get("Retry-After", delay * (2 ** attempt)))
                await asyncio.sleep(wait)
                continue
            if resp.status_code >= 500:
                await asyncio.sleep(delay * (2 ** attempt))
                continue
            if resp.status_code in (404, 400):
                return None
            resp.raise_for_status()
            return _parse_response(resp, url)
        except httpx.TimeoutException:
            await asyncio.sleep(delay * (2 ** attempt))
    return None


async def scrape_occupation(client, token_mgr, rome_code):
    """Fetch all data for one ROME occupation."""
    result = {}

    # 1. Fiche métier (ROME: 1 req/s)
    fiche = await api_get(client, f"{ROME_BASE}/fiche_metier/{rome_code}", token_mgr, rome_limiter)
    if fiche:
        result["fiche"] = fiche

    # 2. Métier info (ROME: 1 req/s)
    metier = await api_get(client, f"{ROME_METIERS_BASE}/metier/{rome_code}", token_mgr, rome_limiter)
    if metier:
        result["metier"] = metier

    # 3-6: Marché du travail endpoints (10 req/s) — can run in parallel
    salaires_task = api_get(
        client,
        f"{MARCHE_BASE}/v1/indicateur/salaire-rome-fap/NAT/FR?codeRome={rome_code}",
        token_mgr, marche_limiter,
    )
    demandeurs_task = api_post(
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
        limiter=marche_limiter,
    )
    offres_task = api_post(
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
        limiter=marche_limiter,
    )
    tensions_task = api_post(
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
        limiter=marche_limiter,
    )

    salaires, demandeurs, offres, tensions = await asyncio.gather(
        salaires_task, demandeurs_task, offres_task, tensions_task
    )
    if salaires:
        result["salaires"] = salaires
    if demandeurs:
        result["demandeurs"] = demandeurs
    if offres:
        result["offres"] = offres
    if tensions:
        result["tensions"] = tensions

    return result


async def process_one(client, token_mgr, i, occ, total, sem):
    """Process a single occupation with concurrency semaphore."""
    async with sem:
        rome_code = occ["code_rome"]
        slug = occ["slug"]
        path = f"html_fr/{slug}.json"

        try:
            data = await scrape_occupation(client, token_mgr, rome_code)
            with open(path, "w") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            sections = [k for k in data if data[k]]
            print(f"  [{i+1}/{total}] {occ['title']} ({rome_code}) OK ({len(sections)} sections)")
        except Exception as e:
            print(f"  [{i+1}/{total}] {occ['title']} ({rome_code}) ERROR: {e}")


async def async_main():
    global rome_limiter, marche_limiter

    parser = argparse.ArgumentParser(description="Scrape France Travail ROME data")
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--end", type=int, default=None)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--concurrency", type=int, default=10,
                        help="Max parallel occupations (default: 10)")
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

    # Rate limiters: ROME at 1 req/s, Marché at 8 req/s (safe margin from 10)
    rome_limiter = RateLimiter(rate=1.0)
    marche_limiter = RateLimiter(rate=8.0)

    # Bottleneck: 2 ROME calls/occupation at 1 req/s = ~0.5 occupations/s
    # With concurrency=10, ~10 occupations overlap their marché calls
    est_seconds = len(to_scrape) * 2  # ~2s per occupation (ROME is bottleneck)
    print(f"Scraping {len(to_scrape)} occupations (~{est_seconds/60:.0f} min estimated, concurrency={args.concurrency})")

    token_mgr = TokenManager(client_id, client_secret)
    sem = asyncio.Semaphore(args.concurrency)

    async with httpx.AsyncClient() as client:
        tasks = [
            process_one(client, token_mgr, i, occ, len(occupations), sem)
            for i, occ in to_scrape
        ]
        await asyncio.gather(*tasks)

    cached = len([f for f in os.listdir("html_fr") if f.endswith(".json")])
    print(f"\nDone. {cached}/{len(occupations)} JSON files in html_fr/")


if __name__ == "__main__":
    asyncio.run(async_main())
