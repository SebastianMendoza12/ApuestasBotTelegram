import logging

from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(
        "Error al procesar la actualización %s: %s", update, context.error,
        exc_info=context.error,
    )

    if update and update.effective_message:
        await update.effective_message.reply_text(
            "Ocurrió un error inesperado. Por favor intenta de nuevo más tarde."
        )