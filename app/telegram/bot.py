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
B = "\u2800"  # blank braille character for empty lines


def _colombia_time(iso_str: str) -> str:
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        co = dt + COLOMBIA_OFFSET
        return co.strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        return iso_str[:16].replace("T", " ")


COUNTRY_FLAGS: dict[str, str] = {
    "spain": "\U0001f1ea\U0001f1f8", "belgium": "\U0001f1e7\U0001f1ea",
    "france": "\U0001f1eb\U0001f1f7", "england": "\U0001f3f4\U000e0067\U000e0062\U000e0065\U000e006e\U000e0067\U000e007f",
    "germany": "\U0001f1e9\U0001f1ea", "italy": "\U0001f1ee\U0001f1f9",
    "portugal": "\U0001f1f5\U0001f1f9", "netherlands": "\U0001f1f3\U0001f1f1",
    "brazil": "\U0001f1e7\U0001f1f7", "argentina": "\U0001f1e6\U0001f1f7",
    "uruguay": "\U0001f1fa\U0001f1fe", "colombia": "\U0001f1e8\U0001f1f4",
    "mexico": "\U0001f1f2\U0001f1fd", "usa": "\U0001f1fa\U0001f1f8",
    "japan": "\U0001f1ef\U0001f1f5", "korea": "\U0001f1f0\U0001f1f7",
    "australia": "\U0001f1e6\U0001f1fa", "poland": "\U0001f1f5\U0001f1f1",
    "switzerland": "\U0001f1e8\U0001f1ed", "croatia": "\U0001f1ed\U0001f1f7",
    "denmark": "\U0001f1e9\U0001f1f0", "sweden": "\U0001f1f8\U0001f1ea",
    "norway": "\U0001f1f3\U0001f1f4", "turkey": "\U0001f1f9\U0001f1f7",
    "russia": "\U0001f1f7\U0001f1fa", "ukraine": "\U0001f1fa\U0001f1e6",
    "austria": "\U0001f1e6\U0001f1f9", "hungary": "\U0001f1ed\U0001f1fa",
    "serbia": "\U0001f1f7\U0001f1f8", "czech": "\U0001f1e8\U0001f1ff",
    "greece": "\U0001f1ec\U0001f1f7", "romania": "\U0001f1f7\U0001f1f4",
    "scotland": "\U0001f3f4\U000e0067\U000e0062\U000e0073\U000e0063\U000e0074\U000e007f",
    "wales": "\U0001f3f4\U000e0067\U000e0062\U000e0077\U000e006c\U000e0073\U000e007f",
    "ireland": "\U0001f1ee\U0001f1ea", "morocco": "\U0001f1f2\U0001f1e6",
    "senegal": "\U0001f1f8\U0001f1f3", "nigeria": "\U0001f1f3\U0001f1ec",
    "cameroon": "\U0001f1e8\U0001f1f2", "ghana": "\U0001f1ec\U0001f1ed",
    "egypt": "\U0001f1ea\U0001f1ec", "tunisia": "\U0001f1f9\U0001f1f3",
    "algeria": "\U0001f1e6\U0001f1eb", "ivory coast": "\U0001f1e8\U0001f1ee",
    "ecuador": "\U0001f1ea\U0001f1e8", "peru": "\U0001f1f5\U0001f1ea",
    "chile": "\U0001f1e8\U0001f1f1", "paraguay": "\U0001f1f5\U0001f1fe",
    "venezuela": "\U0001f1fb\U0001f1ea", "bolivia": "\U0001f1e7\U0001f1f4",
    "costa rica": "\U0001f1e8\U0001f1f7", "panama": "\U0001f1f5\U0001f1e6",
    "honduras": "\U0001f1ed\U0001f1f3", "jamaica": "\U0001f1ef\U0001f1f2",
    "canada": "\U0001f1e8\U0001f1e6", "china": "\U0001f1e8\U0001f1f3",
    "india": "\U0001f1ee\U0001f1f3", "saudi arabia": "\U0001f1f8\U0001f1e6",
    "iran": "\U0001f1ee\U0001f1f7", "qatar": "\U0001f1f6\U0001f1e6",
    "united arab emirates": "\U0001f1e6\U0001f1ea", "israel": "\U0001f1ee\U0001f1f1",
}


