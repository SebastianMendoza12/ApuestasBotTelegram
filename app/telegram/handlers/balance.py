from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from app.core.database import db_manager
from app.services.user.service import UserService


async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user

    async with db_manager.session() as session:
        service = UserService(session)
        db_user = await service.get_or_create(
            telegram_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            language_code=user.language_code,
            is_bot=user.is_bot,
        )

    await update.message.reply_text(
        f"Tu saldo actual: ${db_user.balance:,.2f}"
    )


balance_handler = CommandHandler("balance", balance_command)