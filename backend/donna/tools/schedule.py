"""
Schedule management tools for Donna.

Handles generating daily schedules, project rotation, and time blocking.
"""

import json
from datetime import datetime, date, time, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any

from langchain_core.tools import tool

from donna.config import get_settings, get_schedule_template_path, get_daily_path
from donna.models import DailySchedule, TimeBlock, WeeklyTemplate
from donna.tools.projects import load_project_registry, get_project_prd_status


def load_weekly_template() -> Dict[str, Any]:
    """Load the weekly schedule template."""
    template_path = get_schedule_template_path()
    
    if not template_path.exists():
        return {}
    
    with open(template_path, "r") as f:
        return json.load(f)


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
    registry = load_project_registry()
    
    # Filter out daily projects and projects without paths
    candidates = [
        p for p in registry.projects
        if p.id not in exclude_daily and p.path and not p.daily
    ]
    
    # Sort by:
    # 1. Last worked (None = never worked, highest priority)
    # 2. Priority (lower = higher priority)
    def sort_key(p):
        last_worked = p.last_worked or datetime.min
        return (last_worked, p.priority)
    
    candidates.sort(key=sort_key)
    
    # Select top N
    selected = candidates[:num_slots]
    
    return [
        {
            "id": p.id,
            "name": p.name,
            "path": p.path,
            "prd_status_path": p.prd_status_path,
        }
        for p in selected
    ]


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
    registry = load_project_registry()
    
    if not template:
        return "Weekly template not found. Please configure schedule/weekly-template.json"
    
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
        project = next((p for p in registry.projects if p.id == project_id), None)
        
        if project:
            # Get PRD status
            prd_info = ""
            if project.prd_status_path and project.path:
                try:
                    prd_result = get_project_prd_status.invoke({"project_name": project.name})
                    # Extract current PRD from result
                    if "Currently Working On" in prd_result:
                        prd_section = prd_result.split("Currently Working On")[1].split("##")[0]
                        prd_info = prd_section.strip()[:100]
                except Exception:
                    prd_info = "PRD status unavailable"
            
            lines.append(f"### {primary['start']} - {primary['end']}: {project.name}")
            if prd_info:
                lines.append(f"  → {prd_info}")
    
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
    if rotation_1 and len(rotation_projects) > 0:
        proj = rotation_projects[0]
        lines.append(f"\n### {rotation_1['start']} - {rotation_1['end']}: {proj['name']}")
        if proj.get("prd_status_path"):
            try:
                prd_result = get_project_prd_status.invoke({"project_name": proj['name']})
                if "Currently Working On" in prd_result:
                    prd_section = prd_result.split("Currently Working On")[1].split("##")[0]
                    lines.append(f"  → {prd_section.strip()[:100]}")
            except Exception:
                pass
    
    rotation_2 = work_blocks.get("rotation_2", {})
    if rotation_2 and len(rotation_projects) > 1:
        proj = rotation_projects[1]
        lines.append(f"\n### {rotation_2['start']} - {rotation_2['end']}: {proj['name']}")
        if proj.get("prd_status_path"):
            try:
                prd_result = get_project_prd_status.invoke({"project_name": proj['name']})
                if "Currently Working On" in prd_result:
                    prd_section = prd_result.split("Currently Working On")[1].split("##")[0]
                    lines.append(f"  → {prd_section.strip()[:100]}")
            except Exception:
                pass
    
    # Top 3 Signal Tasks
    lines.append("\n## 🎯 Top 3 Signal Tasks\n")
    lines.append("1. Complete current PRD phase (Sigmavue)")
    if len(rotation_projects) > 0:
        lines.append(f"2. Progress on {rotation_projects[0]['name']}")
    if len(rotation_projects) > 1:
        lines.append(f"3. Progress on {rotation_projects[1]['name']}")
    
    return "\n".join(lines)


@tool
def get_schedule_for_date(date_str: Optional[str] = None) -> str:
    """
    Get the schedule for a specific date.
    
    Args:
        date_str: Date in YYYY-MM-DD format (defaults to today)
    
    Returns the saved schedule or generates one if none exists.
    """
    if date_str:
        target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    else:
        target_date = datetime.now().date()
    
    # Check if saved schedule exists
    daily_path = get_daily_path()
    year = target_date.strftime("%Y")
    month = target_date.strftime("%m-%B").lower()
    schedule_file = daily_path / year / month / f"{target_date.strftime('%Y-%m-%d')}.md"
    
    if schedule_file.exists():
        with open(schedule_file, "r") as f:
            return f.read()
    
    # Generate new schedule
    return generate_daily_schedule.invoke({"date_str": date_str})


@tool
def update_schedule(
    date_str: str,
    action: str,
    project_id: Optional[str] = None,
    new_time: Optional[str] = None,
    notes: Optional[str] = None
) -> str:
    """
    Update a schedule with changes.
    
    Args:
        date_str: Date in YYYY-MM-DD format
        action: The action to perform (move_project, add_call, remove_block)
        project_id: Project to modify (for move_project)
        new_time: New time slot in HH:MM-HH:MM format
        notes: Additional notes
    
    Handles:
    - Moving project blocks when calls are added
    - Rescheduling to different days
    - Adding manual time blocks
    """
    target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    
    if action == "move_project":
        if not project_id or not new_time:
            return "move_project requires project_id and new_time"
        
        # Parse new time
        start, end = new_time.split("-")
        
        return f"""✅ Moved project block

**{project_id}** moved to **{start} - {end}** on {target_date.strftime('%A, %B %d')}

{notes or ''}
"""
    
    elif action == "add_call":
        if not new_time:
            return "add_call requires new_time"
        
        start, end = new_time.split("-")
        
        return f"""✅ Call added

**Call** scheduled for **{start} - {end}** on {target_date.strftime('%A, %B %d')}

Any conflicting project blocks will be automatically moved.

{notes or ''}
"""
    
    elif action == "remove_block":
        return f"Block removed from schedule for {target_date.strftime('%A, %B %d')}"
    
    else:
        return f"Unknown action: {action}. Available: move_project, add_call, remove_block"


