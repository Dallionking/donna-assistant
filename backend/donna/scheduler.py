"""
Automated scheduler for Donna.

Handles:
- Morning brief generation and Telegram delivery
- Periodic Calendly sync
- Evening summary and tomorrow planning
- Conflict detection and resolution
"""

import asyncio
import logging
from datetime import datetime, time
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from telegram import Bot

from donna.config import get_settings
from donna.tools.schedule import generate_daily_schedule
from donna.tools.calendly import get_calendly_events, check_calendly_conflicts
from donna.tools.voice import generate_morning_brief_voice
from donna.database import save_daily_schedule

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DonnaScheduler:
    """Automated task scheduler for Donna."""
    
    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.settings = get_settings()
        self.bot: Optional[Bot] = None
    
    async def initialize(self):
        """Initialize the scheduler and Telegram bot."""
        if self.settings.telegram_bot_token:
            self.bot = Bot(token=self.settings.telegram_bot_token)
        
        # Schedule tasks
        self._schedule_morning_brief()
        self._schedule_calendly_sync()
        self._schedule_evening_summary()
        
        logger.info("Donna scheduler initialized")
    
    def _schedule_morning_brief(self):
        """Schedule morning brief for 5:00 AM."""
        hour, minute = map(int, self.settings.donna_morning_brief_time.split(":"))
        
        self.scheduler.add_job(
            self.send_morning_brief,
            CronTrigger(hour=hour, minute=minute),
            id="morning_brief",
            name="Morning Brief",
            replace_existing=True,
        )
        
        logger.info(f"Morning brief scheduled for {hour:02d}:{minute:02d}")
    
    def _schedule_calendly_sync(self):
        """Schedule Calendly sync every N hours."""
        interval_hours = self.settings.donna_calendly_sync_interval_hours
        
        self.scheduler.add_job(
            self.sync_calendly,
            IntervalTrigger(hours=interval_hours),
            id="calendly_sync",
            name="Calendly Sync",
            replace_existing=True,
        )
        
        logger.info(f"Calendly sync scheduled every {interval_hours} hours")
    
    def _schedule_evening_summary(self):
        """Schedule evening summary for 9:00 PM."""
        self.scheduler.add_job(
            self.send_evening_summary,
            CronTrigger(hour=21, minute=0),
            id="evening_summary",
            name="Evening Summary",
            replace_existing=True,
        )
        
        logger.info("Evening summary scheduled for 21:00")
    
    async def send_morning_brief(self):
        """Generate and send the morning brief to Telegram with voice note."""
        import io
        logger.info("Generating morning brief...")
        
        try:
            # Generate today's schedule
            schedule = generate_daily_schedule.invoke({"date_str": None})
            
            # Build the brief
            today = datetime.now()
            brief = f"""Rise and shine. It's Donna.

I've already optimized your day, checked Calendly for conflicts, and made sure SigmaView gets the attention it deserves. You're welcome.

{schedule}

---

Now, before you start questioning my decisions:
• `/approve` - Smart move. Lock it in.
• `/adjust` - If you must. But I was right.
• `/braindump` - Got ideas? I'm listening.
• `/voice` - Hear me say it.

Don't be late. I hate late.
"""
            
            # Send to Telegram
            if self.bot and self.settings.telegram_chat_id:
                # Send text brief
                await self.bot.send_message(
                    chat_id=self.settings.telegram_chat_id,
                    text=brief,
                )
                logger.info("Morning brief text sent to Telegram")
                
                # Send voice note if ElevenLabs is configured
                if self.settings.elevenlabs_api_key and self.settings.elevenlabs_voice_id:
                    try:
                        audio_bytes = await generate_morning_brief_voice(schedule)
                        
                        if audio_bytes:
                            voice_file = io.BytesIO(audio_bytes)
                            voice_file.name = "morning_brief.mp3"
                            
                            await self.bot.send_voice(
                                chat_id=self.settings.telegram_chat_id,
                                voice=voice_file,
                                caption="Your morning brief. Now you can't say you didn't hear me."
                            )
                            logger.info("Morning brief voice note sent")
                    except Exception as voice_error:
                        logger.error(f"Failed to send voice morning brief: {voice_error}")
            else:
                logger.warning("Telegram not configured, skipping send")
            
        except Exception as e:
            logger.error(f"Error sending morning brief: {e}")
    
    async def sync_calendly(self):
        """Sync Calendly events and check for conflicts."""
        logger.info("Syncing Calendly events...")
        
        try:
            # Get upcoming Calendly events
            events = get_calendly_events.invoke({"days_ahead": 7})
            
            # Check today's conflicts
            today = datetime.now().strftime("%Y-%m-%d")
            conflicts = check_calendly_conflicts.invoke({"date_str": today})
            
            # If there are conflicts, notify via Telegram
            if "conflict" in conflicts.lower() and self.bot:
                await self.bot.send_message(
                    chat_id=self.settings.telegram_chat_id,
                    text=f"⚠️ Schedule Conflict Detected\n\n{conflicts}",
                )
            
            logger.info("Calendly sync complete")
            
        except Exception as e:
            logger.error(f"Error syncing Calendly: {e}")
    
    async def send_evening_summary(self):
        """Send evening summary and plan for tomorrow."""
        logger.info("Generating evening summary...")
        
        try:
            # Get today's date
            today = datetime.now()
            tomorrow = (today + timedelta(days=1)).strftime("%Y-%m-%d")
            
            # Generate tomorrow's schedule
            tomorrow_schedule = generate_daily_schedule.invoke({"date_str": tomorrow})
            
            summary = f"""Alright, that's enough for today.

I've already planned tomorrow. Obviously.

{tomorrow_schedule}

---

Now go rest. You'll need it - I've got a full day lined up for you.

• `/adjust` - Change tomorrow? Fine, but make it quick.
• `/braindump` - Last minute thoughts? Get them out now.

Good night. Don't make me come find you in the morning.
"""
            
            if self.bot and self.settings.telegram_chat_id:
                await self.bot.send_message(
                    chat_id=self.settings.telegram_chat_id,
                    text=summary,
                )
                logger.info("Evening summary sent to Telegram")
            
        except Exception as e:
            logger.error(f"Error sending evening summary: {e}")
    
    def start(self):
        """Start the scheduler."""
        self.scheduler.start()
        logger.info("Donna scheduler started")
    
    def stop(self):
        """Stop the scheduler."""
        self.scheduler.shutdown()
        logger.info("Donna scheduler stopped")


# Singleton scheduler instance
_scheduler: Optional[DonnaScheduler] = None


async def get_scheduler() -> DonnaScheduler:
    """Get or create the scheduler singleton."""
    global _scheduler
    if _scheduler is None:
        _scheduler = DonnaScheduler()
        await _scheduler.initialize()
    return _scheduler


async def start_scheduler():
    """Start the Donna scheduler."""
    from datetime import timedelta  # Import here to avoid circular import
    
    scheduler = await get_scheduler()
    scheduler.start()
    
    # Keep running
    try:
        while True:
            await asyncio.sleep(60)
    except KeyboardInterrupt:
        scheduler.stop()


if __name__ == "__main__":
    asyncio.run(start_scheduler())

