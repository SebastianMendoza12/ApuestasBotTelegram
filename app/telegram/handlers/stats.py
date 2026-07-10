import logging
from html import escape

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from app.core.config import settings
from app.core.database import db_manager
from app.models.prediction import Prediction, PredictionStatus

logger = logging.getLogger(__name__)


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user or user.id != settings.admin_telegram_id:
        await update.message.reply_text("No tienes permiso para usar este comando.")
        return

    from sqlalchemy import func, select
    from decimal import Decimal

    async with db_manager.session() as session:
        total = (await session.execute(
            select(func.count(Prediction.id)).where(Prediction.is_combined == False)
        )).scalar() or 0

        won = (await session.execute(
            select(func.count(Prediction.id)).where(
                Prediction.is_combined == False, Prediction.status == PredictionStatus.WON
            )
        )).scalar() or 0

        lost = (await session.execute(
            select(func.count(Prediction.id)).where(
                Prediction.is_combined == False, Prediction.status == PredictionStatus.LOST
            )
        )).scalar() or 0

        pending = (await session.execute(
            select(func.count(Prediction.id)).where(
                Prediction.is_combined == False, Prediction.status == PredictionStatus.PENDING
            )
        )).scalar() or 0

        recent = (await session.execute(
            select(Prediction)
            .where(Prediction.is_combined == False,
                   Prediction.status.in_([PredictionStatus.WON, PredictionStatus.LOST]))
            .order_by(Prediction.created_at.desc())
            .limit(20)
        )).scalars().all()

        streak = 0
        for p in recent:
            if p.status == PredictionStatus.WON:
                streak += 1
            else:
                break

        returned = (await session.execute(
            select(func.coalesce(func.sum(Prediction.units_returned), 0)).where(
                Prediction.is_combined == False, Prediction.status == PredictionStatus.WON
            )
        )).scalar() or Decimal("0")

    if total == 0:
        await update.message.reply_text("No hay predicciones registradas aun.")
        return

    pct = round(won / total * 100, 1)
    invested = Decimal(total) * Decimal("1.00")
    net = float(returned) - float(invested)
    roi = round(net / float(invested) * 100, 1) if invested > 0 else 0

    sign = "+" if net >= 0 else ""
    roi_sign = "+" if roi >= 0 else ""

    message = (
        "<b>ESTADISTICAS</b>\n\n"
        f"<b>Total predicciones:</b> {total}\n"
        f"<b>Aciertos:</b> {won}\n"
        f"<b>Fallos:</b> {lost}\n"
        f"<b>Pendientes:</b> {pending}\n"
        f"<b>Porcentaje:</b> {pct}%\n"
        f"<b>Racha actual:</b> {streak}\n"
        f"<b>Ganancia neta:</b> {sign}{net:.2f} unidades\n"
        f"<b>ROI:</b> {roi_sign}{roi}%"
    )

    await update.message.reply_text(message, parse_mode="HTML")


stats_handler = CommandHandler("stats", stats_command)
