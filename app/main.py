import logging
import sys
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from telegram.ext import Application

from app.core.config import settings
from app.core.database import db_manager, init_db
from app.telegram.bot import create_bot_application, send_recommendation, send_no_recommendation, send_results_summary

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

    logger.info("Iniciando aplicacion...")

    logger.info("Inicializando base de datos...")
    await init_db()
    logger.info("Base de datos inicializada correctamente")

    logger.info("Creando aplicacion del bot de Telegram...")
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

    logger.info("Aplicacion iniciada correctamente")

    yield

    logger.info("Iniciando apagado de la aplicacion...")

    if telegram_app:
        logger.info("Deteniendo aplicacion del bot de Telegram...")
        await telegram_app.stop()
        await telegram_app.shutdown()

    logger.info("Cerrando conexiones de base de datos...")
    await db_manager.close()
    logger.info("Conexiones de base de datos cerradas")

    logger.info("Apagado de aplicacion completado")


def _validate_cron_secret(secret: str) -> None:
    if secret != settings.cron_secret:
        raise HTTPException(status_code=403, detail="cron_secret invalido")


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

    @app.get("/cron/odds", tags=["Cron"])
    async def cron_odds(
        secret: str = Query(..., description="cron_secret"),
    ) -> dict:
        _validate_cron_secret(secret)

        from app.services.odds.client import get_odds
        from app.services.strategy.engine import analyze_and_recommend

        all_odds = {}
        sports = ["soccer", "tennis", "basketball", "table_tennis"]
        for sport in sports:
            try:
                data = await get_odds(sport)
                all_odds[sport] = data
            except Exception as e:
                logger.warning(f"Error obteniendo odds de {sport}: {e}")
                continue

        if not all_odds:
            if telegram_app:
                await send_no_recommendation(telegram_app)
            return {"status": "sin_datos", "detail": "no se pudieron obtener odds"}

        recommendation = analyze_and_recommend(all_odds)
        if recommendation and recommendation.get("simple"):
            if telegram_app:
                await send_recommendation(telegram_app, recommendation)
            return {
                "status": "ok",
                "total_events_analyzed": recommendation["total_events_analyzed"],
                "has_simple": True,
                "has_combined": recommendation.get("combined") is not None,
            }
        else:
            if telegram_app:
                await send_no_recommendation(telegram_app)
            return {"status": "sin_recomendaciones", "detail": "no se encontraron recomendaciones"}

    @app.get("/cron/check", tags=["Cron"])
    async def cron_check(
        secret: str = Query(..., description="cron_secret"),
    ) -> dict:
        _validate_cron_secret(secret)

        from datetime import UTC, datetime
        from sqlalchemy import select
        from app.models.prediction import Prediction, PredictionStatus

        async with db_manager.session() as session:
            result = await session.execute(
                select(Prediction)
                .where(Prediction.is_combined == False, Prediction.status == PredictionStatus.PENDING)
                .limit(50)
            )
            pending = result.scalars().all()

            if not pending:
                return {"status": "ok", "checked": 0, "results": []}

            from app.services.odds.client import get_scores

            sport_events: dict[str, list[str]] = {}
            for p in pending:
                sport_events.setdefault(p.sport, []).append(p.event_id)

            results = []
            for sport, event_ids in sport_events.items():
                try:
                    scores_data = await get_scores(sport, event_ids)
                except Exception as e:
                    logger.warning(f"Error obteniendo scores de {sport}: {e}")
                    continue

                for event in scores_data:
                    completed = event.get("completed")
                    scores = event.get("scores", [])
                    if not completed or not scores:
                        continue

                    event_id = event.get("id")
                    home_score = None
                    away_score = None
                    for s in scores:
                        if s.get("name") == event.get("home_team"):
                            home_score = s.get("score")
                        elif s.get("name") == event.get("away_team"):
                            away_score = s.get("score")

                    if home_score is None or away_score is None:
                        continue

                    for p in pending:
                        if p.event_id != event_id:
                            continue
                        pred_selection = p.selection.lower()
                        home_name = (p.home_team or "").lower()
                        away_name = (p.away_team or "").lower()

                        if pred_selection == home_name:
                            won = int(home_score) > int(away_score)
                        elif pred_selection == away_name:
                            won = int(away_score) > int(home_score)
                        else:
                            won = False

                        p.status = PredictionStatus.WON if won else PredictionStatus.LOST
                        p.units_returned = (p.odds * p.units_staked) if won else Decimal("0")
                        p.settled_at = datetime.now(UTC)

                        results.append({
                            "home_team": p.home_team,
                            "away_team": p.away_team,
                            "selection": p.selection,
                            "status": "won" if won else "lost",
                        })

            await session.flush()

        if results and telegram_app:
                await send_results_summary(telegram_app, results)

        return {"status": "ok", "checked": len(results), "results": results}

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