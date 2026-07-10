import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from statistics import mean

from app.services.stats.analyzer import analyze_match
from app.services.stats.client import get_fixtures_for_range, _match_team

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

    all_candidates = _get_all_candidates(all_events)
    if not all_candidates:
        return None

    fixtures = await get_fixtures_for_range(2)
    covered_candidates: list[dict] = []
    best_simple_covered = None
    best_simple_noncovered = None

    if fixtures:
        for c in all_candidates:
            home_info = _match_team(c["home_team"], fixtures)
            away_info = _match_team(c["away_team"], fixtures)
            if home_info and away_info:
                c["home_api_name"] = home_info[1]
                c["away_api_name"] = away_info[1]
                c["match_id"] = home_info[2]
                covered_candidates.append(c)

    # Try each covered candidate looking for one with H2H stats
    if covered_candidates:
        for c in covered_candidates:
            c["stats"] = await analyze_match(c["home_team"], c["away_team"])
            if c["stats"] and c["stats"].get("has_h2h"):
                best_simple_covered = c
                break
        # fallback: first covered even without H2H
        if not best_simple_covered:
            best_simple_covered = covered_candidates[0]

    # non-covered: conservative filter, pick best that is NOT the covered one
    noncovered = [
        c for c in all_candidates
        if c["odds"] <= 5.0 and c["odds"] >= 1.3
        and c["value_diff"] > 0.05 * c["avg_odds"]
        and (not best_simple_covered or c["event_id"] != best_simple_covered["event_id"])
    ]
    if noncovered:
        best_simple_noncovered = noncovered[0]
        best_simple_noncovered["note"] = "sin estadisticas (liga no cubierta)"

    if not best_simple_covered and not best_simple_noncovered:
        return None

    best_combined = None
    if best_simple_covered and best_simple_covered.get("stats"):
        best_combined = _build_best_combined(all_events, best_simple_covered)

    return {
        "simple_covered": best_simple_covered,
        "simple_noncovered": best_simple_noncovered,
        "combined": best_combined,
        "total_events_analyzed": len(all_events),
    }


def _get_all_candidates(events: list[dict]) -> list[dict]:
    candidates = []
    for event in events:
        all_outcomes: dict[str, list[dict]] = {}
        for bm in event["bookmakers"]:
            bm_key = bm.get("key", "").lower()
            for market in bm.get("markets", []):
                mk = market.get("key")
                if mk not in ("h2h", "spreads", "totals"):
                    continue
                for outcome in market.get("outcomes", []):
                    price = outcome.get("price")
                    if not price:
                        continue
                    sel = outcome.get("name", "")
                    point = outcome.get("point")
                    if mk in ("h2h", "spreads", "totals"):
                        pt = f"{point}" if point is not None else ""
                        group_key = f"{mk}|{sel}|{pt}"
                    entry = {"selection": sel, "price": Decimal(str(price)),
                             "market_key": mk, "bookmaker": bm_key,
                             "point": point}
                    all_outcomes.setdefault(group_key, []).append(entry)
        for group_key, outcomes in all_outcomes.items():
            if len(outcomes) < 2:
                continue
            avg_odds = mean(o["price"] for o in outcomes)
            for o in outcomes:
                if o["price"] > avg_odds * Decimal("1.02"):
                    confidence = float((o["price"] - avg_odds) / avg_odds * 100)
                    pt = o.get("point")
                    if pt is not None and o["market_key"] == "spreads":
                        pt_str = f" {pt:+.1f}"
                    elif pt is not None and o["market_key"] == "totals":
                        pt_str = f" {pt}"
                    else:
                        pt_str = ""
                    sel_full = f"{o['selection']}{pt_str}"
                    reasoning = (
                        f"cuota {o['price']:.2f} por encima del promedio "
                        f"{avg_odds:.2f} para {sel_full}"
                    )
                    candidates.append({
                        "sport": event["sport"],
                        "sport_emoji": event["sport_emoji"],
                        "league": event["league"],
                        "home_team": event["home_team"],
                        "away_team": event["away_team"],
                        "event_start_time": event["event_start_time"],
                        "event_id": event["event_id"],
                        "selection": sel_full,
                        "odds": float(o["price"]),
                        "bookmaker": o["bookmaker"],
                        "market": o["market_key"],
                        "market_key": o["market_key"],
                        "point": o.get("point"),
                        "confidence": round(confidence, 1),
                        "reasoning": reasoning,
                        "avg_odds": float(avg_odds),
                        "value_diff": float(o["price"] - avg_odds),
                    })
    if not candidates:
        return []
    candidates.sort(key=lambda x: x["value_diff"], reverse=True)
    return candidates


def _build_best_combined(events: list[dict], best_simple: dict | None) -> dict | None:
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