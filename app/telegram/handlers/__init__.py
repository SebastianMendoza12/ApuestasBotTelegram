from telegram.ext import Application


def register_handlers(application: Application) -> None:
    from app.telegram.handlers.start import start_handler, help_handler
    from app.telegram.handlers.historial import historial_handler
    from app.telegram.handlers.stats import stats_handler
    from app.telegram.handlers.error import error_handler

    application.add_handler(start_handler)
    application.add_handler(help_handler)
    application.add_handler(historial_handler)
    application.add_handler(stats_handler)
    application.add_error_handler(error_handler)