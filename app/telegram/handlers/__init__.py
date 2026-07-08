from telegram.ext import Application


def register_handlers(application: Application) -> None:
    from app.telegram.handlers.start import start_handler
    from app.telegram.handlers.balance import balance_handler
    from app.telegram.handlers.bet import bet_handlers
    from app.telegram.handlers.error import error_handler

    application.add_handler(start_handler)
    application.add_handler(balance_handler)
    for handler in bet_handlers:
        application.add_handler(handler)
    application.add_error_handler(error_handler)