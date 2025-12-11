"""
Project management tools for Donna.

Handles reading project registry, PRD status, and project discovery.
All data stored in Supabase - NO local file access.
"""

import json
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import uuid4

from langchain_core.tools import tool

from donna.config import get_settings
from donna.database import get_supabase_client
from donna.models import Project, ProjectRegistry, PRDEntry, ProjectPRDStatus, PRDStatus

logger = logging.getLogger(__name__)


def load_projects_from_supabase() -> List[dict]:
    """Load all projects from Supabase."""
    try:
        supabase = get_supabase_client()
        if not supabase:
            return []
        
        result = supabase.table("projects").select("*").order("priority").execute()
        return result.data if result.data else []
    except Exception as e:
        logger.error(f"Error loading projects: {e}")
        return []


def save_project_to_supabase(project_data: dict) -> bool:
    """Save a project to Supabase."""
    try:
        supabase = get_supabase_client()
        if not supabase:
            return False
        
        supabase.table("projects").upsert(project_data).execute()
        return True
    except Exception as e:
        logger.error(f"Error saving project: {e}")
        return False


@tool
def get_all_projects() -> str:
    """
    Get a list of all tracked projects with their status.
    
    Returns a summary of each project including:
    - Name and path
    - Type (startup/personal/client)
    - Priority level
    - Whether it's a daily project
    - Last worked date
    """
    projects = load_projects_from_supabase()
    
    if not projects:
        return "No projects are currently tracked. Ask me to add a project!"
    
    lines = ["# Tracked Projects\n"]
    
    for p in projects:
        status = "🟢" if p.get("path") else "🔴"
        daily_marker = " (DAILY)" if p.get("daily") else ""
        last_worked = p.get("last_worked", "Never")
        if isinstance(last_worked, str) and "T" in last_worked:
            last_worked = last_worked[:10]
        
        lines.append(f"## {status} {p.get('name', 'Unknown')}{daily_marker}")
        lines.append(f"- **Type**: {p.get('type', 'unknown')}")
        lines.append(f"- **Priority**: {p.get('priority', 999)}")
        lines.append(f"- **Path**: `{p.get('path') or 'Not configured'}`")
        lines.append(f"- **Last Worked**: {last_worked}")
        if p.get("description"):
            lines.append(f"- **Description**: {p.get('description')}")
        lines.append("")
    
    return "\n".join(lines)


@tool
def get_project_prd_status(project_name: str) -> str:
    """
    Get the PRD status for a specific project.
    
    Args:
        project_name: The name or ID of the project
    
    Returns detailed PRD status including:
    - Total number of PRDs
    - Current PRD being worked on
    - Next PRD in queue
    - Implementation status
    """
    projects = load_projects_from_supabase()
    
    # Find the project
    project = None
    for p in projects:
        if (p.get("id", "").lower() == project_name.lower() or 
            p.get("name", "").lower() == project_name.lower()):
            project = p
            break
    
    if not project:
        project_names = [p.get("name", "") for p in projects]
        return f"Project '{project_name}' not found. Available projects: {', '.join(project_names)}"
    
    if not project.get("path"):
        return f"Project '{project.get('name')}' does not have a path configured."
    
    prd_status_path = project.get("prd_status_path")
    if not prd_status_path:
        return f"Project '{project.get('name')}' does not have a PRD status file configured."
    
    # Try to load PRD status from the project path
    # Note: This only works when running locally, not on Render
    try:
        prd_status_file = Path(project["path"]) / prd_status_path
        
        if not prd_status_file.exists():
            return f"PRD status file not found. The project may only be accessible locally."
        
        with open(prd_status_file, "r") as f:
            prd_data = json.load(f)
        
        # Parse PRDs
        prds_raw = prd_data.get("prds", [])
        current_prd = None
        next_prd = None
        
        by_status = {}
        
        for prd_raw in prds_raw:
            status = prd_raw.get("status", "not_started")
            by_status[status] = by_status.get(status, 0) + 1
            
            if status == "in_progress" and not current_prd:
                current_prd = prd_raw
            elif status == "not_started" and not next_prd:
                next_prd = prd_raw
        
        # Build response
        lines = [f"# PRD Status: {project.get('name')}\n"]
        lines.append(f"**Total PRDs**: {len(prds_raw)}")
        
        if current_prd:
            lines.append(f"\n## 🔄 Currently Working On")
            lines.append(f"**{current_prd.get('id', 'Unknown')}**: {current_prd.get('name', 'Unnamed')}")
            if current_prd.get("priority"):
                lines.append(f"- Priority: {current_prd.get('priority')}")
        else:
            lines.append("\n## 🔄 Currently Working On")
            lines.append("No PRD currently in progress.")
        
        if next_prd:
            lines.append(f"\n## ⏭️ Next Up")
            lines.append(f"**{next_prd.get('id', 'Unknown')}**: {next_prd.get('name', 'Unnamed')}")
        
        lines.append("\n## 📊 Summary")
        for status, count in by_status.items():
            lines.append(f"- {status}: {count}")
        
        return "\n".join(lines)
        
    except Exception as e:
        logger.error(f"Error reading PRD status: {e}")
        return f"Could not read PRD status. This may only work when running locally. Error: {str(e)[:50]}"


