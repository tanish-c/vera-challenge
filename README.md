# Vera Bot

A small FastAPI service that serves the challenge bot endpoints.

## Endpoints

- `GET /v1/healthz`
- `GET /v1/metadata`
- `POST /v1/context`
- `POST /v1/tick`
- `POST /v1/reply`

## Local run

```bash
pip install -r requirements.txt
python bot.py
```

By default the app listens on `0.0.0.0:8000` when started directly.

## Deploy to Render

Use a **Web Service** with these settings:

- **Build command**: `pip install -r requirements.txt`
- **Start command**: `python bot.py`
- **Python version**: 3.11 or later

## Project layout

- `bot.py` - FastAPI app and endpoint handlers
- `composer.py` - message composition logic
- `requirements.txt` - runtime dependencies
- `Procfile` - process entry for hosting platforms
- `runtime.txt` - Python version pin

## Environment variables

Optional variables accepted by the app:

- `TEAM_MEMBERS` (defaults to Tanish Chhabra)
- `MODEL_NAME`
- `APPROACH`
- `CONTACT_EMAIL` (defaults to imtanish09@gmail.com)
- `BOT_VERSION`
- `SUBMITTED_AT`
