import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from html import escape

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
    ht = escape(simple["home_team"])
    aw = escape(simple["away_team"])
    sel = escape(simple["selection"])
    bm = _disp_bm(simple["bookmaker"])

    lines = [f"\U0001f3af <b>RECOMENDACION #{prediction_id}</b>"]
    lines.append("")
    lines.append(f"{se} <b>{ht} vs {aw}</b>")
    lines.append("")
    lines.append(f"\U0001f3af <b>Seleccion:</b> {sel}")
    lines.append(f"\U0001f4b0 <b>Cuota:</b> <code>@{simple['odds']}</code> ({bm})")
    lines.append(f"\u23f0 <b>Inicio:</b> {_colombia_time(simple['event_start_time'])}")

    stats = simple.get("stats")
    if stats:
        h_form = stats.get("home_form", "")
        a_form = stats.get("away_form", "")
        h_name = escape(stats.get("home_api_name", ht))
        a_name = escape(stats.get("away_api_name", aw))
        if h_form and a_form:
            lines.append(f"\U0001f4ca <b>Forma:</b> {h_name} ({h_form}) vs {a_name} ({a_form})")
        h2h = stats.get("h2h_record", "")
        if h2h:
            lines.append(f"\U0001f4ca <b>H2H:</b> {h2h}")

    lines.append("")
    lines.append(f"\U0001f4c8 <b>Analisis:</b> {escape(simple['reasoning'])}")

    if combined:
        bm_c = _disp_bm(combined["bookmaker"])
        lines.append("")
        lines.append(f"\U0001f4a5 <b>COMBINADA (x{combined['num_legs']}) {bm_c.upper()}</b>")
        for i, leg in enumerate(combined["legs"], 1):
            se2 = emoji_sport.get(leg["sport"], "\U0001f3b2")
            lht = escape(leg["home_team"])
            law = escape(leg["away_team"])
            lsel = escape(leg["selection"])
            short = lht if len(lht) <= 15 else lht[:12] + "..."
            lines.append(f"{i}.{se2} {short} vs {law[:12]}... \u2192 <b>{lsel}</b> <code>@{leg['odds']}</code>")
        lines.append("")
        lines.append(f"\U0001f4b0 <b>Total:</b> <code>@{combined['total_odds']}</code>")

    await application.bot.send_message(chat_id=chat_id, text="\n".join(lines), parse_mode="HTML")


async def send_results_summary(application: Application, results: list[dict]) -> None:
    if not results:
        return
    lines = ["\u2705 <b>RESULTADOS DEL DIA</b>", ""]
    won = 0
    lost = 0
    for r in results:
        ht = escape(r.get("home_team", ""))
        aw = escape(r.get("away_team", ""))
        sel = escape(r.get("selection", ""))
        if r["status"] == "won":
            won += 1
            lines.append(f"\u2705 {ht} vs {aw} \u2192 <b>{sel}</b> GANO")
        else:
            lost += 1
            lines.append(f"\u274c {ht} vs {aw} \u2192 <b>{sel}</b> PERDIO")
    lines.append("")
    lines.append(f"<b>Aciertos:</b> {won} | <b>Fallos:</b> {lost}")
    await application.bot.send_message(chat_id=settings.admin_telegram_id, text="\n".join(lines), parse_mode="HTML")


async def send_no_recommendation(application: Application) -> None:
    await application.bot.send_message(
        chat_id=settings.admin_telegram_id,
        text="no se encontraron recomendaciones disponibles en este momento",
        parse_mode="HTML",
    )