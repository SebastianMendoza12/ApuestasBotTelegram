import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from statistics import mean

from app.services.stats.analyzer import analyze_match

logger = logging.getLogger(__name__)

COL_OFFSET = timedelta(hours=-5)


def _get_session_window(session: str | None = None) -> tuple[datetime, datetime]:
    """Retorna (inicio_utc, fin_utc) segun el turno.

    morning: eventos entre 10:00 y 18:59 Colombia (apostar 10am-7pm)
    evening: eventos entre 19:00 hoy y 09:59 manana Colombia (apostar 7pm-10am)
    """
    now_utc = datetime.now(UTC)
    col_now = now_utc + COL_OFFSET

    if session is None or session == "auto":
        session = "morning" if col_now.hour < 12 else "evening"

    if session == "morning":
        start_col = col_now.replace(hour=10, minute=0, second=0, microsecond=0)
        if col_now > start_col:
            start_col = col_now
        end_col = col_now.replace(hour=18, minute=59, second=59, microsecond=0)
    else:
        start_col = col_now.replace(hour=19, minute=0, second=0, microsecond=0)
        if col_now > start_col:
            start_col = col_now
        end_col = (col_now + timedelta(days=1)).replace(hour=9, minute=59, second=59, microsecond=0)

    return start_col - COL_OFFSET, end_col - COL_OFFSET

BOOKMAKER_NAMES: dict[str, str] = {
    "pinnacle": "Pinnacle",
    "betfair_ex_uk": "Betfair",
    "betfair_ex_eu": "Betfair",
    "betfair_sb_uk": "Betfair",
    "bet365_au": "Bet365",
    "betway": "Betway",
    "betvictor": "Bet Victor",
    "unibet_uk": "Unibet",
    "unibet_fr": "Unibet",
    "unibet_nl": "Unibet",
    "unibet_se": "Unibet",
    "unibet_it": "Unibet",
    "codere_it": "Codere",
    "onexbet": "1xBet",
    "betsson": "Betsson",
    "marathonbet": "Marathonbet",
    "sport888": "888sport",
    "tipico_de": "Tipico",
    "winamax_de": "Winamax",
    "winamax_fr": "Winamax",
    "leovegas": "LeoVegas",
    "leovegas_se": "LeoVegas",
    "draftkings": "DraftKings",
    "fanduel": "FanDuel",
    "betmgm": "BetMGM",
    "betrivers": "BetRivers",
    "bovada": "Bovada",
    "williamhill": "William Hill",
    "ladbrokes_uk": "Ladbrokes",
    "ladbrokes_au": "Ladbrokes",
    "paddypower": "Paddy Power",
    "skybet": "Sky Bet",
    "betfred_uk": "Betfred",
    "casumo": "Casumo",
    "coral": "Coral",
    "smarkets": "Smarkets",
    "matchbook": "Matchbook",
    "everygame": "Everygame",
    "mybookieag": "MyBookie",
    "betonlineag": "BetOnline",
    "betanysports": "BetAnySports",
    "gtbets": "GTbets",
    "nordicbet": "NordicBet",
    "boylesports": "BoyleSports",
    "virginbet": "Virgin Bet",
    "livescorebet": "LiveScore Bet",
    "grosvenor": "Grosvenor",
    "betus": "BetUS",
    "lowvig": "LowVig",
    "pointsbetau": "PointsBet",
    "sportsbet": "SportsBet",
    "tab": "TAB",
    "neds": "Neds",
    "betr_au": "Betr",
    "betright": "BetRight",
    "playup": "PlayUp",
    "tabtouch": "TABtouch",
    "betclic_fr": "Betclic",
    "pmu_fr": "PMU",
    "netbet_fr": "NetBet",
    "coolbet": "Coolbet",
    "suprabets": "Suprabets",
    "atg_se": "ATG",
    "betinia_se": "Betinia",
    "betmgm_se": "BetMGM",
    "campobet_se": "CampoBet",
    "expekt_se": "Expekt",
    "hajper_se": "Hajper",
    "mrgreen_se": "Mr Green",
    "svenskaspel_se": "Svenska Spel",
    "sport888_se": "888sport",
    "unibet": "Unibet",
    "ballybet": "Bally Bet",
    "betparx": "betPARX",
    "espnbet": "ESPN Bet",
    "fliff": "Fliff",
    "hardrockbet": "Hard Rock Bet",
    "rebet": "ReBet",
    "betfair_ex_au": "Betfair",
    "betr_au": "Betr",
    "bet365_au": "Bet365",
    "dabble_au": "Dabble",
}


def _bookmaker_name(key: str) -> str:
    return BOOKMAKER_NAMES.get(key, key.replace("_", " ").title())
SPORT_EMOJIS = {
    "soccer": "\u26bd",
    "tennis": "\U0001f3be",
    "basketball": "\U0001f3c0",
    "table_tennis": "\U0001f3d3",
}


