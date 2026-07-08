from telegram import Update
from telegram.ext import CommandHandler, ContextTypes


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await update.message.reply_html(
        f"!hola {user.mention_html()}! Soy tu Bot de Apuestas automatico.\n\n"
        "envio recomendaciones automaticas a las 8 AM y 5 PM.\n\n"
        "comandos:\n"
        "/historial - Ver historial de predicciones\n"
        "/stats - Ver estadisticas\n"
        "/ayuda - Mostrar ayuda"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "comandos disponibles:\n"
        "/start - Iniciar el bot\n"
        "/ayuda - Mostrar esta ayuda\n"
        "/historial - Ver historial de predicciones\n"
        "/stats - Ver estadisticas"
    )


start_handler = CommandHandler("start", start_command)
help_handler = CommandHandler("help", help_command)