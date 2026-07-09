import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.ext import ApplicationBuilder
from telegram.request import HTTPXRequest
from telegram.ext import Defaults

from app.core.config import settings
from app.core.database import db_manager
from app.models.prediction import Prediction, PredictionStatus
from app.telegram.handlers import register_handlers

logger = logging.getLogger(__name__)

COLOMBIA_OFFSET = timedelta(hours=-5)


def _colombia_time(iso_str: str) -> str:
    """Convierte ISO UTC a hora Colombia (UTC-5) para mostrar."""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        co = dt + COLOMBIA_OFFSET
        return co.strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        return iso_str[:16].replace("T", " ")

BOOKMAKER_DISPLAY: dict[str, str] = {
    "pinnacle": "Pinnacle", "betfair_ex_uk": "Betfair", "betfair_ex_eu": "Betfair",
    "betway": "Betway", "betvictor": "Bet Victor", "codere_it": "Codere",
    "unibet_uk": "Unibet", "unibet_fr": "Unibet", "unibet_nl": "Unibet",
    "unibet_se": "Unibet", "unibet_it": "Unibet", "unibet": "Unibet",
    "onexbet": "1xBet", "betsson": "Betsson", "marathonbet": "Marathonbet",
    "sport888": "888sport", "tipico_de": "Tipico", "winamax_de": "Winamax",
    "winamax_fr": "Winamax", "leovegas": "LeoVegas", "leovegas_se": "LeoVegas",
    "draftkings": "DraftKings", "fanduel": "FanDuel", "betmgm": "BetMGM",
    "betrivers": "BetRivers", "bovada": "Bovada", "williamhill": "William Hill",
    "ladbrokes_uk": "Ladbrokes", "ladbrokes_au": "Ladbrokes",
    "paddypower": "Paddy Power", "skybet": "Sky Bet", "betfred_uk": "Betfred",
    "bet365_au": "Bet365", "coolbet": "Coolbet", "suprabets": "Suprabets",
    "casumo": "Casumo", "coral": "Coral", "smarkets": "Smarkets",
    "matchbook": "Matchbook", "everygame": "Everygame", "mybookieag": "MyBookie",
    "betonlineag": "BetOnline", "betanysports": "BetAnySports", "gtbets": "GTbets",
    "nordicbet": "NordicBet", "boylesports": "BoyleSports", "virginbet": "Virgin Bet",
    "livescorebet": "LiveScore Bet", "grosvenor": "Grosvenor",
    "betus": "BetUS", "lowvig": "LowVig", "pointsbetau": "PointsBet",
    "sportsbet": "SportsBet", "tab": "TAB", "neds": "Neds",
    "betclic_fr": "Betclic", "pmu_fr": "PMU", "netbet_fr": "NetBet",
    "ballybet": "Bally Bet", "betparx": "betPARX", "espnbet": "ESPN Bet",
    "fliff": "Fliff", "hardrockbet": "Hard Rock Bet",
}


def _disp_bm(key: str) -> str:
    return BOOKMAKER_DISPLAY.get(key, key.replace("_", " ").title())


def create_bot_application() -> Application:
    request = HTTPXRequest(
        connection_pool_size=100,
        read_timeout=30,
        write_timeout=30,
        connect_timeout=30,
        pool_timeout=10,
    )

    defaults = Defaults(
        parse_mode="HTML",
        disable_notification=False,
    )

    application = (
        ApplicationBuilder()
        .token(settings.telegram_bot_token)
        .request(request)
        .defaults(defaults)
        .concurrent_updates(True)
        .build()
    )

    register_handlers(application)

    return application


