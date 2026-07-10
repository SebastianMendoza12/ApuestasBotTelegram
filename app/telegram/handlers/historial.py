import logging
from html import escape

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from app.core.config import settings
from app.core.database import db_manager
from app.models.prediction import Prediction, PredictionStatus

logger = logging.getLogger(__name__)


async def historial_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user or user.id != settings.admin_telegram_id:
        await update.message.reply_text("No tienes permiso para usar este comando.")
        return

    from sqlalchemy import select
    async with db_manager.session() as session:
        result = await session.execute(
            select(Prediction)
            .where(Prediction.is_combined == False)
            .order_by(Prediction.created_at.desc())
            .limit(20)
        )
        predictions = result.scalars().all()

        total = len(predictions)
        won = sum(1 for p in predictions if p.status == PredictionStatus.WON)
        lost = sum(1 for p in predictions if p.status == PredictionStatus.LOST)

    if not predictions:
        await update.message.reply_text("No hay predicciones registradas aun.")
        return

    status_map = {
        PredictionStatus.PENDING: "\u23f3",
        PredictionStatus.WON: "\u2705",
        PredictionStatus.LOST: "\u274c",
        PredictionStatus.VOID: "\u26a0\ufe0f",
    }
    lines = []
    for p in predictions:
        s = status_map.get(p.status, "?")
        ht = escape(p.home_team or "")
        aw = escape(p.away_team or "")
        sel = escape(p.selection or "")
        lines.append(f"{s} <b>{ht}</b> vs <b>{aw}</b> \u2192 {sel} ({p.odds:.2f})")

    message = "\n".join(lines)
    pct = round(won / total * 100, 1) if total > 0 else 0
    message += f"\n\nStats: {won} ganadas | {lost} perdidas | {pct}% acierto"

    await update.message.reply_text(message, parse_mode="HTML")


historial_handler = CommandHandler("historial", historial_command)