@tool
def scan_and_add_project(project_path: str, project_name: Optional[str] = None, project_type: str = "client") -> str:
    """
    Add a new project to the registry.
    
    Args:
        project_path: Full path to the project folder
        project_name: Optional name for the project (auto-detected if not provided)
        project_type: Type of project (startup/personal/client)
    """
    path = Path(project_path)
    
    # Auto-detect project name
    if not project_name:
        project_name = path.name
    
    # Check for existing project
    projects = load_projects_from_supabase()
    for p in projects:
        if p.get("path") == str(path):
            return f"Project already registered: {p.get('name')}"
    
    # Determine priority
    max_priority = max((p.get("priority", 0) for p in projects), default=0)
    
    # Create project ID
    project_id = project_name.lower().replace(" ", "-").replace("_", "-")
    
    # Scan for PRD status file (only works locally)
    prd_status_path = None
    prd_locations = [
        "docs/prds/.prd-status.json",
        ".prd-status.json",
        "frontend/docs/prds/.prd-status.json",
    ]
    
    for loc in prd_locations:
        if (path / loc).exists():
            prd_status_path = loc
            break
    
    # Create project data
    project_data = {
        "id": project_id,
        "name": project_name,
        "path": str(path),
        "type": project_type,
        "priority": max_priority + 1,
        "daily": False,
        "prd_status_path": prd_status_path,
        "description": f"Added on {datetime.now().strftime('%Y-%m-%d')}",
        "created_at": datetime.now().isoformat(),
    }
    
    # Save to Supabase
    if save_project_to_supabase(project_data):
        lines = [f"✅ Added project: **{project_name}**\n"]
        lines.append(f"- **Path**: `{path}`")
        lines.append(f"- **Type**: {project_type}")
        lines.append(f"- **Priority**: {project_data['priority']}")
        
        if prd_status_path:
            lines.append(f"- **PRD Status**: Found at `{prd_status_path}`")
        else:
            lines.append("- **PRD Status**: Not found")
        
        return "\n".join(lines)
    else:
        return f"Failed to save project. Database may be unavailable."


@tool
def update_project_last_worked(project_name: str) -> str:
    """
    Update the last worked date for a project.
    
    Args:
        project_name: Name of the project
    
    Call this when finishing a work session on a project.
    """
    try:
        supabase = get_supabase_client()
        if not supabase:
            return "Database not connected."
        
        result = supabase.table("projects").update({
            "last_worked": datetime.now().isoformat()
        }).ilike("name", f"%{project_name}%").execute()
        
        if result.data:
            return f"Updated last worked for {project_name}."
        else:
            return f"Project not found: {project_name}"
            
    except Exception as e:
        logger.error(f"Error updating project: {e}")
        return f"Error: {str(e)}"


