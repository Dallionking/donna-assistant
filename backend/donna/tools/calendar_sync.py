"""
Calendar Sync Tool - Syncs Donna's schedule template to Google Calendar as recurring events.

This creates time blocks for:
- Morning routine (wake, gym, stretch, shower, ready)
- Work blocks (Sigmavue, breaks, project rotation)
- Evening blocks (dinner, wind down)
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from langchain_core.tools import tool
from googleapiclient.discovery import build

from donna.config import get_settings
from donna.google_auth import get_google_credentials
from donna.database import get_supabase_client

logger = logging.getLogger(__name__)

# Color IDs for Google Calendar (makes it visually organized)
CALENDAR_COLORS = {
    "personal": "9",      # Blue - morning routine
    "sigmavue": "11",     # Red - priority work
    "break": "8",         # Gray - breaks
    "rotation": "10",     # Green - project rotation
    "evening": "6",       # Orange - evening
}


def get_calendar_service():
    """Get authenticated Google Calendar service."""
    creds = get_google_credentials()
    if not creds:
        return None
    return build('calendar', 'v3', credentials=creds)


def parse_time_12h(time_str: str) -> tuple:
    """Parse 12-hour time string to hour and minute."""
    try:
        dt = datetime.strptime(time_str.strip(), "%I:%M %p")
        return dt.hour, dt.minute
    except ValueError:
        # Try without space
        dt = datetime.strptime(time_str.strip(), "%I:%M%p")
        return dt.hour, dt.minute


def create_recurring_event(
    service,
    summary: str,
    start_time: str,
    end_time: str,
    color_id: str = "1",
    days: List[str] = None,
    description: str = "",
    calendar_id: str = "primary"
) -> Optional[Dict]:
    """
    Create a recurring event on Google Calendar.
    
    Args:
        service: Google Calendar service
        summary: Event title
        start_time: Start time in "HH:MM AM/PM" format
        end_time: End time in "HH:MM AM/PM" format
        color_id: Google Calendar color ID
        days: List of days ["monday", "tuesday", ...] or None for daily
        description: Event description
        calendar_id: Calendar ID (default: primary)
    
    Returns:
        Created event or None on failure
    """
    settings = get_settings()
    
    # Parse times
    start_hour, start_min = parse_time_12h(start_time)
    end_hour, end_min = parse_time_12h(end_time)
    
    # Get today's date for the start
    today = datetime.now()
    
    # Create start and end datetime
    start_dt = today.replace(hour=start_hour, minute=start_min, second=0, microsecond=0)
    end_dt = today.replace(hour=end_hour, minute=end_min, second=0, microsecond=0)
    
    # Handle overnight events
    if end_dt <= start_dt:
        end_dt += timedelta(days=1)
    
    # Build recurrence rule
    if days:
        # Specific days (e.g., MWF for gym)
        day_codes = {
            "monday": "MO", "tuesday": "TU", "wednesday": "WE",
            "thursday": "TH", "friday": "FR", "saturday": "SA", "sunday": "SU"
        }
        days_str = ",".join([day_codes[d.lower()] for d in days])
        rrule = f"RRULE:FREQ=WEEKLY;BYDAY={days_str}"
    else:
        # Daily
        rrule = "RRULE:FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR,SA,SU"
    
    event = {
        "summary": summary,
        "description": description,
        "start": {
            "dateTime": start_dt.isoformat(),
            "timeZone": settings.donna_timezone,
        },
        "end": {
            "dateTime": end_dt.isoformat(),
            "timeZone": settings.donna_timezone,
        },
        "recurrence": [rrule],
        "colorId": color_id,
        "reminders": {
            "useDefault": False,
            "overrides": [],  # No reminders for routine blocks
        },
    }
    
    try:
        created_event = service.events().insert(calendarId=calendar_id, body=event).execute()
        logger.info(f"Created recurring event: {summary}")
        return created_event
    except Exception as e:
        logger.error(f"Failed to create event {summary}: {e}")
        return None


def delete_donna_events(service, calendar_id: str = "primary") -> int:
    """Delete all Donna-created recurring events to avoid duplicates."""
    deleted = 0
    try:
        # Search for events with "[Donna]" prefix
        page_token = None
        while True:
            events_result = service.events().list(
                calendarId=calendar_id,
                q="[Donna]",
                singleEvents=False,
                pageToken=page_token
            ).execute()
            
            for event in events_result.get("items", []):
                if event.get("summary", "").startswith("[Donna]"):
                    service.events().delete(
                        calendarId=calendar_id,
                        eventId=event["id"]
                    ).execute()
                    deleted += 1
                    logger.info(f"Deleted event: {event.get('summary')}")
            
            page_token = events_result.get("nextPageToken")
            if not page_token:
                break
                
    except Exception as e:
        logger.error(f"Error deleting events: {e}")
    
    return deleted


def get_schedule_template() -> Optional[Dict]:
    """
    Get schedule template from Supabase only.
    NO local file access - runs on server.
    """
    try:
        supabase = get_supabase_client()
        if supabase:
            result = supabase.table("settings").select("*").eq("key", "weekly_template").execute()
            if result.data:
                value = result.data[0].get("value")
                if isinstance(value, str):
                    return json.loads(value)
                return value
    except Exception as e:
        logger.warning(f"Could not fetch from Supabase: {e}")
    
    # Return default template if Supabase fails
    return {
        "personal_blocks": {
            "wake": "7:00 AM",
            "gym": {"time": "8:00 AM", "days": ["monday", "wednesday", "friday"], "duration_minutes": 90},
            "stretch": "9:30 AM",
            "shower": "10:00 AM",
            "ready": "10:30 AM"
        },
        "work_blocks": {
            "primary": {"start": "12:00 PM", "end": "3:00 PM", "project": "sigmavue"},
            "break_1": {"start": "3:00 PM", "end": "3:30 PM"},
            "rotation_1": {"start": "3:30 PM", "end": "5:00 PM"},
            "rotation_2": {"start": "5:00 PM", "end": "7:00 PM"}
        },
        "evening": {"end_work": "7:00 PM", "dinner": "7:30 PM", "wind_down": "9:00 PM"}
    }


@tool
def sync_schedule_to_calendar(
    include_morning: bool = True,
    include_work: bool = True,
    include_evening: bool = False,
    clear_existing: bool = True
) -> str:
    """
    Sync Donna's schedule template to Google Calendar as recurring events.
    
    Creates time-blocked recurring events for your daily routine.
    Events are prefixed with [Donna] for easy identification.
    
    Args:
        include_morning: Include morning routine (wake, gym, etc.)
        include_work: Include work blocks (Sigmavue, rotation)
        include_evening: Include evening blocks (dinner, wind down)
        clear_existing: Clear existing [Donna] events first
    
    Returns:
        Summary of created events
    """
    service = get_calendar_service()
    if not service:
        return "❌ Google Calendar not connected. Please set up Google authentication."
    
    template = get_schedule_template()
    if not template:
        return "❌ No schedule template found. Please set up your weekly template first."
    
    created_events = []
    
    # Clear existing Donna events if requested
    if clear_existing:
        deleted = delete_donna_events(service)
        if deleted > 0:
            created_events.append(f"🗑️ Cleared {deleted} existing [Donna] events")
    
    # Morning Routine
    if include_morning:
        personal = template.get("personal_blocks", {})
        
        # Gym (MWF)
        if "gym" in personal:
            gym = personal["gym"]
            gym_time = gym.get("time", "8:00 AM")
            duration = gym.get("duration_minutes", 90)
            end_hour, end_min = parse_time_12h(gym_time)
            end_dt = datetime.now().replace(hour=end_hour, minute=end_min) + timedelta(minutes=duration)
            end_time = end_dt.strftime("%I:%M %p")
            
            if create_recurring_event(
                service,
                "[Donna] 🏋️ Gym",
                gym_time,
                end_time,
                CALENDAR_COLORS["personal"],
                gym.get("days", ["monday", "wednesday", "friday"]),
                "Non-negotiable. Get after it."
            ):
                created_events.append("🏋️ Gym (Mon/Wed/Fri)")
        
        # Stretch/Recovery
        if "stretch" in personal:
            if create_recurring_event(
                service,
                "[Donna] 🧘 Stretch & Recovery",
                personal["stretch"],
                personal.get("shower", "10:00 AM"),
                CALENDAR_COLORS["personal"],
                description="Post-workout recovery"
            ):
                created_events.append("🧘 Stretch & Recovery")
        
        # Ready time
        if "ready" in personal:
            if create_recurring_event(
                service,
                "[Donna] ✅ Ready for Work",
                personal["ready"],
                "11:30 AM",
                CALENDAR_COLORS["personal"],
                description="Prep time before deep work"
            ):
                created_events.append("✅ Ready for Work")
    
    # Work Blocks
    if include_work:
        work = template.get("work_blocks", {})
        
        # Sigmavue Deep Work
        if "primary" in work:
            primary = work["primary"]
            if create_recurring_event(
                service,
                f"[Donna] 🔥 {primary.get('description', 'Sigmavue Deep Work')}",
                primary["start"],
                primary["end"],
                CALENDAR_COLORS["sigmavue"],
                description="NON-NEGOTIABLE. Sigmavue gets done first."
            ):
                created_events.append("🔥 Sigmavue Deep Work (12-3 PM)")
        
        # Break
        if "break_1" in work:
            brk = work["break_1"]
            if create_recurring_event(
                service,
                "[Donna] ☕ Break",
                brk["start"],
                brk["end"],
                CALENDAR_COLORS["break"],
                description="Reset. Breathe. You earned it."
            ):
                created_events.append("☕ Break (3-3:30 PM)")
        
        # Rotation 1
        if "rotation_1" in work:
            rot1 = work["rotation_1"]
            if create_recurring_event(
                service,
                f"[Donna] 📦 {rot1.get('description', 'Project Rotation 1')}",
                rot1["start"],
                rot1["end"],
                CALENDAR_COLORS["rotation"],
                description="Client or personal project work"
            ):
                created_events.append("📦 Project Rotation 1 (3:30-5 PM)")
        
        # Rotation 2
        if "rotation_2" in work:
            rot2 = work["rotation_2"]
            if create_recurring_event(
                service,
                f"[Donna] 📦 {rot2.get('description', 'Project Rotation 2')}",
                rot2["start"],
                rot2["end"],
                CALENDAR_COLORS["rotation"],
                description="Client or personal project work"
            ):
                created_events.append("📦 Project Rotation 2 (5-7 PM)")
    
    # Evening Blocks
    if include_evening:
        evening = template.get("evening", {})
        
        if "dinner" in evening:
            if create_recurring_event(
                service,
                "[Donna] 🍽️ Dinner",
                evening["dinner"],
                evening.get("wind_down", "9:00 PM"),
                CALENDAR_COLORS["evening"],
                description="Eat. Recover."
            ):
                created_events.append("🍽️ Dinner")
        
        if "wind_down" in evening:
            if create_recurring_event(
                service,
                "[Donna] 🌙 Wind Down",
                evening["wind_down"],
                "10:30 PM",
                CALENDAR_COLORS["evening"],
                description="No screens. Prepare for tomorrow."
            ):
                created_events.append("🌙 Wind Down")
    
    if created_events:
        result = "✅ **Calendar synced!** I've created the following recurring events:\n\n"
        result += "\n".join([f"• {e}" for e in created_events])
        result += "\n\n*All events are prefixed with [Donna] and will repeat weekly.*"
        result += "\n*Calendly calls will still override these blocks.*"
        return result
    else:
        return "❌ No events were created. Check your schedule template."


@tool  
def clear_donna_calendar_events() -> str:
    """
    Clear all [Donna] prefixed events from Google Calendar.
    
    Use this to remove all Donna-created schedule blocks.
    """
    service = get_calendar_service()
    if not service:
        return "❌ Google Calendar not connected."
    
    deleted = delete_donna_events(service)
    
    if deleted > 0:
        return f"✅ Cleared {deleted} [Donna] events from your calendar. It's like they never existed."
    else:
        return "No [Donna] events found to delete. Your calendar is already clean."


@tool
def update_schedule_template(
    block_name: str,
    start_time: str = None,
    end_time: str = None,
    days: List[str] = None
) -> str:
    """
    Update a specific block in the schedule template.
    
    Args:
        block_name: Name of block to update (e.g., "gym", "sigmavue", "rotation_1")
        start_time: New start time (e.g., "8:00 AM")
        end_time: New end time (e.g., "9:30 AM")
        days: Days for the block (e.g., ["monday", "wednesday", "friday"])
    
    Returns:
        Confirmation of update
    """
    template = get_schedule_template()
    if not template:
        return "❌ No schedule template found."
    
    updated = False
    
    # Check personal blocks
    if block_name in template.get("personal_blocks", {}):
        block = template["personal_blocks"][block_name]
        if isinstance(block, dict):
            if start_time:
                block["time"] = start_time
                updated = True
            if days:
                block["days"] = days
                updated = True
        else:
            if start_time:
                template["personal_blocks"][block_name] = start_time
                updated = True
    
    # Check work blocks
    for key, block in template.get("work_blocks", {}).items():
        if block_name.lower() in key.lower():
            if start_time:
                block["start"] = start_time
                updated = True
            if end_time:
                block["end"] = end_time
                updated = True
    
    if updated:
        # Save to Supabase
        try:
            supabase = get_supabase_client()
            if supabase:
                supabase.table("settings").upsert({
                    "key": "weekly_template",
                    "value": json.dumps(template)
                }).execute()
        except Exception as e:
            logger.error(f"Failed to save to Supabase: {e}")
        
        # Also save locally
        settings = get_settings()
        template_path = settings.donna_workspace / "schedule" / "weekly-template.json"
        template_path.write_text(json.dumps(template, indent=2))
        
        return f"✅ Updated {block_name}. Run `/sync_calendar` to apply changes to Google Calendar."
    else:
        return f"❌ Block '{block_name}' not found. Available blocks: gym, stretch, sigmavue, rotation_1, rotation_2"