async def analyze_and_recommend(all_odds: dict[str, list[dict]], session: str | None = None) -> dict | None:
    start_window, end_window = _get_session_window(session)
    now = datetime.now(UTC)
    all_events: list[dict] = []

    for sport_name, events in all_odds.items():
        emoji = SPORT_EMOJIS.get(sport_name, "\U0001f3b2")
        for event in events:
            start_time_str = event.get("commence_time")
            if not start_time_str:
                continue
            try:
                start_dt = datetime.fromisoformat(start_time_str.replace("Z", "+00:00"))
            except ValueError:
                continue
            if start_dt < start_window or start_dt > end_window:
                continue
            event_data = {
                "sport": sport_name,
                "sport_emoji": emoji,
                "league": event.get("sport_title", ""),
                "home_team": event.get("home_team"),
                "away_team": event.get("away_team"),
                "event_start_time": start_dt.isoformat(),
                "event_id": event.get("id"),
                "bookmakers": event.get("bookmakers", []),
            }
            all_events.append(event_data)

    if not all_events:
        return None

    best_simple = _find_best_simple(all_events)
    best_combined = _build_best_combined(all_events)

    if best_simple:
        stats = await analyze_match(best_simple["home_team"], best_simple["away_team"])
        if stats:
            best_simple["stats"] = stats
            home_f = stats.get("home_form", "")
            away_f = stats.get("away_form", "")
            h2h = stats.get("h2h_record", "")
            if home_f and away_f:
                sel = best_simple["selection"].lower()
                home = best_simple["home_team"].lower()
                forma_sel = home_f if sel == home else away_f
                best_simple["reasoning"] += (
                    f" | forma: {stats.get('home_api_name', best_simple['home_team'])} ({home_f}) "
                    f"vs {stats.get('away_api_name', best_simple['away_team'])} ({away_f})"
                )
                if h2h:
                    best_simple["reasoning"] += f" | historial: {h2h}"

    return {
        "simple": best_simple,
        "combined": best_combined,
        "total_events_analyzed": len(all_events),
    }


def _find_best_simple(events: list[dict]) -> dict | None:
    candidates = []
    for event in events:
        for bm in event["bookmakers"]:
            bm_key = bm.get("key", "").lower()
            for market in bm.get("markets", []):
                if market.get("key") != "h2h":
                    continue
                odds_list = []
                for outcome in market.get("outcomes", []):
                    price = outcome.get("price")
                    if not price:
                        continue
                    odds_list.append({
                        "selection": outcome.get("name"),
                        "price": Decimal(str(price)),
                        "market_key": "h2h",
                        "bookmaker": bm_key,
                    })
                if len(odds_list) < 2:
                    continue
                avg_odds = mean(o["price"] for o in odds_list)
                for o in odds_list:
                    if o["price"] > avg_odds * Decimal("1.02"):
                        confidence = float((o["price"] - avg_odds) / avg_odds * 100)
                        reasoning = (
                            f"cuota @{o['price']:.2f} por encima del promedio "
                            f"@{avg_odds:.2f} entre las casas disponibles"
                        )
                        candidates.append({
                            "sport": event["sport"],
                            "sport_emoji": event["sport_emoji"],
                            "league": event["league"],
                            "home_team": event["home_team"],
                            "away_team": event["away_team"],
                            "event_start_time": event["event_start_time"],
                            "event_id": event["event_id"],
                            "selection": o["selection"],
                            "odds": float(o["price"]),
                            "bookmaker": o["bookmaker"],
                            "market": "h2h",
                            "market_key": "h2h",
                            "confidence": round(confidence, 1),
                            "reasoning": reasoning,
                            "avg_odds": float(avg_odds),
                            "value_diff": float(o["price"] - avg_odds),
                        })
    if not candidates:
        return None
    candidates.sort(key=lambda x: x["value_diff"], reverse=True)
    return candidates[0]


def _build_best_combined(events: list[dict]) -> dict | None:
    best_simple = _find_best_simple(events)
    if not best_simple:
        return None

    best_bookmaker = best_simple["bookmaker"]
    legs = []

    for event in events:
        if len(legs) >= 5:
            break
        if event["event_id"] == best_simple["event_id"]:
            continue
        for bm in event["bookmakers"]:
            if bm.get("key", "") != best_bookmaker:
                continue
            for market in bm.get("markets", []):
                if market.get("key") != "h2h":
                    continue
                for outcome in market.get("outcomes", []):
                    price = outcome.get("price")
                    if not price:
                        continue
                    odds_val = Decimal(str(price))
                    legs.append({
                        "sport": event["sport"],
                        "sport_emoji": event["sport_emoji"],
                        "home_team": event["home_team"],
                        "away_team": event["away_team"],
                        "event_start_time": event["event_start_time"],
                        "selection": outcome.get("name"),
                        "odds": float(odds_val),
                        "bookmaker": best_bookmaker,
                        "market": "h2h",
                        "event_id": event["event_id"],
                    })
                    break
            if legs and len(legs) <= 5:
                break
        if len(legs) >= 5:
            break

    if len(legs) < 2:
        return None

    total_odds = 1.0
    for leg in legs:
        total_odds *= leg["odds"]
    total_odds = round(total_odds, 2)

    return {
        "bookmaker": best_bookmaker,
        "legs": legs[:5],
        "total_odds": total_odds,
        "num_legs": min(len(legs), 5),
    }