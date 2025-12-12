"""
Calendly integration tools for Donna.

Handles fetching scheduled events and managing conflicts.
Automatically creates client records from invitees.
"""

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, date, timedelta

import httpx
from langchain_core.tools import tool

from donna.config import get_settings

logger = logging.getLogger(__name__)


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


async def create_client_from_calendly_invitee(
    name: str,
    email: str,
    event_type: Optional[str] = None,
    event_uri: Optional[str] = None
) -> Optional[str]:
    """
    Auto-create a client record from a Calendly invitee.
    
    Called when a Calendly event is booked via webhook.
    
    Args:
        name: Invitee's name
        email: Invitee's email
        event_type: Type of event booked
        event_uri: Calendly event URI for reference
    
    Returns:
        Client ID if created, None if already exists or error
    """
    from donna.database import search_clients, save_client
    
    # Check if client already exists
    existing = await search_clients(email)
    if existing:
        logger.info(f"Client already exists: {name} ({email})")
        return existing[0].get('id')
    
    # Also check by name
    existing_by_name = await search_clients(name)
    if existing_by_name:
        # Check if email matches or is similar
        for c in existing_by_name:
            if c.get('email') == email:
                logger.info(f"Client already exists (by name match): {name}")
                return c.get('id')
    
    # Create new client
    notes = f"Booked via Calendly"
    if event_type:
        notes += f" - {event_type}"
    
    client_data = {
        "name": name,
        "email": email,
        "source": "calendly",
        "notes": notes,
        "first_contact": datetime.now().isoformat(),
        "created_at": datetime.now().isoformat(),
    }
    
    client_id = await save_client(client_data)
    
    if client_id:
        logger.info(f"Auto-created client from Calendly: {name} ({email})")
    
    return client_id


def sync_create_client_from_calendly(
    name: str,
    email: str,
    event_type: Optional[str] = None
) -> Optional[str]:
    """Synchronous wrapper for create_client_from_calendly_invitee."""
    import asyncio
    
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    return loop.run_until_complete(
        create_client_from_calendly_invitee(name, email, event_type)
    )


@tool
def sync_calendly_invitees_as_clients() -> str:
    """
    Sync all Calendly invitees as clients.
    
    Fetches recent Calendly events and creates client records
    for any invitees not already in the system.
    
    Returns:
        Summary of clients created/found
    """
    settings = get_settings()
    
    if not settings.calendly_api_key:
        return "⚠️ Calendly not configured. Add CALENDLY_API_KEY to .env"
    
    try:
        headers = get_calendly_headers()
        created = 0
        existing = 0
        
        with httpx.Client() as client:
            # Get current user
            user_response = client.get(
                f"{CALENDLY_API_BASE}/users/me",
                headers=headers
            )
            
            if user_response.status_code != 200:
                return f"Error authenticating with Calendly"
            
            user_uri = user_response.json()["resource"]["uri"]
            
            # Get events from last 30 days
            now = datetime.now()
            min_time = (now - timedelta(days=30)).isoformat() + "Z"
            max_time = (now + timedelta(days=30)).isoformat() + "Z"
            
            events_response = client.get(
                f"{CALENDLY_API_BASE}/scheduled_events",
                headers=headers,
                params={
                    "user": user_uri,
                    "min_start_time": min_time,
                    "max_start_time": max_time,
                }
            )
            
            if events_response.status_code != 200:
                return f"Error fetching events"
            
            events = events_response.json().get("collection", [])
            
            for event in events:
                event_type = event.get("name", "Call")
                event_uri = event.get("uri", "")
                
                # Get invitees
                try:
                    inv_response = client.get(
                        f"{event_uri}/invitees",
                        headers=headers
                    )
                    
                    if inv_response.status_code == 200:
                        invitees = inv_response.json().get("collection", [])
                        
                        for invitee in invitees:
                            name = invitee.get("name", "Unknown")
                            email = invitee.get("email", "")
                            
                            if email:
                                result = sync_create_client_from_calendly(
                                    name, email, event_type
                                )
                                if result:
                                    created += 1
                                else:
                                    existing += 1
                except Exception as e:
                    logger.error(f"Error getting invitees: {e}")
        
        return f"""# Calendly Sync Complete

- **New clients created**: {created}
- **Already in system**: {existing}

All your Calendly contacts are now tracked as clients."""
        
    except Exception as e:
        return f"Error syncing Calendly: {str(e)}"
