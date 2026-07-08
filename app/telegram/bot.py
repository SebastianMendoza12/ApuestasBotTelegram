from telegram.ext import Application, ApplicationBuilder, Defaults
from telegram.request import HTTPXRequest

from app.core.config import settings
from app.telegram.handlers import register_handlers
from app.telegram.middlewares import register_middlewares


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

    register_middlewares(application)
    register_handlers(application)

    return application