"""
Web server for Donna - enables deployment on Render.

Provides:
- Health check endpoint for Render
- Runs Telegram bot in background
- Handles graceful shutdown
"""

import asyncio
import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from donna.telegram_bot import create_bot
from donna.scheduler import DonnaScheduler
from donna.config import get_settings

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Global references
bot_application = None
scheduler = None


async def start_bot():
    """Start the Telegram bot."""
    global bot_application
    
    bot_application = create_bot()
    await bot_application.initialize()
    await bot_application.start()
    await bot_application.updater.start_polling()
    logger.info("Telegram bot started!")


async def stop_bot():
    """Stop the Telegram bot."""
    global bot_application
    
    if bot_application:
        await bot_application.updater.stop()
        await bot_application.stop()
        await bot_application.shutdown()
        logger.info("Telegram bot stopped!")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle."""
    global scheduler
    
    # Startup
    logger.info("Starting Donna services...")
    
    # Start scheduler
    scheduler = DonnaScheduler()
    scheduler.start()
    
    # Start Telegram bot
    await start_bot()
    
    logger.info("Donna is ready!")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Donna...")
    await stop_bot()
    if scheduler:
        scheduler.stop()
    logger.info("Donna shut down gracefully.")


# Create FastAPI app
app = FastAPI(
    title="Donna - Personal Executive Assistant",
    description="I'm Donna. I know everything.",
    version="1.0.0",
    lifespan=lifespan
)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "Donna",
        "status": "I'm Donna. I know everything.",
        "version": "1.0.0"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint for Render."""
    return JSONResponse(
        status_code=200,
        content={
            "status": "healthy",
            "message": "I'm still here. Obviously."
        }
    )


@app.get("/status")
async def status():
    """Detailed status endpoint."""
    return {
        "bot": "running" if bot_application else "stopped",
        "scheduler": "running" if scheduler else "stopped",
        "personality": "Donna Paulsen",
        "sass_level": "maximum"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

