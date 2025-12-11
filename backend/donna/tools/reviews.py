"""
Weekly review tools for Donna.

Generates weekly summaries and reflections.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from donna.config import get_settings
from donna.database import get_supabase_client

logger = logging.getLogger(__name__)


def get_week_data() -> dict:
    """Get data for the past week."""
    try:
        supabase = get_supabase_client()
        if not supabase:
            return {}
        
        week_ago = (datetime.now() - timedelta(days=7)).isoformat()
        
        # Get completed tasks
        tasks_result = supabase.table("tasks").select("*").eq(
            "status", "completed"
        ).gte("completed_at", week_ago).execute()
        
        # Get brain dumps
        dumps_result = supabase.table("brain_dumps").select("*").gte(
            "created_at", week_ago
        ).execute()
        
        # Get projects worked on
        projects_result = supabase.table("projects").select("*").gte(
            "last_worked", week_ago
        ).execute()
        
        return {
            "completed_tasks": tasks_result.data if tasks_result.data else [],
            "brain_dumps": dumps_result.data if dumps_result.data else [],
            "projects_worked": projects_result.data if projects_result.data else [],
        }
        
    except Exception as e:
        logger.error(f"Error getting week data: {e}")
        return {}


@tool
def generate_weekly_review() -> str:
    """
    Generate a weekly review summarizing accomplishments and setting focus for next week.
    
    This looks at:
    - Tasks completed
    - Brain dumps processed
    - Projects worked on
    - Patterns and insights
    
    Use this when the user asks:
    - "How was my week?"
    - "Weekly review"
    - "What did I accomplish?"
    """
    data = get_week_data()
    
    completed_tasks = data.get("completed_tasks", [])
    brain_dumps = data.get("brain_dumps", [])
    projects_worked = data.get("projects_worked", [])
    
    today = datetime.now()
    week_start = (today - timedelta(days=7)).strftime("%B %d")
    week_end = today.strftime("%B %d, %Y")
    
    lines = [f"# Weekly Review: {week_start} - {week_end}\n"]
    lines.append("*I've been watching. Here's what happened.*\n")
    
    # Accomplishments
    lines.append("## ✅ Tasks Completed")
    if completed_tasks:
        lines.append(f"You completed **{len(completed_tasks)}** tasks this week.\n")
        for task in completed_tasks[:10]:  # Show top 10
            lines.append(f"- {task.get('title', 'Unknown task')}")
    else:
        lines.append("No tasks completed. Interesting. We should talk about that.\n")
    
    # Projects
    lines.append("\n## 📁 Projects Worked On")
    if projects_worked:
        lines.append(f"You touched **{len(projects_worked)}** projects.\n")
        for proj in projects_worked:
            lines.append(f"- {proj.get('name', 'Unknown project')}")
    else:
        lines.append("No projects logged. Either you were slacking or not logging your work.\n")
    
    # Brain Dumps
    lines.append("\n## 💭 Brain Dumps")
    if brain_dumps:
        lines.append(f"**{len(brain_dumps)}** brain dumps captured.\n")
        lines.append("*Your ideas are safe with me.*")
    else:
        lines.append("No brain dumps. Your mind was either empty or too busy to share. I prefer busy.\n")
    
    # Stats
    lines.append("\n## 📊 Stats")
    lines.append(f"- Tasks: {len(completed_tasks)}")
    lines.append(f"- Projects: {len(projects_worked)}")
    lines.append(f"- Ideas: {len(brain_dumps)}")
    
    # Insights
    lines.append("\n## 💡 Insights")
    
    if len(completed_tasks) < 5:
        lines.append("- Task completion was low. Let's aim higher next week.")
    elif len(completed_tasks) > 15:
        lines.append("- Great task velocity! You were crushing it.")
    
    if len(projects_worked) < 2:
        lines.append("- Project diversity was low. Consider rotating more.")
    
    # Next Week Focus
    lines.append("\n## 🎯 Next Week Focus")
    lines.append("1. Sigmavue daily blocks (always)")
    lines.append("2. Clear your pending tasks")
    lines.append("3. Review projects that need attention")
    
    lines.append("\n---")
    lines.append("*Not bad. But I know you can do better. That's why you have me.*")
    
    return "\n".join(lines)


@tool
def generate_week_ahead() -> str:
    """
    Generate a preview of the week ahead.
    
    Shows what's coming up and suggests priorities.
    
    Use this when the user asks:
    - "What's coming up this week?"
    - "Week ahead"
    - "Plan my week"
    """
    try:
        supabase = get_supabase_client()
        
        # Get pending tasks
        pending_tasks = []
        if supabase:
            result = supabase.table("tasks").select("*").eq(
                "status", "pending"
            ).in_("priority", ["signal", "high", "medium"]).limit(10).execute()
            pending_tasks = result.data if result.data else []
        
        # Get projects needing attention
        from donna.tools.projects import load_projects_from_supabase
        projects = load_projects_from_supabase()
        
        today = datetime.now()
        week_end = (today + timedelta(days=7)).strftime("%B %d, %Y")
        
        lines = [f"# Week Ahead: Through {week_end}\n"]
        lines.append("*I've already planned it. You just have to show up.*\n")
        
        # Daily blocks
        lines.append("## 📅 Daily Blocks")
        lines.append("- **12-3pm**: Sigmavue (non-negotiable)")
        lines.append("- **3-3:30pm**: Break")
        lines.append("- **3:30-5pm**: Project Rotation 1")
        lines.append("- **5-7pm**: Project Rotation 2")
        
        # Priority tasks
        lines.append("\n## 🎯 Priority Tasks")
        if pending_tasks:
            for task in pending_tasks[:5]:
                priority = task.get("priority", "medium")
                emoji = "🔴" if priority in ["signal", "high"] else "🟡"
                lines.append(f"- {emoji} {task.get('title', 'Unknown')}")
        else:
            lines.append("- No pending tasks! Either clear or add some.")
        
        # Projects to focus on
        lines.append("\n## 📁 Projects for This Week")
        non_daily = [p for p in projects if not p.get("daily")][:3]
        for proj in non_daily:
            lines.append(f"- {proj.get('name', 'Unknown')}")
        
        lines.append("\n## 💪 Goals")
        lines.append("1. Complete all Sigmavue blocks")
        lines.append("2. Clear at least 5 tasks")
        lines.append("3. Touch 3+ projects")
        
        lines.append("\n---")
        lines.append("*You've got this. And you've got me. That's an unfair advantage.*")
        
        return "\n".join(lines)
        
    except Exception as e:
        logger.error(f"Error generating week ahead: {e}")
        return f"Error generating week ahead: {str(e)}"

