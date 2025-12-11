"""
Task management tools for Donna.

Natural language task creation, management, and tracking.
All data stored in Supabase.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, List
from uuid import uuid4

from langchain_core.tools import tool

from donna.config import get_settings
from donna.database import get_supabase_client

logger = logging.getLogger(__name__)


@tool
def add_task(
    title: str,
    priority: str = "medium",
    project: Optional[str] = None,
    due_date: Optional[str] = None,
    description: Optional[str] = None
) -> str:
    """
    Add a new task to the task list.
    
    Args:
        title: What needs to be done (e.g., "Call the client", "Review PR")
        priority: high/medium/low or signal/noise (default: medium)
        project: Associated project (e.g., "sigmavue", "academy")
        due_date: When it's due (e.g., "today", "tomorrow", "2024-12-15")
        description: Additional details
    
    Use this when the user says things like:
    - "Add X to my tasks"
    - "Remind me to X"
    - "I need to do X"
    - "Add this to my todo list"
    """
    try:
        supabase = get_supabase_client()
        if not supabase:
            return "Database not connected. Task not saved."
        
        task_id = str(uuid4())
        
        # Parse due date
        parsed_due = None
        if due_date:
            if due_date.lower() == "today":
                parsed_due = datetime.now().replace(hour=23, minute=59).isoformat()
            elif due_date.lower() == "tomorrow":
                parsed_due = (datetime.now() + timedelta(days=1)).replace(hour=23, minute=59).isoformat()
            else:
                try:
                    parsed_due = datetime.fromisoformat(due_date).isoformat()
                except:
                    pass
        
        # Normalize priority
        priority = priority.lower()
        if priority not in ["high", "medium", "low", "signal", "noise"]:
            priority = "medium"
        
        # Insert task
        result = supabase.table("tasks").insert({
            "id": task_id,
            "title": title,
            "description": description,
            "priority": priority,
            "status": "pending",
            "project_id": project.lower() if project else None,
            "due_date": parsed_due,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }).execute()
        
        if result.data:
            priority_emoji = "🔴" if priority in ["high", "signal"] else "🟡" if priority == "medium" else "🟢"
            
            return f"""✅ Task added!

{priority_emoji} **{title}**
- Priority: {priority}
{f"- Project: {project}" if project else ""}
{f"- Due: {due_date}" if due_date else ""}

I've got it tracked. One less thing for you to remember.
"""
        else:
            return "Failed to add task. Try again."
            
    except Exception as e:
        logger.error(f"Error adding task: {e}")
        return f"Error adding task: {str(e)}"


@tool
def get_tasks(
    status: str = "pending",
    project: Optional[str] = None,
    priority: Optional[str] = None,
    limit: int = 10
) -> str:
    """
    Get tasks from the task list.
    
    Args:
        status: pending/in_progress/completed/all (default: pending)
        project: Filter by project
        priority: Filter by priority (high/medium/low/signal/noise)
        limit: Maximum number to return
    
    Use this when the user asks:
    - "What do I need to do?"
    - "What's on my list?"
    - "Show my tasks"
    - "What are my todos?"
    """
    try:
        supabase = get_supabase_client()
        if not supabase:
            return "Database not connected."
        
        query = supabase.table("tasks").select("*")
        
        # Filter by status
        if status != "all":
            query = query.eq("status", status)
        
        # Filter by project
        if project:
            query = query.eq("project_id", project.lower())
        
        # Filter by priority
        if priority:
            query = query.eq("priority", priority.lower())
        
        # Order and limit
        query = query.order("priority").order("created_at", desc=True).limit(limit)
        
        result = query.execute()
        
        if not result.data:
            if status == "pending":
                return "No pending tasks. Impressive. Or suspicious. Are you sure you're being productive?"
            return f"No {status} tasks found."
        
        lines = [f"# Your Tasks ({len(result.data)})\n"]
        
        # Group by priority
        by_priority = {"signal": [], "high": [], "medium": [], "low": [], "noise": []}
        for task in result.data:
            p = task.get("priority", "medium")
            if p in by_priority:
                by_priority[p].append(task)
            else:
                by_priority["medium"].append(task)
        
        # Display
        priority_emojis = {
            "signal": "🎯",
            "high": "🔴",
            "medium": "🟡",
            "low": "🟢",
            "noise": "⚪"
        }
        
        for priority_level, tasks in by_priority.items():
            if tasks:
                lines.append(f"\n## {priority_emojis.get(priority_level, '•')} {priority_level.title()} Priority\n")
                for task in tasks:
                    title = task.get("title", "Untitled")
                    project_id = task.get("project_id", "")
                    status_emoji = "✅" if task.get("status") == "completed" else "⬜"
                    
                    line = f"- {status_emoji} {title}"
                    if project_id:
                        line += f" ({project_id})"
                    lines.append(line)
        
        return "\n".join(lines)
        
    except Exception as e:
        logger.error(f"Error getting tasks: {e}")
        return f"Error: {str(e)}"


@tool
def complete_task(task_title: str) -> str:
    """
    Mark a task as completed.
    
    Args:
        task_title: The title or partial title of the task to complete
    
    Use this when the user says:
    - "Done with X"
    - "Mark X as complete"
    - "Finished X"
    - "I completed X"
    """
    try:
        supabase = get_supabase_client()
        if not supabase:
            return "Database not connected."
        
        # Find the task by partial title match
        result = supabase.table("tasks").select("*").ilike(
            "title", f"%{task_title}%"
        ).eq("status", "pending").limit(1).execute()
        
        if not result.data:
            return f"Couldn't find a pending task matching '{task_title}'. Are you sure it exists?"
        
        task = result.data[0]
        
        # Update to completed
        supabase.table("tasks").update({
            "status": "completed",
            "completed_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }).eq("id", task["id"]).execute()
        
        return f"""✅ Done!