async def send_recommendation(application: Application, recommendation: dict) -> None:
    simple = recommendation.get("simple")
    combined = recommendation.get("combined")
    if not simple:
        return

    chat_id = settings.admin_telegram_id

    async with db_manager.session() as session:
        pred = Prediction(
            sport=simple["sport"],
            league=simple.get("league", ""),
            home_team=simple["home_team"],
            away_team=simple["away_team"],
            event_start_time=datetime.fromisoformat(simple["event_start_time"]),
            market="h2h",
            market_key="h2h",
            selection=simple["selection"],
            odds=Decimal(str(simple["odds"])),
            bookmaker=simple["bookmaker"],
            event_id=simple["event_id"],
            is_combined=False,
            confidence_score=simple.get("confidence"),
            reasoning=simple.get("reasoning"),
            status=PredictionStatus.PENDING,
        )
        session.add(pred)
        await session.flush()
        prediction_id = pred.id

        if combined:
            parent = Prediction(
                sport=combined["legs"][0]["sport"],
                league="",
                home_team=combined["legs"][0]["home_team"],
                away_team=combined["legs"][0]["away_team"],
                event_start_time=datetime.fromisoformat(combined["legs"][0]["event_start_time"]),
                market="h2h",
                market_key="h2h",
                selection=combined["legs"][0]["selection"],
                odds=Decimal(str(combined["legs"][0]["odds"])),
                bookmaker=combined["bookmaker"],
                event_id=combined["legs"][0]["event_id"],
                is_combined=True,
                combined_legs=combined["num_legs"],
                combined_odds=Decimal(str(combined["total_odds"])),
                status=PredictionStatus.PENDING,
            )
            session.add(parent)
            await session.flush()
            combined_id = parent.id
            for leg in combined["legs"][1:]:
                child = Prediction(
                    sport=leg["sport"],
                    league="",
                    home_team=leg["home_team"],
                    away_team=leg["away_team"],
                    event_start_time=datetime.fromisoformat(leg["event_start_time"]),
                    market="h2h",
                    market_key="h2h",
                    selection=leg["selection"],
                    odds=Decimal(str(leg["odds"])),
                    bookmaker=leg["bookmaker"],
                    event_id=leg["event_id"],
                    is_combined=True,
                    parent_prediction_id=combined_id,
                    status=PredictionStatus.PENDING,
                )
                session.add(child)

    emoji_sport = {"soccer": "\u26bd", "tennis": "\U0001f3be", "basketball": "\U0001f3c0", "table_tennis": "\U0001f3d3"}
    se = emoji_sport.get(simple["sport"], "\U0001f3b2")

    lines = [f"\U0001f3af RECOMENDACION #{prediction_id}"]
    lines.append(f"{se} {simple['home_team']} vs {simple['away_team']}")
    lines.append(f"seleccion: {simple['selection']}")
    lines.append(f"cuota: @{simple['odds']} ({_disp_bm(simple['bookmaker'])})")
    lines.append(f"inicio: {_colombia_time(simple['event_start_time'])}")
    lines.append(f"\n\U0001f4c8 por que: {simple['reasoning']}")

    if combined:
        lines.append(f"\n\U0001f4af COMBINADA (x{combined['num_legs']}) {_disp_bm(combined['bookmaker']).upper()}")
        for i, leg in enumerate(combined["legs"], 1):
            se2 = emoji_sport.get(leg["sport"], "\U0001f3b2")
            lines.append(f"{i}. {se2} {leg['home_team']} vs {leg['away_team']} -> {leg['selection']} @ {leg['odds']}")
        lines.append(f"\U0001f4b0 cuota total: @{combined['total_odds']}")

    await application.bot.send_message(chat_id=chat_id, text="\n".join(lines))


async def send_results_summary(application: Application, results: list[dict]) -> None:
    if not results:
        return
    lines = ["\u2705 RESULTADOS DEL DIA"]
    won = 0
    lost = 0
    for r in results:
        if r["status"] == "won":
            won += 1
            lines.append(f"\u2705 {r['home_team']} vs {r['away_team']} -> {r['selection']} GANO")
        else:
            lost += 1
            lines.append(f"\u274c {r['home_team']} vs {r['away_team']} -> {r['selection']} PERDIO")
    lines.append(f"\naciertos: {won} | fallos: {lost}")
    await application.bot.send_message(chat_id=settings.admin_telegram_id, text="\n".join(lines))


async def send_no_recommendation(application: Application) -> None:
    await application.bot.send_message(
        chat_id=settings.admin_telegram_id,
        text="no se encontraron recomendaciones disponibles en este momento",
    )