"""
Schedule management tools for Donna.

Handles generating daily schedules, project rotation, and time blocking.
All data stored in Supabase - NO local file access.
"""

import json
import logging
from datetime import datetime, date, time, timedelta
from typing import Optional, List, Dict, Any

from langchain_core.tools import tool

from donna.config import get_settings
from donna.database import get_supabase_client
from donna.tools.projects import load_projects_from_supabase, get_project_prd_status

logger = logging.getLogger(__name__)


def load_weekly_template() -> Dict[str, Any]:
    """Load the weekly schedule template from Supabase."""
    try:
        supabase = get_supabase_client()
        if not supabase:
            logger.warning("Supabase not available for weekly template")
            return get_default_template()
        
        result = supabase.table("settings").select("*").eq("key", "weekly_template").limit(1).execute()
        
        if result.data:
            value = result.data[0].get("value")
            if isinstance(value, str):
                return json.loads(value)
            return value
        
        # Return default if not found
        return get_default_template()
        
    except Exception as e:
        logger.error(f"Error loading weekly template: {e}")
        return get_default_template()


def get_default_template() -> Dict[str, Any]:
    """Get default schedule template."""
    return {
        "personal_blocks": {
            "wake": "7:00 AM",
            "gym": {
                "time": "8:00 AM",
                "days": ["monday", "wednesday", "friday"],
                "duration_minutes": 90
            },
            "stretch": "9:30 AM",
            "shower": "10:00 AM",
            "ready": "10:30 AM"
        },
        "work_blocks": {
            "primary": {
                "start": "12:00 PM",
                "end": "3:00 PM",
                "project": "sigmavue",
                "description": "Sigmavue Deep Work (Non-negotiable)"
            },
            "break_1": {
                "start": "3:00 PM",
                "end": "3:30 PM",
                "description": "Break / Reset"
            },
            "rotation_1": {
                "start": "3:30 PM",
                "end": "5:00 PM",
                "description": "Client/Personal Project Rotation Slot 1"
            },
            "rotation_2": {
                "start": "5:00 PM",
                "end": "7:00 PM",
                "description": "Client/Personal Project Rotation Slot 2"
            }
        },
        "evening": {
            "end_work": "7:00 PM",
            "dinner": "7:30 PM",
            "wind_down": "9:00 PM"
        }
    }


def get_day_name(d: date) -> str:
    """Get lowercase day name."""
    return d.strftime("%A").lower()


def select_rotation_projects(exclude_daily: List[str], num_slots: int = 2) -> List[Dict[str, Any]]:
    """
    Select projects for rotation slots based on:
    1. PRD status (in_progress > not_started)
    2. Last worked date (oldest first)
    3. Priority
    """
    projects = load_projects_from_supabase()
    
    # Filter out daily projects and projects without paths
    candidates = [
        p for p in projects
        if p.get("id") not in exclude_daily and p.get("path") and not p.get("daily")
    ]
    
    # Sort by last worked (None = never worked, highest priority) then priority
    def sort_key(p):
        last_worked = p.get("last_worked")
        if last_worked:
            try:
                return (datetime.fromisoformat(last_worked.replace("Z", "")), p.get("priority", 999))
            except:
                pass
        return (datetime.min, p.get("priority", 999))
    
    candidates.sort(key=sort_key)
    
    # Select top N
    return candidates[:num_slots]