**{task.get('title')}** marked as complete.

One down. Want to see what's left? Just ask.
"""
        
    except Exception as e:
        logger.error(f"Error completing task: {e}")
        return f"Error: {str(e)}"


@tool
def delete_task(task_title: str) -> str:
    """
    Delete a task from the list.
    
    Args:
        task_title: The title or partial title of the task to delete
    
    Use this when the user says:
    - "Delete X"
    - "Remove X from my tasks"
    - "Cancel X"
    - "Forget about X"
    """
    try:
        supabase = get_supabase_client()
        if not supabase:
            return "Database not connected."
        
        # Find the task
        result = supabase.table("tasks").select("*").ilike(
            "title", f"%{task_title}%"
        ).limit(1).execute()
        
        if not result.data:
            return f"Couldn't find a task matching '{task_title}'."
        
        task = result.data[0]
        
        # Delete it
        supabase.table("tasks").delete().eq("id", task["id"]).execute()
        
        return f"🗑️ Deleted: **{task.get('title')}**\n\nGone. Like it never happened."
        
    except Exception as e:
        logger.error(f"Error deleting task: {e}")
        return f"Error: {str(e)}"


@tool
def get_signal_tasks() -> str:
    """
    Get the top Signal tasks - the ones that matter most.
    
    These are high priority tasks that move the needle.
    Signal > Noise, always.
    
    Use this when the user asks:
    - "What should I focus on?"
    - "What's the priority?"
    - "What's important today?"
    """
    try:
        supabase = get_supabase_client()
        if not supabase:
            return "Database not connected."
        
        # Get signal and high priority tasks
        result = supabase.table("tasks").select("*").in_(
            "priority", ["signal", "high"]
        ).eq("status", "pending").order("created_at").limit(5).execute()
        
        if not result.data:
            # No high priority, get top medium
            result = supabase.table("tasks").select("*").eq(
                "priority", "medium"
            ).eq("status", "pending").limit(3).execute()
        
        if not result.data:
            return """No priority tasks right now.

Either you're crushing it, or you haven't told me what matters.

Use: "Add [task] to my tasks with high priority"
"""
        
        lines = ["# 🎯 Signal Tasks (Focus Here)\n"]
        
        for i, task in enumerate(result.data, 1):
            title = task.get("title", "Untitled")
            project = task.get("project_id", "")
            
            lines.append(f"{i}. **{title}**")
            if project:
                lines.append(f"   → {project}")
        
        lines.append("\n---\nThese move the needle. Everything else is noise.")
        
        return "\n".join(lines)
        
    except Exception as e:
        logger.error(f"Error getting signal tasks: {e}")
        return f"Error: {str(e)}"


@tool
def update_task_priority(task_title: str, new_priority: str) -> str:
    """
    Update the priority of a task.
    
    Args:
        task_title: The title or partial title of the task
        new_priority: The new priority (signal/high/medium/low/noise)
    
    Use this when the user says:
    - "Make X high priority"
    - "X is urgent"
    - "Move X to signal"
    """
    try:
        supabase = get_supabase_client()
        if not supabase:
            return "Database not connected."
        
        # Find the task
        result = supabase.table("tasks").select("*").ilike(
            "title", f"%{task_title}%"
        ).limit(1).execute()
        
        if not result.data:
            return f"Couldn't find a task matching '{task_title}'."
        
        task = result.data[0]
        
        # Normalize priority
        new_priority = new_priority.lower()
        if new_priority not in ["signal", "high", "medium", "low", "noise"]:
            return f"Invalid priority '{new_priority}'. Use: signal, high, medium, low, or noise."
        
        # Update
        supabase.table("tasks").update({
            "priority": new_priority,
            "updated_at": datetime.now().isoformat(),
        }).eq("id", task["id"]).execute()
        
        priority_emoji = "🎯" if new_priority == "signal" else "🔴" if new_priority == "high" else "🟡"
        
        return f"""{priority_emoji} Priority updated!

**{task.get('title')}** is now {new_priority} priority.
"""
        
    except Exception as e:
        logger.error(f"Error updating priority: {e}")
        return f"Error: {str(e)}"

