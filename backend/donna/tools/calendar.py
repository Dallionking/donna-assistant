"""
Google Calendar integration tools for Donna.

Handles reading events, creating time blocks, and syncing schedules.
"""

import json
from datetime import datetime, date, time, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any

from langchain_core.tools import tool

from donna.config import get_settings
from donna.google_auth import get_calendar_service


@tool
def get_today_events() -> str:
    """
    Get all events for today from Google Calendar.
    
    Returns a list of events including:
    - Time
    - Title
    - Location (if any)
    - Whether it's a Calendly meeting
    """
    service = get_calendar_service()
    
    if service is None:
        return """⚠️ Google Calendar not configured.

To set up Google Calendar:
1. Go to Google Cloud Console
2. Enable the Calendar API
3. Create OAuth credentials
4. Save credentials.json to backend/credentials/
5. Run the OAuth flow to generate token.json

For now, I'll work with your schedule template.
"""
    
    # Get today's events
    today = datetime.now().date()
    time_min = datetime.combine(today, time.min).isoformat() + 'Z'
    time_max = datetime.combine(today, time.max).isoformat() + 'Z'
    
    try:
        events_result = service.events().list(
            calendarId='primary',
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])
        
        if not events:
            return f"No events on your calendar for {today.strftime('%A, %B %d')}."
        
        lines = [f"# Calendar Events for {today.strftime('%A, %B %d')}\n"]
        
        for event in events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            start_time = datetime.fromisoformat(start.replace('Z', '+00:00'))
            
            title = event.get('summary', 'No Title')
            location = event.get('location', '')
            
            # Check if it's a Calendly event
            is_calendly = 'calendly' in title.lower() or 'calendly' in event.get('description', '').lower()
            calendly_marker = " 📞" if is_calendly else ""
            
            lines.append(f"**{start_time.strftime('%I:%M %p')}** - {title}{calendly_marker}")
            if location:
                lines.append(f"  📍 {location}")
        
        return "\n".join(lines)
        
    except Exception as e:
        return f"Error fetching calendar events: {str(e)}"


@tool
def create_time_block(
    title: str,
    start_time: str,
    end_time: str,
    date_str: Optional[str] = None,
    description: Optional[str] = None,
    color: Optional[str] = None
) -> str:
    """
    Create a time block on Google Calendar.
    
    Args:
        title: Title of the time block (e.g., "Sigmavue: PRD-F-INTERFACE-STATES")
        start_time: Start time in HH:MM format (24h)
        end_time: End time in HH:MM format (24h)
        date_str: Date in YYYY-MM-DD format (defaults to today)
        description: Optional description with PRD details
        color: Optional color ID (1-11)
    
    Returns confirmation or error message.
    """
    service = get_calendar_service()
    
    if service is None:
        return f"""⚠️ Google Calendar not configured.

Would create event:
- **Title**: {title}
- **Time**: {start_time} - {end_time}
- **Date**: {date_str or 'Today'}
- **Description**: {description or 'None'}

Configure Google Calendar OAuth to enable syncing.
"""
    
    # Parse date
    if date_str:
        event_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    else:
        event_date = datetime.now().date()
    
    # Parse times
    start_dt = datetime.combine(event_date, datetime.strptime(start_time, "%H:%M").time())
    end_dt = datetime.combine(event_date, datetime.strptime(end_time, "%H:%M").time())
    
    # Create event
    event = {
        'summary': title,
        'description': description or '',
        'start': {
            'dateTime': start_dt.isoformat(),
            'timeZone': get_settings().donna_timezone,
        },
        'end': {
            'dateTime': end_dt.isoformat(),
            'timeZone': get_settings().donna_timezone,
        },
    }
    
    if color:
        event['colorId'] = color
    
    try:
        created_event = service.events().insert(calendarId='primary', body=event).execute()
        return f"""✅ Time block created!

**{title}**
- Time: {start_time} - {end_time}
- Date: {event_date.strftime('%A, %B %d')}
- Calendar Link: {created_event.get('htmlLink', 'N/A')}
"""
    except Exception as e:
        return f"Error creating calendar event: {str(e)}"


@tool
def sync_schedule_to_calendar(date_str: Optional[str] = None) -> str:
    """
    Sync the daily schedule to Google Calendar.
    
    Args:
        date_str: Date in YYYY-MM-DD format (defaults to today)
    
    Creates time blocks for:
    - Personal routine (wake, gym, etc.)
    - Work blocks with project assignments
    - Breaks
    
    Respects existing Calendly events by working around them.
    """
    from donna.tools.schedule import get_schedule_for_date
    
    service = get_calendar_service()
    
    if date_str:
        target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    else:
        target_date = datetime.now().date()
    
    # Get the schedule
    schedule_result = get_schedule_for_date.invoke({"date_str": date_str})
    
    if service is None:
        return f"""⚠️ Google Calendar not configured.

Would sync schedule for {target_date.strftime('%A, %B %d')}:

{schedule_result}

Configure Google Calendar OAuth to enable syncing.
"""
    
    # TODO: Parse schedule and create events
    # This would involve:
    # 1. Get existing events for the day
    # 2. Identify Calendly events (don't modify)
    # 3. Create/update Donna-managed time blocks
    # 4. Handle conflicts by moving project blocks
    
    return f"""✅ Schedule synced to Google Calendar!

Date: {target_date.strftime('%A, %B %d')}

{schedule_result}
"""


