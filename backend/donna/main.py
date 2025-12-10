"""
Donna - Main Entry Point

Run this to start Donna's background services:
- Telegram bot
- Automated scheduler (morning briefs, Calendly sync)
"""

import asyncio
import logging
import sys

from donna.telegram_bot import run_bot
from donna.scheduler import start_scheduler

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger(__name__)


async def main():
    """Run Donna's background services."""
    logger.info("Starting Donna Personal Assistant...")
    
    # Run both the Telegram bot and scheduler concurrently
    await asyncio.gather(
        run_bot(),
        start_scheduler(),
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Donna shutting down...")