@tool
def generate_daily_schedule(date_str: Optional[str] = None) -> str:
    """
    Generate a daily schedule based on the weekly template and project rotation.
    
    Args:
        date_str: Date in YYYY-MM-DD format (defaults to today)
    
    Returns the generated schedule with:
    - Personal routine blocks
    - Work blocks with specific projects and PRDs
    - Top 3 Signal tasks
    """
    if date_str:
        target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    else:
        target_date = datetime.now().date()
    
    day_name = get_day_name(target_date)
    template = load_weekly_template()
    projects = load_projects_from_supabase()
    
    # Build schedule lines
    lines = [f"# Schedule for {target_date.strftime('%A, %B %d, %Y')}\n"]
    
    # Personal blocks
    personal = template.get("personal_blocks", {})
    
    lines.append("## 🌅 Morning Routine\n")
    
    if personal.get("wake"):
        lines.append(f"- **{personal['wake']}** - Wake up")
    
    gym_config = personal.get("gym", {})
    if gym_config and day_name in gym_config.get("days", []):
        lines.append(f"- **{gym_config['time']}** - Gym ({gym_config.get('duration_minutes', 90)} min)")
    
    if personal.get("stretch"):
        lines.append(f"- **{personal['stretch']}** - Stretch / Recovery")
    
    if personal.get("shower"):
        lines.append(f"- **{personal['shower']}** - Shower")
    
    if personal.get("ready"):
        lines.append(f"- **{personal['ready']}** - Ready / Personal time")
    
    # Work blocks
    lines.append("\n## 💼 Work Blocks\n")
    
    work_blocks = template.get("work_blocks", {})
    
    # Primary block (Sigmavue)
    primary = work_blocks.get("primary", {})
    if primary:
        project_id = primary.get("project", "sigmavue")
        project = next((p for p in projects if p.get("id") == project_id), None)
        
        project_name = project.get("name", "Sigmavue") if project else "Sigmavue"
        lines.append(f"### {primary['start']} - {primary['end']}: {project_name} 🔥")
        lines.append(f"  → Non-negotiable deep work block")
    
    # Break
    break_block = work_blocks.get("break_1", {})
    if break_block:
        lines.append(f"\n### {break_block['start']} - {break_block['end']}: Break ☕")
    
    # Rotation slots
    rotation_projects = select_rotation_projects(
        exclude_daily=["sigmavue"],
        num_slots=2
    )
    
    rotation_1 = work_blocks.get("rotation_1", {})
    if rotation_1:
        if len(rotation_projects) > 0:
            proj = rotation_projects[0]
            lines.append(f"\n### {rotation_1['start']} - {rotation_1['end']}: {proj.get('name', 'Project 1')}")
        else:
            lines.append(f"\n### {rotation_1['start']} - {rotation_1['end']}: {rotation_1.get('description', 'Project Rotation 1')}")
    
    rotation_2 = work_blocks.get("rotation_2", {})
    if rotation_2:
        if len(rotation_projects) > 1:
            proj = rotation_projects[1]
            lines.append(f"\n### {rotation_2['start']} - {rotation_2['end']}: {proj.get('name', 'Project 2')}")
        else:
            lines.append(f"\n### {rotation_2['start']} - {rotation_2['end']}: {rotation_2.get('description', 'Project Rotation 2')}")
    
    # Evening
    evening = template.get("evening", {})
    if evening:
        lines.append("\n## 🌙 Evening\n")
        if evening.get("end_work"):
            lines.append(f"- **{evening['end_work']}** - End work")
        if evening.get("dinner"):
            lines.append(f"- **{evening['dinner']}** - Dinner")
        if evening.get("wind_down"):
            lines.append(f"- **{evening['wind_down']}** - Wind down")
    
    # Top 3 Signal Tasks
    lines.append("\n## 🎯 Top 3 Signal Tasks\n")
    lines.append("1. Sigmavue - Current PRD phase")
    if len(rotation_projects) > 0:
        lines.append(f"2. {rotation_projects[0].get('name', 'Project')} - Check PRD status")
    if len(rotation_projects) > 1:
        lines.append(f"3. {rotation_projects[1].get('name', 'Project')} - Check PRD status")
    
    # Notes
    lines.append("\n---")
    lines.append("\n*Calendly calls override project blocks. Check your calendar.*")
    
    return "\n".join(lines)


@tool
def get_schedule_for_date(date_str: Optional[str] = None) -> str:
    """
    Get the schedule for a specific date.
    
    Args:
        date_str: Date in YYYY-MM-DD format (defaults to today)
    
    Alias for generate_daily_schedule with friendlier name.
    """
    return generate_daily_schedule.invoke({"date_str": date_str})


@tool
def update_schedule(
    block_name: str,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    project: Optional[str] = None
) -> str:
    """
    Update a specific block in the schedule template.
    
    Args:
        block_name: Name of block (e.g., "primary", "rotation_1", "gym")
        start_time: New start time (e.g., "12:00 PM")
        end_time: New end time (e.g., "3:00 PM")
        project: Project to assign to the block
    
    Returns confirmation of update.
    """
    template = load_weekly_template()
    updated = False
    
    # Check work blocks
    if block_name in template.get("work_blocks", {}):
        block = template["work_blocks"][block_name]
        if start_time:
            block["start"] = start_time
            updated = True
        if end_time:
            block["end"] = end_time
            updated = True
        if project:
            block["project"] = project
            updated = True
    
    # Check personal blocks
    elif block_name in template.get("personal_blocks", {}):
        if start_time:
            if isinstance(template["personal_blocks"][block_name], dict):
                template["personal_blocks"][block_name]["time"] = start_time
            else:
                template["personal_blocks"][block_name] = start_time
            updated = True
    
    if updated:
        # Save to Supabase
        try:
            supabase = get_supabase_client()
            if supabase:
                supabase.table("settings").upsert({
                    "key": "weekly_template",
                    "value": template,
                    "updated_at": datetime.now().isoformat()
                }).execute()
                
                return f"✅ Updated {block_name}. Run sync_calendar to apply to Google Calendar."
        except Exception as e:
            logger.error(f"Failed to save template: {e}")
            return f"Failed to save: {str(e)}"
    
    return f"Block '{block_name}' not found or no changes made."


@tool
def get_tomorrow_schedule() -> str:
    """Get tomorrow's schedule."""
    tomorrow = datetime.now().date() + timedelta(days=1)
    return generate_daily_schedule.invoke({"date_str": tomorrow.strftime("%Y-%m-%d")})
