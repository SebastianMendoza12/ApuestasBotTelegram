from telegram import Update
from telegram.ext import CommandHandler, ContextTypes


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await update.message.reply_html(
        f"¡Hola {user.mention_html()}! Bienvenido al Bot de Apuestas.\n\n"
        "Comandos disponibles:\n"
        "/balance - Consultar tu saldo\n"
        "/apostar &lt;monto&gt; &lt;equipo&gt; - Realizar una apuesta\n"
        "/ayuda - Mostrar ayuda"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Comandos disponibles:\n"
        "/start - Iniciar el bot\n"
        "/ayuda - Mostrar esta ayuda\n"
        "/balance - Consultar tu saldo\n"
        "/apostar &lt;monto&gt; &lt;equipo&gt; - Realizar una apuesta\n"
    )


start_handler = CommandHandler("start", start_command)
help_handler = CommandHandler("help", help_command)