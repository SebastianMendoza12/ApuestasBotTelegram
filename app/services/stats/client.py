import logging
from datetime import date, datetime

import httpx

from app.core.config import settings
from app.services.odds.cache import cache

logger = logging.getLogger(__name__)

BASE_URL = settings.football_api_base_url
API_KEY = settings.football_api_key
HEADERS = {"x-apisports-key": API_KEY} if API_KEY else {}


async def get_today_fixtures() -> list[dict]:
    today = date.today().isoformat()
    cache_key = f"football_fixtures_{today}"
    cached = cache.get(cache_key)
    if cached:
        return cached
    url = f"{BASE_URL}/fixtures"
    params = {"date": today}
    async with httpx.AsyncClient(timeout=15, headers=HEADERS) as client:
        r = await client.get(url, params=params)
        if r.status_code != 200:
            logger.warning("api-football fixtures error: %s %s", r.status_code, r.text[:200])
            return []
        data = r.json()
    result = data.get("response", [])
    cache.set(cache_key, result)
    return result


def _match_team(odds_name: str, fixtures: list[dict]) -> tuple[int, str] | None:
    odds_lower = odds_name.lower().strip()
    for f in fixtures:
        for side in ("home", "away"):
            team = f.get("teams", {}).get(side, {})
            api_name = (team.get("name") or "").lower().strip()
            if api_name and (api_name == odds_lower or api_name in odds_lower or odds_lower in api_name):
                return team.get("id"), team.get("name", "")
    return None


async def get_match_stats(home_team: str, away_team: str) -> dict | None:
    if not API_KEY:
        return None
    try:
        fixtures = await get_today_fixtures()
        if not fixtures:
            return None
        home_info = _match_team(home_team, fixtures)
        away_info = _match_team(away_team, fixtures)
        if not home_info or not away_info:
            logger.info("no se encontraron equipos en api-football: %s vs %s", home_team, away_team)
            return None
        home_id, home_api_name = home_info
        away_id, away_api_name = away_info
        cache_key = f"h2h_{home_id}_{away_id}"
        cached = cache.get(cache_key)
        if cached:
            return cached
        url = f"{BASE_URL}/fixtures/headtohead"
        params = {"h2h": f"{home_id}-{away_id}", "last": 5}
        async with httpx.AsyncClient(timeout=15, headers=HEADERS) as client:
            r = await client.get(url, params=params)
            if r.status_code != 200:
                return None
            data = r.json()
        matches = data.get("response", [])
        result = _build_stats(matches, home_api_name, away_api_name)
        if result:
            cache.set(cache_key, result)
        return result
    except Exception as e:
        logger.warning("error obteniendo stats de %s vs %s: %s", home_team, away_team, e)
        return None


def _build_stats(matches: list[dict], home_api_name: str, away_api_name: str) -> dict:
    home_form: list[str] = []
    away_form: list[str] = []
    h2h: list[str] = []
    home_wins = 0
    away_wins = 0
    draws = 0
    for m in matches:
        home_team_name = (m.get("teams", {}).get("home", {}).get("name") or "").lower()
        away_team_name = (m.get("teams", {}).get("away", {}).get("name") or "").lower()
        is_home_home = home_team_name == home_api_name.lower()
        g_home = m.get("goals", {}).get("home")
        g_away = m.get("goals", {}).get("away")
        if g_home is None or g_away is None:
            continue
        if is_home_home:
            home_g = int(g_home)
            away_g = int(g_away)
        else:
            home_g = int(g_away)
            away_g = int(g_home)
        if home_g > away_g:
            home_form.append("G")
            away_form.append("P")
            h2h.append(f"{home_api_name} {home_g}-{away_g} {away_api_name}")
            home_wins += 1
        elif away_g > home_g:
            home_form.append("P")
            away_form.append("G")
            h2h.append(f"{away_api_name} {away_g}-{home_g} {home_api_name}")
            away_wins += 1
        else:
            home_form.append("E")
            away_form.append("E")
            h2h.append(f"empate {home_g}-{away_g}")
            draws += 1
    home_form_str = "".join(home_form)
    away_form_str = "".join(away_form)
    if not home_form_str and not away_form_str:
        return {}
    return {
        "home_form": home_form_str or "—",
        "away_form": away_form_str or "—",
        "h2h_record": f"{home_wins}-{draws}-{away_wins}",
        "h2h_matches": h2h,
        "home_api_name": home_api_name,
        "away_api_name": away_api_name,
    }