@tool
def suggest_next_project() -> str:
    """
    Suggest the best project to work on next based on:
    1. Days since last worked (stale projects get priority)
    2. Project type (client > personal)
    3. Priority ranking
    
    Use this when the user asks "What should I work on?" or "What's next?"
    """
    projects = load_projects_from_supabase()
    
    if not projects:
        return "No projects tracked. Add some projects first!"
    
    # Filter out daily projects (Sigmavue handled separately)
    candidates = [p for p in projects if not p.get("daily")]
    
    if not candidates:
        return "All your projects are daily projects. Focus on Sigmavue!"
    
    # Score each project
    scored = []
    for p in candidates:
        score = 0
        
        # Days since last worked (more days = higher score)
        last_worked = p.get("last_worked")
        if not last_worked:
            score += 100  # Never worked = highest priority
        else:
            try:
                last_date = datetime.fromisoformat(last_worked.replace("Z", "+00:00"))
                days_ago = (datetime.now() - last_date.replace(tzinfo=None)).days
                score += min(days_ago * 10, 100)  # Cap at 100
            except:
                score += 50
        
        # Type priority (client work pays bills)
        project_type = p.get("type", "personal")
        if project_type == "client":
            score += 30
        elif project_type == "startup":
            score += 20
        
        # Priority ranking (lower priority number = higher importance)
        priority = p.get("priority", 10)
        score += max(0, 20 - priority * 2)
        
        scored.append((p, score))
    
    # Sort by score (highest first)
    scored.sort(key=lambda x: x[1], reverse=True)
    
    # Build recommendation
    lines = ["# 🎯 Project Recommendation\n"]
    
    if scored:
        top = scored[0][0]
        lines.append(f"## Work on: **{top.get('name')}**\n")
        
        last_worked = top.get("last_worked")
        if last_worked:
            try:
                days = (datetime.now() - datetime.fromisoformat(last_worked.replace("Z", ""))).days
                lines.append(f"- Last touched: {days} days ago")
            except:
                lines.append("- Last touched: Unknown")
        else:
            lines.append("- Never worked on - fresh project!")
        
        lines.append(f"- Type: {top.get('type', 'unknown')}")
        lines.append(f"- Priority: {top.get('priority', 'N/A')}")
        
        if len(scored) > 1:
            lines.append("\n### Alternatives:")
            for proj, score in scored[1:4]:  # Show top 3 alternatives
                lines.append(f"- {proj.get('name')}")
    
    lines.append("\n---\n*Sigmavue is still your daily priority from 12-3pm.*")
    
    return "\n".join(lines)


@tool
def get_projects_needing_attention(days_threshold: int = 3) -> str:
    """
    Get projects that haven't been worked on recently.
    
    Args:
        days_threshold: Number of days of inactivity before flagging
    
    Returns list of projects that need attention.
    """
    projects = load_projects_from_supabase()
    
    if not projects:
        return "No projects tracked."
    
    from datetime import timedelta
    cutoff = datetime.now() - timedelta(days=days_threshold)
    
    stale_projects = []
    for p in projects:
        last_worked = p.get("last_worked")
        if not last_worked:
            stale_projects.append((p, "Never"))
        else:
            try:
                last_date = datetime.fromisoformat(last_worked.replace("Z", "+00:00"))
                if last_date < cutoff:
                    days_ago = (datetime.now() - last_date.replace(tzinfo=None)).days
                    stale_projects.append((p, f"{days_ago} days ago"))
            except:
                stale_projects.append((p, "Unknown"))
    
    if not stale_projects:
        return f"All projects have been worked on in the last {days_threshold} days. Nice!"
    
    lines = [f"# Projects Needing Attention\n"]
    lines.append(f"These haven't been touched in {days_threshold}+ days:\n")
    
    for proj, last_worked in stale_projects:
        lines.append(f"- **{proj.get('name')}** ({proj.get('type', 'unknown')})")
        lines.append(f"  Last worked: {last_worked}")
        lines.append("")
    
    return "\n".join(lines)
