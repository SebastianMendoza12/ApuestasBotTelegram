import asyncio
import logging
import time
from datetime import date, timedelta

import httpx

from app.core.config import settings
from app.services.odds.cache import cache

logger = logging.getLogger(__name__)

BASE_URL = settings.football_api_base_url
API_KEY = settings.football_api_key
HEADERS = {"X-Auth-Token": API_KEY} if API_KEY else {}

# football-data.org plan gratis: 10 req/min. Con forma real + H2H ahora se
# hacen hasta 3 llamadas por partido, asi que se espacian para no chocar
# con el limite y perder recomendaciones por 429 silenciosos.
_RATE_LOCK = asyncio.Lock()
_LAST_CALL_TS = 0.0
MIN_CALL_INTERVAL = 6.5  # segundos entre llamadas -> ~9.2 req/min, con margen


async def _throttle() -> None:
    global _LAST_CALL_TS
    async with _RATE_LOCK:
        now = time.monotonic()
        wait = MIN_CALL_INTERVAL - (now - _LAST_CALL_TS)
        if wait > 0:
            await asyncio.sleep(wait)
        _LAST_CALL_TS = time.monotonic()


async def _fetch_matches(date_from: str, date_to: str) -> list[dict]:
    url = f"{BASE_URL}/matches"
    params = {"dateFrom": date_from, "dateTo": date_to}
    await _throttle()
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
    await _throttle()
    async with httpx.AsyncClient(timeout=15, headers=HEADERS) as client:
        r = await client.get(url, params={"limit": 5})
        if r.status_code != 200:
            return []
        data = r.json()
    return data.get("matches", [])


async def _fetch_team_recent_matches(team_id: int, limit: int = 6) -> list[dict]:
    """Ultimos partidos JUGADOS del equipo (rendimiento real, independiente del rival)."""
    cache_key = f"fd_team_recent_{team_id}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    url = f"{BASE_URL}/teams/{team_id}/matches"
    params = {"status": "FINISHED", "limit": limit}
    await _throttle()
    async with httpx.AsyncClient(timeout=15, headers=HEADERS) as client:
        r = await client.get(url, params=params)
        if r.status_code != 200:
            logger.warning("football-data error %s (team matches %s): %s", r.status_code, team_id, r.text[:200])
            return []
        data = r.json()
    matches = data.get("matches", [])
    matches.sort(key=lambda m: m.get("utcDate", ""), reverse=True)
    cache.set(cache_key, matches)
    return matches


# G=3, E=1, P=0. Peso mayor para los partidos mas recientes (indice 0 = mas reciente).
_FORM_POINT = {"G": 3, "E": 1, "P": 0}
_FORM_WEIGHTS = [1.5, 1.3, 1.15, 1.0, 0.85, 0.7]


def _team_form_from_matches(team_id: int, matches: list[dict]) -> dict:
    letters: list[str] = []
    for m in matches:
        score = m.get("score", {}).get("fullTime", {})
        g_home, g_away = score.get("home"), score.get("away")
        if g_home is None or g_away is None:
            continue
        home_side = (m.get("homeTeam", {}) or {}).get("id") == team_id
        gf, ga = (g_home, g_away) if home_side else (g_away, g_home)
        if gf > ga:
            letters.append("G")
        elif gf < ga:
            letters.append("P")
        else:
            letters.append("E")

    weighted_sum = 0.0
    weight_total = 0.0
    for i, letter in enumerate(letters):
        w = _FORM_WEIGHTS[i] if i < len(_FORM_WEIGHTS) else 0.5
        weighted_sum += _FORM_POINT[letter] * w
        weight_total += 3 * w
    score = (weighted_sum / weight_total) if weight_total else 0.5

    return {"form_str": "".join(letters), "form_score": round(score, 3), "matches_count": len(letters)}


def _build_h2h(
    h2h_matches: list[dict],
    home_api_name: str,
    away_api_name: str,
) -> dict:
    h2h_list: list[str] = []
    home_wins = 0
    away_wins = 0
    draws = 0

    for m in h2h_matches:
        h_name = (m.get("homeTeam", {}).get("name") or "").lower()
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
            home_wins += 1
        elif ag > hg:
            away_wins += 1
        else:
            draws += 1

    total = home_wins + draws + away_wins
    h2h_diff = ((home_wins - away_wins) / total) if total else 0.0

    return {
        "h2h_record": f"{home_wins}-{draws}-{away_wins}",
        "h2h_matches": h2h_list,
        "h2h_diff": round(h2h_diff, 3),
        "has_h2h": bool(h2h_matches),
    }


def _extract_referee(fixtures: list[dict], match_id: int) -> str | None:
    for m in fixtures:
        if m.get("id") == match_id:
            refs = m.get("referees") or []
            names = [r.get("name") for r in refs if r.get("name")]
            return names[0] if names else None
    return None


HOME_ADVANTAGE = 0.04  # pequeno bonus estructural por jugar de local


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
        cache_key = f"fd_stats_v2_{home_id}_{away_id}"
        cached = cache.get(cache_key)
        if cached:
            return cached

        h2h_matches = await _fetch_h2h(match_id)
        h2h = _build_h2h(h2h_matches, home_api_name, away_api_name)

        home_recent = await _fetch_team_recent_matches(home_id)
        away_recent = await _fetch_team_recent_matches(away_id)
        home_form = _team_form_from_matches(home_id, home_recent)
        away_form = _team_form_from_matches(away_id, away_recent)

        home_strength = home_form["form_score"] + HOME_ADVANTAGE
        away_strength = away_form["form_score"]
        form_diff = home_strength - away_strength  # positivo favorece al local

        # combinado: 65% forma reciente real, 35% historial directo (H2H)
        combined_diff = round(0.65 * form_diff + 0.35 * h2h["h2h_diff"], 3)

        referee = _extract_referee(fixtures, match_id)

        result = {
            "home_api_name": home_api_name,
            "away_api_name": away_api_name,
            "home_form": home_form["form_str"],
            "away_form": away_form["form_str"],
            "home_form_score": home_form["form_score"],
            "away_form_score": away_form["form_score"],
            "home_form_matches": home_form["matches_count"],
            "away_form_matches": away_form["matches_count"],
            "combined_diff": combined_diff,
            "referee": referee,
            **h2h,
        }
        cache.set(cache_key, result)
        return result
    except Exception as e:
        logger.warning("error obteniendo stats de %s vs %s: %s", home_team, away_team, e)
        return None
