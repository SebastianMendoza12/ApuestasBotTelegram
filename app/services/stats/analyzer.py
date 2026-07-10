from app.services.stats.client import get_match_stats


async def analyze_match(home_team: str, away_team: str) -> dict | None:
    return await get_match_stats(home_team, away_team)


def stats_alignment_score(
    stats: dict | None,
    selection: str,
    home_team: str,
    away_team: str,
    market_key: str,
) -> float:
    """Que tan alineada esta una seleccion con las estadisticas reales del partido.

    Devuelve un valor 0..1 donde 0.5 = neutral (sin senal), >0.5 = las stats
    respaldan la seleccion, <0.5 = las stats la contradicen.
    Solo aplica a mercado h2h (moneyline), donde 'favorecer al equipo mejor
    parado' tiene sentido directo. Para spreads/totals no hay una lectura
    directa desde forma/H2H, asi que se devuelve neutral.
    """
    if not stats or market_key != "h2h":
        return 0.5

    diff = stats.get("combined_diff", 0.0)  # positivo favorece al local
    sel_lower = selection.lower().strip()
    home_lower = home_team.lower().strip()
    away_lower = away_team.lower().strip()

    if sel_lower == home_lower or sel_lower in home_lower or home_lower in sel_lower:
        alignment = diff
    elif sel_lower == away_lower or sel_lower in away_lower or away_lower in sel_lower:
        alignment = -diff
    elif "draw" in sel_lower or "empate" in sel_lower:
        # el empate es mas probable cuanto mas parejos esten los equipos
        alignment = 0.5 - abs(diff)
    else:
        return 0.5

    # normaliza aprox -1..1 -> 0..1
    score = 0.5 + max(-0.5, min(0.5, alignment))
    return round(score, 3)
