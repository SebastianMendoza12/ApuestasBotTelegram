from app.services.stats.client import get_match_stats


async def analyze_match(home_team: str, away_team: str) -> dict | None:
    return await get_match_stats(home_team, away_team)
