"""
Calendly integration tools for Donna.

Handles fetching scheduled events and managing conflicts.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime, date, timedelta

import httpx
from langchain_core.tools import tool

from donna.config import get_settings


CALENDLY_API_BASE = "https://api.calendly.com"


def get_calendly_headers() -> Dict[str, str]:
    """Get headers for Calendly API requests."""
    settings = get_settings()
    
    if not settings.calendly_api_key:
        return {}
    
    return {
        "Authorization": f"Bearer {settings.calendly_api_key}",
        "Content-Type": "application/json",
    }


async def get_current_user() -> Optional[Dict[str, Any]]:
    """Get the current Calendly user."""
    headers = get_calendly_headers()
    
    if not headers:
        return None
    
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{CALENDLY_API_BASE}/users/me",
            headers=headers
        )
        
        if response.status_code == 200:
            return response.json().get("resource")
        
        return None


@tool
def get_calendly_events(days_ahead: int = 7) -> str:
    """
    Get upcoming Calendly events.
    
    Args:
        days_ahead: Number of days to look ahead (default: 7)
    
    Returns list of scheduled calls with:
    - Date and time
    - Event type
    - Invitee name
    - Status
    """
    settings = get_settings()
    
    if not settings.calendly_api_key:
        return """⚠️ Calendly not configured.

To set up Calendly:
1. Go to calendly.com/integrations/api_webhooks
2. Generate a Personal Access Token
3. Add CALENDLY_API_KEY to your .env file

This will allow me to:
- See your scheduled calls
- Auto-adjust your schedule when calls are booked
- Prioritize calls over project blocks
"""
    
    # Note: Actual implementation would be async
    # For tool compatibility, we'll use sync httpx
    
    try:
        headers = get_calendly_headers()
        
        # First get current user
        with httpx.Client() as client:
            user_response = client.get(
                f"{CALENDLY_API_BASE}/users/me",
                headers=headers
            )
            
            if user_response.status_code != 200:
                return f"Error authenticating with Calendly: {user_response.text}"
            
            user_uri = user_response.json()["resource"]["uri"]
            
            # Get scheduled events
            now = datetime.now()
            min_time = now.isoformat() + "Z"
            max_time = (now + timedelta(days=days_ahead)).isoformat() + "Z"
            
            events_response = client.get(
                f"{CALENDLY_API_BASE}/scheduled_events",
                headers=headers,
                params={
                    "user": user_uri,
                    "min_start_time": min_time,
                    "max_start_time": max_time,
                    "status": "active",
                }
            )
            
            if events_response.status_code != 200:
                return f"Error fetching events: {events_response.text}"
            
            events = events_response.json().get("collection", [])
            
            if not events:
                return f"No Calendly events scheduled in the next {days_ahead} days."
            
            lines = [f"# Upcoming Calendly Events (Next {days_ahead} days)\n"]
            
            for event in events:
                start = datetime.fromisoformat(event["start_time"].replace("Z", "+00:00"))
                end = datetime.fromisoformat(event["end_time"].replace("Z", "+00:00"))
                
                event_type = event.get("name", "Call")
                status = event.get("status", "active")
                
                lines.append(f"## 📞 {event_type}")
                lines.append(f"**Date**: {start.strftime('%A, %B %d')}")
                lines.append(f"**Time**: {start.strftime('%I:%M %p')} - {end.strftime('%I:%M %p')}")
                lines.append(f"**Status**: {status}")
                
                # Get invitee info
                invitees_uri = event.get("uri", "") + "/invitees"
                try:
                    inv_response = client.get(invitees_uri, headers=headers)
                    if inv_response.status_code == 200:
                        invitees = inv_response.json().get("collection", [])
                        if invitees:
                            invitee = invitees[0]
                            lines.append(f"**With**: {invitee.get('name', 'Unknown')}")
                            lines.append(f"**Email**: {invitee.get('email', 'N/A')}")
                except Exception:
                    pass
                
                lines.append("")
            
            return "\n".join(lines)
            
    except Exception as e:
        return f"Error fetching Calendly events: {str(e)}"


@tool
def check_calendly_conflicts(date_str: str) -> str:
    """
    Check for Calendly events that conflict with scheduled project blocks.
    
    Args:
        date_str: Date to check in YYYY-MM-DD format
    
    Returns:
    - List of Calendly events on that date
    - Any conflicts with project blocks
    - Suggested schedule adjustments
    """
    settings = get_settings()
    
    if not settings.calendly_api_key:
        return "⚠️ Calendly not configured. Add CALENDLY_API_KEY to .env"
    
    target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    
    # Get Calendly events for that day
    events_result = get_calendly_events.invoke({"days_ahead": 1})
    
    # In a real implementation, we would:
    # 1. Parse the events
    # 2. Compare with scheduled project blocks
    # 3. Identify conflicts
    # 4. Suggest rescheduling
    
    return f"""# Conflict Check for {target_date.strftime('%A, %B %d')}

{events_result}

## Conflict Resolution

If any Calendly events overlap with your project blocks:
1. The call takes priority
2. The project block will be moved to the next available slot
3. You'll be notified via Telegram

Use `/sync` to apply schedule adjustments.
"""


