"""
Automated scheduler for Donna.

Handles:
- Morning brief generation and Telegram delivery
- Periodic Calendly sync
- Evening summary and tomorrow planning
- Conflict detection and resolution
"""

import asyncio
import io
import logging
from datetime import datetime, time, timedelta
from typing import Optional

import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from telegram import Bot

from donna.config import get_settings
from donna.tools.schedule import generate_daily_schedule
from donna.tools.voice import text_to_speech, clean_text_for_tts

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DonnaScheduler:
    """Automated task scheduler for Donna."""
    
    def __init__(self):
        self.settings = get_settings()
        self.timezone = pytz.timezone(self.settings.donna_timezone)
        
        # Create scheduler with timezone
        self.scheduler = AsyncIOScheduler(timezone=self.timezone)
        self.bot: Optional[Bot] = None
        
        logger.info(f"DonnaScheduler initialized with timezone: {self.settings.donna_timezone}")
    
    async def initialize(self):
        """Initialize the scheduler and Telegram bot."""
        if self.settings.telegram_bot_token:
            self.bot = Bot(token=self.settings.telegram_bot_token)
            logger.info("Telegram bot initialized for scheduler")
        
        # Schedule tasks
        self._schedule_morning_brief()
        self._schedule_calendly_sync()
        self._schedule_evening_summary()
        self._schedule_work_block_reminders()
        self._schedule_event_check()
        self._schedule_weekly_reviews()
        
        # Log all scheduled jobs
        logger.info("=" * 50)
        logger.info("Donna Scheduler Jobs:")
        for job in self.scheduler.get_jobs():
            logger.info(f"  - {job.name}: {job.trigger}")
        logger.info("=" * 50)
    
    def _schedule_work_block_reminders(self):
        """Schedule reminders at the start of each work block."""
        # Sigmavue block starts at 12:00 PM
        self.scheduler.add_job(
            self.remind_sigmavue_block,
            CronTrigger(hour=12, minute=0, timezone=self.timezone),
            id="sigmavue_reminder",
            name="Sigmavue Block Start",
            replace_existing=True,
        )
        
        # Break reminder at 3:00 PM
        self.scheduler.add_job(
            self.remind_break,
            CronTrigger(hour=15, minute=0, timezone=self.timezone),
            id="break_reminder",
            name="Break Reminder",
            replace_existing=True,
        )
        
        # Rotation block 1 at 3:30 PM
        self.scheduler.add_job(
            self.remind_rotation_block,
            CronTrigger(hour=15, minute=30, timezone=self.timezone),
            id="rotation1_reminder",
            name="Rotation Block 1",
            replace_existing=True,
        )
        
        logger.info("Work block reminders scheduled")
    
    def _schedule_event_check(self):
        """Schedule event check every 15 minutes for upcoming reminders."""
        self.scheduler.add_job(
            self.check_upcoming_events,
            IntervalTrigger(minutes=15),
            id="event_check",
            name="Upcoming Event Check",
            replace_existing=True,
        )
        logger.info("Event check scheduled every 15 minutes")
    
    def _schedule_weekly_reviews(self):
        """Schedule weekly review on Sunday and week ahead on Monday."""
        # Sunday 7 PM - Weekly Review
        self.scheduler.add_job(
            self.send_weekly_review,
            CronTrigger(
                day_of_week="sun",
                hour=19,
                minute=0,
                timezone=self.timezone
            ),
            id="weekly_review",
            name="Weekly Review (Sunday)",
            replace_existing=True,
        )
        
        # Monday 5 AM - Week Ahead Preview
        self.scheduler.add_job(
            self.send_week_ahead,
            CronTrigger(
                day_of_week="mon",
                hour=5,
                minute=0,
                timezone=self.timezone
            ),
            id="week_ahead",
            name="Week Ahead (Monday)",
            replace_existing=True,
        )
        
        logger.info("Weekly reviews scheduled: Sunday 7 PM, Monday 5 AM")
    
    async def remind_sigmavue_block(self):
        """Remind user that Sigmavue block is starting."""
        if self.bot and self.settings.telegram_chat_id:
            await self.bot.send_message(
                chat_id=self.settings.telegram_chat_id,
                text="⏰ **Sigmavue Time**\n\nIt's 12:00 PM. Your non-negotiable Sigmavue block starts now.\n\nFocus. No distractions. I'm watching."
            )
            logger.info("Sigmavue block reminder sent")
    
    async def remind_break(self):
        """Remind user to take a break."""
        if self.bot and self.settings.telegram_chat_id:
            await self.bot.send_message(
                chat_id=self.settings.telegram_chat_id,
                text="☕ **Break Time**\n\nIt's 3:00 PM. Step away from the screen.\n\nYou have 30 minutes. Use them wisely."
            )
            logger.info("Break reminder sent")
    
    async def remind_rotation_block(self):
        """Remind user about rotation block with project suggestion."""
        if self.bot and self.settings.telegram_chat_id:
            from donna.tools.projects import get_projects_needing_attention
            
            # Get projects needing attention
            projects_needing = get_projects_needing_attention.invoke({"days_threshold": 3})
            
            message = f"""🔄 **Rotation Block Started**

It's 3:30 PM. Time for project rotation.

{projects_needing if "Needing Attention" in projects_needing else "All projects are up to date. Pick your favorite."}

Focus for 90 minutes. You got this.
"""
            await self.bot.send_message(
                chat_id=self.settings.telegram_chat_id,
                text=message
            )
            logger.info("Rotation block reminder sent")
    
    async def check_upcoming_events(self):
        """Check for calendar events in the next 15 minutes and send reminders."""
        try:
            from donna.tools.calendar import get_today_events
            
            events_result = get_today_events.invoke({})
            
            # Parse events and check for ones starting soon
            now = datetime.now(self.timezone)
            
            # Simple check - look for time strings in the result
            # In production, you'd parse the actual event data
            if "No events" not in events_result and self.bot:
                # Log that we checked
                logger.debug(f"Checked upcoming events at {now}")
                
        except Exception as e:
            logger.error(f"Error checking upcoming events: {e}")
    
    async def send_weekly_review(self):
        """Send the weekly review on Sunday evening."""
        logger.info("=" * 50)
        logger.info("SENDING WEEKLY REVIEW")
        logger.info("=" * 50)
        
        try:
            from donna.tools.reviews import generate_weekly_review
            
            review = generate_weekly_review.invoke({})
            
            if self.bot and self.settings.telegram_chat_id:
                await self.bot.send_message(
                    chat_id=self.settings.telegram_chat_id,
                    text=f"📊 **Weekly Review**\n\n{review}"
                )
                logger.info("Weekly review sent")
                
                # Voice note
                if self.settings.elevenlabs_api_key and self.settings.elevenlabs_voice_id:
                    try:
                        clean_review = clean_text_for_tts(review)
                        voice_script = f"Here's your weekly review. {clean_review[:1000]}"  # Limit length
                        
                        audio_bytes = await text_to_speech(voice_script)
                        if audio_bytes:
                            voice_file = io.BytesIO(audio_bytes)
                            voice_file.name = "weekly_review.mp3"
                            
                            await self.bot.send_voice(
                                chat_id=self.settings.telegram_chat_id,
                                voice=voice_file,
                            )
                    except Exception as voice_error:
                        logger.error(f"Failed to send voice weekly review: {voice_error}")
                        
        except Exception as e:
            logger.error(f"Error sending weekly review: {e}")
    
    async def send_week_ahead(self):
        """Send the week ahead preview on Monday morning."""
        logger.info("=" * 50)
        logger.info("SENDING WEEK AHEAD PREVIEW")
        logger.info("=" * 50)
        
        try:
            from donna.tools.reviews import generate_week_ahead
            
            preview = generate_week_ahead.invoke({})
            
            if self.bot and self.settings.telegram_chat_id:
                await self.bot.send_message(
                    chat_id=self.settings.telegram_chat_id,
                    text=f"📅 **Week Ahead**\n\n{preview}"
                )
                logger.info("Week ahead preview sent")
                
                # Voice note
                if self.settings.elevenlabs_api_key and self.settings.elevenlabs_voice_id:
                    try:
                        clean_preview = clean_text_for_tts(preview)
                        voice_script = f"Here's what's coming up this week. {clean_preview[:1000]}"
                        
                        audio_bytes = await text_to_speech(voice_script)
                        if audio_bytes:
                            voice_file = io.BytesIO(audio_bytes)
                            voice_file.name = "week_ahead.mp3"
                            
                            await self.bot.send_voice(
                                chat_id=self.settings.telegram_chat_id,
                                voice=voice_file,
                            )
                    except Exception as voice_error:
                        logger.error(f"Failed to send voice week ahead: {voice_error}")
                        
        except Exception as e:
            logger.error(f"Error sending week ahead: {e}")
    
    def _schedule_morning_brief(self):
        """Schedule morning brief for 5:00 AM in configured timezone."""
        hour, minute = map(int, self.settings.donna_morning_brief_time.split(":"))
        
        self.scheduler.add_job(
            self.send_morning_brief,
            CronTrigger(
                hour=hour, 
                minute=minute,
                timezone=self.timezone  # Explicit timezone
            ),
            id="morning_brief",
            name="Morning Brief",
            replace_existing=True,
        )
        
        logger.info(f"Morning brief scheduled for {hour:02d}:{minute:02d} {self.settings.donna_timezone}")
    
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
        """Schedule evening summary for 9:00 PM in configured timezone."""
        self.scheduler.add_job(
            self.send_evening_summary,
            CronTrigger(
                hour=21, 
                minute=0,
                timezone=self.timezone  # Explicit timezone
            ),
            id="evening_summary",
            name="Evening Summary",
            replace_existing=True,
        )
        
        logger.info(f"Evening summary scheduled for 21:00 {self.settings.donna_timezone}")
    
    async def send_morning_brief(self):
        """Generate and send the morning brief to Telegram with voice note."""
        logger.info("=" * 50)
        logger.info("SENDING MORNING BRIEF")
        logger.info(f"Current time: {datetime.now(self.timezone)}")
        logger.info("=" * 50)
        
        try:
            # Generate today's schedule
            schedule = generate_daily_schedule.invoke({"date_str": None})
            
            # Build the brief
            today = datetime.now(self.timezone)
            brief = f"""Rise and shine. It's Donna.

I've already optimized your day, checked Calendly for conflicts, and made sure Sigmavue gets the attention it deserves. You're welcome.

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
                        # Clean text for TTS
                        clean_schedule = clean_text_for_tts(schedule)
                        voice_script = f"Rise and shine. It's Donna. I've already optimized your day. {clean_schedule}. Don't be late. I hate late."
                        
                        audio_bytes = await text_to_speech(voice_script)
                        
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
            import traceback
            traceback.print_exc()
    
    async def sync_calendly(self):
        """Sync Calendly events and check for conflicts."""
        logger.info("Syncing Calendly events...")
        
        try:
            # Only sync if Calendly is configured
            if not self.settings.calendly_api_key:
                logger.info("Calendly not configured, skipping sync")
                return
            
            from donna.tools.calendly import get_calendly_events, check_calendly_conflicts
            
            # Get upcoming Calendly events
            events = get_calendly_events.invoke({"days_ahead": 7})
            
            # Check today's conflicts
            today = datetime.now(self.timezone).strftime("%Y-%m-%d")
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
        logger.info("=" * 50)
        logger.info("SENDING EVENING SUMMARY")
        logger.info(f"Current time: {datetime.now(self.timezone)}")
        logger.info("=" * 50)
        
        try:
            # Get tomorrow's date
            today = datetime.now(self.timezone)
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
                
                # Voice note for evening summary
                if self.settings.elevenlabs_api_key and self.settings.elevenlabs_voice_id:
                    try:
                        clean_schedule = clean_text_for_tts(tomorrow_schedule)
                        voice_script = f"Alright, that's enough for today. I've already planned tomorrow. {clean_schedule}. Good night."
                        
                        audio_bytes = await text_to_speech(voice_script)
                        if audio_bytes:
                            voice_file = io.BytesIO(audio_bytes)
                            voice_file.name = "evening_summary.mp3"
                            
                            await self.bot.send_voice(
                                chat_id=self.settings.telegram_chat_id,
                                voice=voice_file,
                            )
                            logger.info("Evening summary voice note sent")
                    except Exception as voice_error:
                        logger.error(f"Failed to send voice evening summary: {voice_error}")
            
        except Exception as e:
            logger.error(f"Error sending evening summary: {e}")
            import traceback
            traceback.print_exc()
    
    def start(self):
        """Start the scheduler."""
        self.scheduler.start()
        logger.info("=" * 50)
        logger.info("DONNA SCHEDULER STARTED")
        logger.info(f"Timezone: {self.settings.donna_timezone}")
        logger.info(f"Current time: {datetime.now(self.timezone)}")
        logger.info("=" * 50)
    
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
