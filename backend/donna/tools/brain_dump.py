"""
Brain dump tools for Donna.

Handles creating, organizing, and searching brain dumps.
All data stored in Supabase - NO local file access.
"""

import json
import re
import logging
from typing import List, Optional
from datetime import datetime
from uuid import uuid4

from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from donna.config import get_settings
from donna.models import BrainDump, ActionItem, TaskPriority
from donna.database import get_supabase_client

logger = logging.getLogger(__name__)


@tool
def create_brain_dump(content: str, title: Optional[str] = None) -> str:
    """
    Create a new brain dump from the provided content.
    
    Args:
        content: The raw content of the brain dump (from voice or text)
        title: Optional title (auto-generated if not provided)
    
    The brain dump will be:
    1. Saved to Supabase
    2. Analyzed for action items
    3. Classified as Signal/Noise
    4. Cross-referenced with projects
    
    Returns confirmation and extracted action items.
    """
    timestamp = datetime.now()
    
    # Auto-generate title if not provided
    if not title:
        first_line = content.split('\n')[0][:50]
        title = re.sub(r'[^a-zA-Z0-9\s]', '', first_line).strip() or "Brain Dump"
    
    # Create unique ID
    brain_dump_id = str(uuid4())
    
    # Store in Supabase
    try:
        supabase = get_supabase_client()
        if supabase:
            result = supabase.table("brain_dumps").insert({
                "id": brain_dump_id,
                "title": title,
                "content": content,
                "raw_content": content,
                "classification": "pending",
                "created_at": timestamp.isoformat(),
            }).execute()
            
            if result.data:
                logger.info(f"Brain dump saved to Supabase: {brain_dump_id}")
        else:
            logger.warning("Supabase not available, brain dump stored in memory only")
    except Exception as e:
        logger.error(f"Failed to save brain dump to Supabase: {e}")

    return f"""✅ Brain dump created!

**Title**: {title}
**ID**: `{brain_dump_id[:8]}...`
**Time**: {timestamp.strftime('%I:%M %p')}

The brain dump has been saved. Would you like me to:
1. Extract action items and classify them as Signal/Noise?
2. Link this to a specific project?
3. Search for related past brain dumps?
"""


@tool
def search_brain_dumps(query: str, limit: int = 5) -> str:
    """
    Search past brain dumps for a specific topic.
    
    Args:
        query: The search query (topic, project name, or keyword)
        limit: Maximum number of results to return
    
    Returns matching brain dumps with excerpts.
    """
    try:
        supabase = get_supabase_client()
        if not supabase:
            return "Database not connected. Cannot search brain dumps."
        
        # Search using ilike for simple text matching
        # In production, you'd use vector search with embeddings
        result = supabase.table("brain_dumps").select("*").ilike(
            "content", f"%{query}%"
        ).order("created_at", desc=True).limit(limit).execute()
        
        if not result.data:
            return f"No brain dumps found matching '{query}'."
        
        lines = [f"# Brain Dumps matching '{query}'\n"]
        lines.append(f"Found {len(result.data)} result(s):\n")
        
        for i, dump in enumerate(result.data, 1):
            title = dump.get("title", "Untitled")
            created = dump.get("created_at", "Unknown")[:10]
            content = dump.get("content", "")[:200]
            
            lines.append(f"## {i}. {title}")
            lines.append(f"**Date**: {created}")
            lines.append(f"**ID**: `{dump.get('id', '')[:8]}...`")
            if content:
                lines.append(f"**Excerpt**: ...{content}...")
            lines.append("")
        
        return "\n".join(lines)
        
    except Exception as e:
        logger.error(f"Error searching brain dumps: {e}")
        return f"Error searching brain dumps: {str(e)}"


@tool
def extract_action_items(brain_dump_id: str) -> str:
    """
    Extract and classify action items from a brain dump.
    
    Args:
        brain_dump_id: ID of the brain dump (or partial ID)
    
    Returns:
    - List of action items
    - Classification as Signal (must do today) or Noise (defer/delete)
    - Project associations
    """
    try:
        supabase = get_supabase_client()
        if not supabase:
            return "Database not connected."
        
        # Find the brain dump (support partial ID match)
        result = supabase.table("brain_dumps").select("*").ilike(
            "id", f"{brain_dump_id}%"
        ).limit(1).execute()
        
        if not result.data:
            return f"Brain dump not found with ID starting with: {brain_dump_id}"
        
        dump = result.data[0]
        content = dump.get("content", "")
        
        # Use GPT to extract action items
        settings = get_settings()
        llm = ChatOpenAI(
            model="gpt-5.1",
            temperature=0.3,
            api_key=settings.openai_api_key,
        )
        
        extraction_prompt = f"""Analyze this brain dump and extract action items.

For each action item, classify it as:
- SIGNAL: Must be done in the next 18 hours, directly moves the needle
- LATER: Important but can wait
- NOISE: Should be deferred, delegated, or deleted

Also identify which project it relates to (if any):
- Sigmavue (trading platform)
- SSS (PRD generation)
- RuthlessApp (productivity app)
- Academy
- Or other client projects

Brain Dump Content:
---
{content}
---

Respond in this exact format:

## Action Items

### Signal (Top Priority)
- [ ] [Action item] → [Project or "Personal"]

### Later
- [ ] [Action item] → [Project or "Personal"]

### Noise (Defer/Delete)
- [ ] [Action item] → Reason to defer/delete
"""

        response = llm.invoke(extraction_prompt)
        analysis = response.content
        
        # Update the brain dump with analysis
        supabase.table("brain_dumps").update({
            "action_items": analysis,
            "classification": "analyzed",
            "analyzed_at": datetime.now().isoformat(),
        }).eq("id", dump["id"]).execute()
        
        return f"""Action items extracted and saved!

{analysis}

The analysis has been saved to the brain dump.
"""
        
    except Exception as e:
        logger.error(f"Error extracting action items: {e}")
        return f"Error extracting action items: {str(e)}"


@tool
def get_recent_brain_dumps(limit: int = 5) -> str:
    """
    Get the most recent brain dumps.
    
    Args:
        limit: Maximum number to return
    
    Returns list of recent brain dumps.
    """
    try:
        supabase = get_supabase_client()
        if not supabase:
            return "Database not connected."
        
        result = supabase.table("brain_dumps").select(
            "id, title, created_at, classification"
        ).order("created_at", desc=True).limit(limit).execute()
        
        if not result.data:
            return "No brain dumps found. Start by sending me your thoughts!"
        
        lines = ["# Recent Brain Dumps\n"]
        
        for dump in result.data:
            title = dump.get("title", "Untitled")
            created = dump.get("created_at", "")[:10]
            status = dump.get("classification", "pending")
            
            status_emoji = "✅" if status == "analyzed" else "⏳"
            lines.append(f"- {status_emoji} **{title}** ({created})")
        
        return "\n".join(lines)
        
    except Exception as e:
        logger.error(f"Error getting brain dumps: {e}")
        return f"Error: {str(e)}"
