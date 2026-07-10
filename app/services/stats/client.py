import logging
from datetime import date, timedelta

import httpx

from app.core.config import settings
from app.services.odds.cache import cache

logger = logging.getLogger(__name__)

BASE_URL = settings.football_api_base_url
API_KEY = settings.football_api_key
HEADERS = {"X-Auth-Token": API_KEY} if API_KEY else {}


async def _fetch_matches(date_from: str, date_to: str) -> list[dict]:
    url = f"{BASE_URL}/matches"
    params = {"dateFrom": date_from, "dateTo": date_to}
    async with httpx.AsyncClient(timeout=15, headers=HEADERS) as client:
        r = await client.get(url, params=params)
        if r.status_code != 200:
            logger.warning("football-data error %s: %s", r.status_code, r.text[:200])
            return []
        data = r.json()
    return data.get("matches", [])


async def get_fixtures_for_range(num_days: int = 2) -> list[dict]:
    today = date.today()
    date_from = today.isoformat()
    date_to = (today + timedelta(days=num_days)).isoformat()
    cache_key = f"fd_matches_{date_from}_{date_to}"
    cached = cache.get(cache_key)
    if cached:
        return cached
    result = await _fetch_matches(date_from, date_to)
    if result:
        cache.set(cache_key, result)
    return result


def _match_team(odds_name: str, matches: list[dict]) -> tuple[int, str, int] | None:
    odds_lower = odds_name.lower().strip()
    for m in matches:
        for side in ("homeTeam", "awayTeam"):
            team = m.get(side, {})
            name = (team.get("name") or "").lower().strip()
            short = (team.get("shortName") or "").lower().strip()
            tla = (team.get("tla") or "").lower().strip()
            for candidate in (name, short, tla):
                if candidate and (candidate == odds_lower or candidate in odds_lower or odds_lower in candidate):
                    return team.get("id"), team.get("name", ""), m.get("id")
    return None


async def _fetch_h2h(match_id: int) -> list[dict]:
    url = f"{BASE_URL}/matches/{match_id}/head2head"
    async with httpx.AsyncClient(timeout=15, headers=HEADERS) as client:
        r = await client.get(url, params={"limit": 5})
        if r.status_code != 200:
            return []
        data = r.json()
    return data.get("matches", [])


def _build_stats(
    h2h_matches: list[dict],
    home_api_name: str,
    away_api_name: str,
) -> dict:
    home_form: list[str] = []
    away_form: list[str] = []
    h2h_list: list[str] = []
    home_wins = 0
    away_wins = 0
    draws = 0

    for m in h2h_matches:
        h_name = (m.get("homeTeam", {}).get("name") or "").lower()
        a_name = (m.get("awayTeam", {}).get("name") or "").lower()
        score = m.get("score", {}).get("fullTime", {})
        g_home = score.get("home")
        g_away = score.get("away")
        if g_home is None or g_away is None:
            continue
        is_home_home = h_name == home_api_name.lower()
        if is_home_home:
            hg, ag = int(g_home), int(g_away)
            h2h_list.append(f"{home_api_name} {hg}-{ag} {away_api_name}")
        else:
            hg, ag = int(g_away), int(g_home)
            h2h_list.append(f"{away_api_name} {ag}-{hg} {home_api_name}")
        if hg > ag:
            home_form.append("G")
            away_form.append("P")
            home_wins += 1
        elif ag > hg:
            home_form.append("P")
            away_form.append("G")
            away_wins += 1
        else:
            home_form.append("E")
            away_form.append("E")
            draws += 1

    home_form_str = "".join(home_form)
    away_form_str = "".join(away_form)

    return {
        "home_form": home_form_str or "",
        "away_form": away_form_str or "",
        "h2h_record": f"{home_wins}-{draws}-{away_wins}",
        "h2h_matches": h2h_list,
        "home_api_name": home_api_name,
        "away_api_name": away_api_name,
        "has_h2h": bool(h2h_matches),
    }


async def get_match_stats(home_team: str, away_team: str) -> dict | None:
    if not API_KEY:
        return None
    try:
        fixtures = await get_fixtures_for_range(2)
        if not fixtures:
            return None
        home_info = _match_team(home_team, fixtures)
        away_info = _match_team(away_team, fixtures)
        if not home_info or not away_info:
            logger.info("no se encontraron equipos: %s vs %s", home_team, away_team)
            return None
        home_id, home_api_name, match_id = home_info
        away_id, away_api_name, _ = away_info
        cache_key = f"fd_h2h_{home_id}_{away_id}"
        cached = cache.get(cache_key)
        if cached:
            return cached
        h2h_matches = await _fetch_h2h(match_id)
        result = _build_stats(h2h_matches, home_api_name, away_api_name)
        cache.set(cache_key, result)
        return result
    except Exception as e:
        logger.warning("error obteniendo stats de %s vs %s: %s", home_team, away_team, e)
        return None
