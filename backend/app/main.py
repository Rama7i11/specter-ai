import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load .env from repo root BEFORE any app imports so os.getenv is populated
# when state.py and routers first access env vars.
load_dotenv(dotenv_path=Path(__file__).parents[2] / ".env")

import pathlib

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.routers import api, demo, hardware, voice, webhook

logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)

app = FastAPI(title="SPECTER-AI Backend", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(webhook.router)
app.include_router(hardware.router)
app.include_router(api.router)
app.include_router(voice.router)
app.include_router(demo.router)

static_dir = pathlib.Path(__file__).parent.parent / "static"
if static_dir.exists():
    app.mount(
        "/dashboards",
        StaticFiles(directory=str(static_dir), html=True),
        name="dashboards",
    )


@app.get("/health")
async def health():
    import time
    from app.services.state import START_TIME
    return {"status": "ok", "uptime": int(time.time() - START_TIME)}
