import logging
import sys
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from telegram.ext import Application

from app.core.config import settings
from app.core.database import db_manager, init_db
from app.telegram.bot import create_bot_application

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)

logger = logging.getLogger(__name__)

telegram_app: Application | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    global telegram_app

    logger.info("Iniciando aplicación...")

    logger.info("Inicializando base de datos...")
    await init_db()
    logger.info("Base de datos inicializada correctamente")

    logger.info("Creando aplicación del bot de Telegram...")
    telegram_app = create_bot_application()
    await telegram_app.initialize()
    await telegram_app.start()

    if settings.telegram_webhook_url:
        logger.info(f"Configurando webhook en {settings.telegram_webhook_url}")
        await telegram_app.bot.set_webhook(
            url=settings.telegram_webhook_url,
            secret_token=settings.telegram_webhook_secret,
            allowed_updates=settings.telegram_allowed_updates,
        )
    else:
        logger.info("Iniciando polling del bot...")
        await telegram_app.updater.start_polling(
            allowed_updates=settings.telegram_allowed_updates,
            drop_pending_updates=True,
        )

    logger.info("Aplicación iniciada correctamente")

    yield

    logger.info("Iniciando apagado de la aplicación...")

    if telegram_app:
        logger.info("Deteniendo aplicación del bot de Telegram...")
        await telegram_app.stop()
        await telegram_app.shutdown()

    logger.info("Cerrando conexiones de base de datos...")
    await db_manager.close()
    logger.info("Conexiones de base de datos cerradas")

    logger.info("Apagado de aplicación completado")


def create_application() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        description="API del Bot de Apuestas Telegram",
        version="1.0.0",
        debug=settings.debug,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.debug else [],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", tags=["Salud"])
    async def health_check() -> dict[str, str]:
        return {"status": "saludable", "service": settings.app_name}

    @app.get("/ready", tags=["Salud"])
    async def readiness_check() -> dict[str, str]:
        return {"status": "listo", "service": settings.app_name}

    return app


app = create_application()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )