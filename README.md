# Bot de Apuestas Telegram

Bot automatico que analiza cuotas en tiempo real de +70 casas de apuestas, combinado con estadisticas de equipos (forma, historial), y envia recomendaciones de apuestas simples y combinadas a Telegram.

## Stack Tecnologico

- **Backend**: FastAPI (asincrono, Python 3.12)
- **Bot**: python-telegram-bot v20+ (polling)
- **Base de Datos**: PostgreSQL + SQLAlchemy 2.0 (asincrono, Neon serverless)
- **Migraciones**: Alembic
- **Config**: Pydantic v2 Settings
- **APIs externas**: The Odds API (cuotas), api-football (estadisticas)
- **Cache**: archivo JSON con TTL de 6h
- **Despliegue**: Render (Web Service) + cron-job.org
- **Keep-alive**: endpoint `/ping` cada 10 min (7 AM - 11 PM Colombia)

## Caracteristicas

- Recomendaciones automaticas 2 veces al dia (8 AM y 5 PM Colombia)
- Deteccion de **value betting**: cuotas por encima del promedio del mercado
- Apuestas **simples** con analisis de valor
- Apuestas **combinadas** (hasta 5 piernas, misma casa, mercado h2h)
- Estadisticas de equipos: **forma** (G/E/P) e **historial H2H** via api-football
- Calculo de ROI, racha, unidades, % de aciertos
- Cache inteligente (6h TTL) para minimizar consumo de APIs
- Resultados verificables via endpoint `/cron/check`
- Sin dependencies externas de scheduler (todo via cron-job.org)

## Ventanas de Tiempo

Cada recomendacion cubre una ventana especifica para evitar overlaps:

| Turno | Horario | Eventos cubiertos (Colombia) |
|-------|---------|------------------------------|
| Manana | 8 AM | 10:00 - 18:59 |
| Tarde | 5 PM | 19:00 - 09:59 (+1) |

- `session=auto` (default): detecta el turno segun la hora actual en Colombia
- Se puede forzar con `?session=morning` o `?session=evening`

## Comandos de Telegram

- `/start` - Iniciar el bot
- `/help` - Mostrar ayuda
- `/ayuda` - Mostrar ayuda (alias)
- `/historial` - Ultimas 20 predicciones con estado
- `/stats` - Estadisticas: total, % aciertos, racha, unidades, ROI

## Endpoints de la API

### Salud
- `GET /health` - Health check (responde "ok")
- `GET /ready` - Readiness check (responde "ok")
- `GET /ping` - Keep-alive (responde "pong")

### Monitoreo
- `GET /bot-status` - Estado del bot (running, polling, username)

### Cron (protegidos con ?secret=)
- `GET /cron/odds?secret=<SECRET>&session=auto` - Obtener cuotas, analizar y enviar recomendacion
- `GET /cron/check?secret=<SECRET>` - Verificar resultados de predicciones pendientes

### Admin
- `POST /admin/reset?secret=<SECRET>` - Eliminar todas las predicciones y reiniciar contador

## Inicio Rapido (desarrollo local)

```bash
# Clonar
git clone <repo-url> && cd bot-apuestas-telegram

# Copiar config
cp .env.example .env
# Editar .env con tus credenciales (ver .env.example)

# Entorno virtual
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/Mac:
source .venv/bin/activate

# Dependencias
pip install -r requirements.txt

# Migraciones
alembic revision --autogenerate -m "v2_predictions"
alembic upgrade head

# Iniciar
uvicorn app.main:app --reload
```

## Variables de Entorno

Ver `.env.example` para todas las variables requeridas:

| Variable | Descripcion |
|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | Token del bot de @BotFather |
| `DATABASE_URL` | URL de conexion PostgreSQL (asyncpg) |
| `ODDS_API_KEY` | API key de the-odds-api.com |
| `FOOTBALL_API_KEY` | API key de api-football.com |
| `ADMIN_TELEGRAM_ID` | Tu ID de Telegram (para recibir recomendaciones) |
| `CRON_SECRET` | Secreto para proteger endpoints cron |

## Despliegue en Render + cron-job.org

1. Subir a GitHub
2. Crear **Web Service** en Render (Docker)
3. Configurar **variables de entorno** en Render (incluir FOOTBALL_API_KEY)
4. Puerto: `10000` (definido en Dockerfile)
5. Crear tareas en **cron-job.org** (timezone: Colombia UTC-5):
   - `*/10 7-23 * * *` → `https://<url>/ping`
   - `0 8 * * *` → `https://<url>/cron/odds?secret=<CRON_SECRET>`
   - `0 17 * * *` → `https://<url>/cron/odds?secret=<CRON_SECRET>`
   - `0 22 * * *` → `https://<url>/cron/check?secret=<CRON_SECRET>`

## Estructura del Proyecto

```
app/
  core/
    config.py         # Config (Pydantic v2 Settings)
    database.py       # SQLAlchemy async engine + session manager
  models/
    prediction.py     # Modelo Prediction (simple + combinada)
  services/
    odds/
      client.py       # Cliente async de The Odds API
      cache.py        # Cache JSON con TTL
    stats/
      client.py       # Cliente async de api-football (forma, h2h)
      analyzer.py     # Wrapper para analisis de stats
    strategy/
      engine.py       # Motor: deteccion de value + integracion de stats
  telegram/
    bot.py            # Creacion del bot, envio de mensajes
    handlers/
      start.py        # /start, /help, /ayuda
      historial.py    # /historial
      stats.py        # /stats
      __init__.py     # Registro de handlers
  main.py             # FastAPI + endpoints cron
Dockerfile            # Python 3.12-slim, uvicorn en puerto 10000
alembic/              # Migraciones de base de datos
```

## APIs Externas

### The Odds API (the-odds-api.com)
- Plan gratis: 500 creditos/mes
- Solo `soccer` activo (otros deportes comentados)
- Regiones: us, us2, uk, eu, au, fr, se (77 casas)
- Mercado: h2h

### Api-Football (api-football.com)
- Plan gratis: 100 requests/dia
- Uso estimado: ~18 requests/dia
- Funciones: obtener fixtures del dia, historial H2H (ultimos 5), forma de equipos
- Cache: 6h TTL para fixtures y H2H