def _flag(team: str) -> str:
    for key, flag in COUNTRY_FLAGS.items():
        if key in team.lower().strip():
            return flag
    return ""


def _form_emoji(letter: str) -> str:
    return {"G": "\u2705", "E": "\u270d\ufe0f", "P": "\u274c"}.get(letter, letter)


def _build_bullets(simple: dict, is_covered: bool) -> list[str]:
    bullets = []
    if is_covered and simple.get("stats"):
        s = simple["stats"]
        hf = s.get("home_form", "")
        af = s.get("away_form", "")
        hn = s.get("home_api_name", simple["home_team"])
        an = s.get("away_api_name", simple["away_team"])
        if hf and af:
            h_emoji = "".join(_form_emoji(x) for x in hf)
            a_emoji = "".join(_form_emoji(x) for x in af)
            bullets.append(f"{hn} llega con forma {h_emoji} en sus ultimos {len(hf)} partidos")
            bullets.append(f"{an} llega con forma {a_emoji} en sus ultimos {len(af)} partidos")
        h2h = s.get("h2h_record", "")
        if h2h:
            bullets.append(f"Historial directo: {hn} domina {h2h} en los ultimos 5 duelos")
    if not is_covered:
        bullets.append("Sin estadisticas disponibles para esta liga")
        bullets.append("Apuesta conservadora basada en valor de cuota")
    avg = simple.get("avg_odds")
    odds = simple["odds"]
    if avg and avg > 0:
        bullets.append(f"Cuota {odds} por encima del promedio del mercado {avg:.2f}")
    return bullets


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
    simple_covered = recommendation.get("simple_covered")
    simple_noncovered = recommendation.get("simple_noncovered")
    combined = recommendation.get("combined")

    chat_id = settings.admin_telegram_id
    emoji_sport = {"soccer": "\u26bd", "tennis": "\U0001f3be", "basketball": "\U0001f3c0", "table_tennis": "\U0001f3d3"}
    lines = []
    pred_id = None

    if simple_covered:
        async with db_manager.session() as session:
            from sqlalchemy import select
            existing = (await session.execute(
                select(Prediction).where(
                    Prediction.event_id == simple_covered["event_id"],
                    Prediction.selection == simple_covered["selection"],
                    Prediction.bookmaker == simple_covered["bookmaker"],
                    Prediction.is_combined == False,
                    Prediction.status == PredictionStatus.PENDING,
                )
            )).scalars().first()
            if existing:
                logger.info("prediccion duplicada (covered), se omite: %s", existing.id)
            else:
                pred = Prediction(
                    sport=simple_covered["sport"],
                    league=simple_covered.get("league", ""),
                    home_team=simple_covered["home_team"],
                    away_team=simple_covered["away_team"],
                    event_start_time=datetime.fromisoformat(simple_covered["event_start_time"]),
                    market=simple_covered.get("market", "h2h"),
                    market_key=simple_covered.get("market_key", "h2h"),
                    selection=simple_covered["selection"],
                    odds=Decimal(str(simple_covered["odds"])),
                    bookmaker=simple_covered["bookmaker"],
                    event_id=simple_covered["event_id"],
                    is_combined=False,
                    confidence_score=simple_covered.get("confidence"),
                    reasoning=simple_covered.get("reasoning"),
                    status=PredictionStatus.PENDING,
                )
                session.add(pred)
                await session.flush()
                pred_id = pred.id

        se = emoji_sport.get(simple_covered["sport"], "\U0001f3b2")
        ht = simple_covered["home_team"]
        aw = simple_covered["away_team"]
        league = simple_covered.get("league", simple_covered["sport"])
        hf = _flag(ht)
        af = _flag(aw)
        sel = simple_covered["selection"]

        if pred_id:
            lines.append(f"<b>RECOMENDACION #{pred_id}</b> {se}")
        lines.append(B)
        lines.append(f"{hf} {escape(ht)} \U0001f19a {escape(aw)} {af}")
        lines.append(B)

        bullets = _build_bullets(simple_covered, True)
        for b in bullets:
            lines.append(f"\U0001f539 {escape(b)}")

        lines.append(B)
        lines.append(f"Nuestro pronostico: {escape(sel)} \U0001f929")
        lines.append(B)
        lines.append(f"Cuota: {simple_covered['odds']}")

    if simple_noncovered:
        async with db_manager.session() as session:
            from sqlalchemy import select
            existing = (await session.execute(
                select(Prediction).where(
                    Prediction.event_id == simple_noncovered["event_id"],
                    Prediction.selection == simple_noncovered["selection"],
                    Prediction.bookmaker == simple_noncovered["bookmaker"],
                    Prediction.is_combined == False,
                    Prediction.status == PredictionStatus.PENDING,
                )
            )).scalars().first()
            if not existing:
                pred = Prediction(
                    sport=simple_noncovered["sport"],
                    league=simple_noncovered.get("league", ""),
                    home_team=simple_noncovered["home_team"],
                    away_team=simple_noncovered["away_team"],
                    event_start_time=datetime.fromisoformat(simple_noncovered["event_start_time"]),
                    market=simple_noncovered.get("market", "h2h"),
                    market_key=simple_noncovered.get("market_key", "h2h"),
                    selection=simple_noncovered["selection"],
                    odds=Decimal(str(simple_noncovered["odds"])),
                    bookmaker=simple_noncovered["bookmaker"],
                    event_id=simple_noncovered["event_id"],
                    is_combined=False,
                    confidence_score=simple_noncovered.get("confidence"),
                    reasoning=simple_noncovered.get("reasoning"),
                    status=PredictionStatus.PENDING,
                )
                session.add(pred)
                await session.flush()

        se = emoji_sport.get(simple_noncovered["sport"], "\U0001f3b2")
        ht = simple_noncovered["home_team"]
        aw = simple_noncovered["away_team"]
        hf = _flag(ht)
        af = _flag(aw)
        sel = simple_noncovered["selection"]

        lines.append("")
        lines.append(f"\u26a0\ufe0f <b>ADICIONAL</b> {se}")
        lines.append(B)
        lines.append(f"{hf} {escape(ht)} \U0001f19a {escape(aw)} {af}")
        lines.append(B)

        bullets = _build_bullets(simple_noncovered, False)
        for b in bullets:
            lines.append(f"\U0001f539 {escape(b)}")

        lines.append(B)
        lines.append(f"Nuestro pronostico: {escape(sel)} \U0001f929")
        lines.append(B)
        lines.append(f"Cuota: {simple_noncovered['odds']}")

    if combined:
        async with db_manager.session() as session:
            from sqlalchemy import select
            existing_parent = (await session.execute(
                select(Prediction).where(
                    Prediction.event_id == combined["legs"][0]["event_id"],
                    Prediction.selection == combined["legs"][0]["selection"],
                    Prediction.is_combined == True,
                    Prediction.status == PredictionStatus.PENDING,
                )
            )).scalars().first()
            if not existing_parent:
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
                        parent_prediction_id=parent.id,
                        status=PredictionStatus.PENDING,
                    )
                    session.add(child)

        lines.append("")
        lines.append(f"\U0001f525 <b>COMBINADA x{combined['num_legs']}</b>")
        lines.append(B)
        for i, leg in enumerate(combined["legs"], 1):
            se2 = emoji_sport.get(leg["sport"], "\U0001f3b2")
            lht = escape(leg["home_team"])
            law = escape(leg["away_team"])
            lsel = escape(leg["selection"])
            lines.append(f"{i}. {se2} {lht} vs {law} \u2192 {lsel} ({leg['odds']})")
        lines.append(B)
        lines.append(f"Cuota total: {combined['total_odds']}")

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