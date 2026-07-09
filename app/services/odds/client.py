import logging
from datetime import UTC, datetime
from typing import Any

import httpx

from app.core.config import settings
from app.services.odds.cache import cache

logger = logging.getLogger(__name__)

BASE_URL = settings.odds_api_base_url
API_KEY = settings.odds_api_key
SPORTS = ["soccer", "tennis", "basketball", "table_tennis"]
BOOKMAKERS = "betano,betplay,codere"
REGION = "eu"
MARKETS = "h2h,totals"


def _sport_key(sport_name: str) -> str:
    mapping = {
        "soccer": "soccer",
        "tennis": "tennis",
        "basketball": "basketball",
        "table_tennis": "table_tennis",
    }
    return mapping.get(sport_name, sport_name)


async def get_active_sports() -> list[dict]:
    url = f"{BASE_URL}/v4/sports"
    params = {"apiKey": API_KEY}
    cache_key = "active_sports"
    cached = cache.get(cache_key)
    if cached:
        return cached
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        data = response.json()
    cache.set(cache_key, data)
    return data


async def get_odds(sport_name: str) -> list[dict]:
    sport = _sport_key(sport_name)
    url = f"{BASE_URL}/v4/sports/{sport}/odds"
    params = {
        "apiKey": API_KEY,
        "regions": REGION,
        "markets": MARKETS,
        "bookmakers": BOOKMAKERS,
        "oddsFormat": "decimal",
    }
    cache_key = f"odds_{sport_name}"
    cached = cache.get(cache_key)
    if cached:
        return cached
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        data = response.json()
    cache.set(cache_key, data)
    return data


async def get_scores(sport_name: str, event_ids: list[str]) -> list[dict]:
    if not event_ids:
        return []
    sport_key = _sport_key(sport_name)
    url = f"{BASE_URL}/v4/sports/{sport_key}/scores"
    params = {
        "apiKey": API_KEY,
        "daysFrom": 2,
        "dateFormat": "iso",
    }
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        data = response.json()
    return [e for e in data if e.get("id") in event_ids]


def parse_upcoming_events(odds_data: list[dict]) -> list[dict]:
    now = datetime.now(UTC)
    events = []
    for event in odds_data:
        start_time = event.get("commence_time") or event.get("commence_time")
        events.append(event)
    return events


def extract_bookmaker_odds(bookmaker: dict, market_key: str = "h2h") -> list[dict]:
    outcomes = []
    for market in bookmaker.get("markets", []):
        if market.get("key") != market_key:
            continue
        for outcome in market.get("outcomes", []):
            outcomes.append({
                "market_key": market_key,
                "selection": outcome.get("name"),
                "price": outcome.get("price"),
                "point": outcome.get("point"),
            })
    return outcomes