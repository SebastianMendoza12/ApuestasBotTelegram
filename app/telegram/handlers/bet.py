from decimal import Decimal

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from app.core.database import db_manager

bet_handlers: list[CommandHandler] = []


async def bet_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user

    if len(context.args) < 2:
        await update.message.reply_text(
            "Uso: /apostar &lt;monto&gt; &lt;equipo&gt;\n"
            "Ejemplo: /apostar 100 TeamA"
        )
        return

    try:
        amount = Decimal(context.args[0])
    except Exception:
        await update.message.reply_text("Monto inválido. Por favor ingresa un número válido.")
        return

    if amount <= 0:
        await update.message.reply_text("El monto debe ser mayor a cero.")
        return

    selection = " ".join(context.args[1:])

    async with db_manager.session() as session:
        from app.services.user.service import UserService
        service = UserService(session)
        db_user = await service.get_or_create(
            telegram_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            language_code=user.language_code,
            is_bot=user.is_bot,
        )

        if db_user.balance < amount:
            await update.message.reply_text(
                f"Saldo insuficiente. Tienes ${db_user.balance:,.2f}."
            )
            return

        await service.update_balance(db_user.id, -amount)

    await update.message.reply_text(
        f"¡Apuesta realizada con éxito!\n"
        f"Monto: ${amount:,.2f}\n"
        f"Selección: {selection}"
    )


bet_handler = CommandHandler("apostar", bet_command)
bet_handlers.append(bet_handler)