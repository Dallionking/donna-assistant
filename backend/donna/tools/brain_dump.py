"""
Brain dump tools for Donna.

Handles creating, organizing, and searching brain dumps.
"""

import json
import re
from pathlib import Path
from typing import List, Optional
from datetime import datetime
from uuid import uuid4

from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from donna.config import get_settings, get_brain_dumps_path
from donna.models import BrainDump, ActionItem, TaskPriority


def get_brain_dump_file_path(title: str, timestamp: datetime = None) -> Path:
    """Generate the file path for a brain dump."""
    if timestamp is None:
        timestamp = datetime.now()
    
    base_path = get_brain_dumps_path()
    year = timestamp.strftime("%Y")
    month = timestamp.strftime("%m-%B").lower()
    
    # Create slug from title
    slug = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')[:50]
    
    filename = f"{timestamp.strftime('%Y-%m-%d_%H%M')}_{slug}.md"
    
    return base_path / year / month / filename


def ensure_directory(path: Path) -> None:
    """Ensure directory exists."""
    path.parent.mkdir(parents=True, exist_ok=True)


@tool
def create_brain_dump(content: str, title: Optional[str] = None) -> str:
    """
    Create a new brain dump from the provided content.
    
    Args:
        content: The raw content of the brain dump (from voice or text)
        title: Optional title (auto-generated if not provided)
    
    The brain dump will be:
    1. Saved to the appropriate date-organized folder
    2. Analyzed for action items
    3. Classified as Signal/Noise
    4. Cross-referenced with projects
    
    Returns the path to the created file and extracted action items.
    """
    settings = get_settings()
    timestamp = datetime.now()
    
    # Auto-generate title if not provided
    if not title:
        # Use first 50 chars or first sentence
        first_line = content.split('\n')[0][:50]
        title = re.sub(r'[^a-zA-Z0-9\s]', '', first_line).strip() or "Brain Dump"
    
    # Get file path
    file_path = get_brain_dump_file_path(title, timestamp)
    ensure_directory(file_path)
    
    # Create the brain dump object
    brain_dump = BrainDump(
        id=uuid4(),
        created_at=timestamp,
        title=title,
        content=content,
        file_path=str(file_path),
    )
    
    # Build markdown content
    md_lines = [
        f"# {title}",
        "",
        f"**Date**: {timestamp.strftime('%A, %B %d, %Y at %I:%M %p')}",
        "",
        "---",
        "",
        "## Raw Dump",
        "",
        content,
        "",
        "---",
        "",
        "## Analysis",
        "",
        "*To be processed by Donna*",
        "",
    ]
    
    # Write file
    with open(file_path, "w") as f:
        f.write("\n".join(md_lines))
    
    return f"""✅ Brain dump created!

**Title**: {title}
**File**: `{file_path}`
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
    brain_dumps_path = get_brain_dumps_path()
    
    if not brain_dumps_path.exists():
        return "No brain dumps found. Start by creating one with /braindump."
    
    # Find all markdown files
    all_dumps = list(brain_dumps_path.rglob("*.md"))
    
    if not all_dumps:
        return "No brain dumps found."
    
    # Simple text search (in production, use vector search with Supabase)
    query_lower = query.lower()
    matches = []
    
    for dump_file in all_dumps:
        try:
            with open(dump_file, "r") as f:
                content = f.read()
            
            if query_lower in content.lower():
                # Extract title and excerpt
                lines = content.split('\n')
                title = lines[0].replace('#', '').strip() if lines else "Untitled"
                
                # Find the matching line for context
                excerpt = ""
                for line in lines:
                    if query_lower in line.lower():
                        excerpt = line[:200]
                        break
                
                matches.append({
                    "file": str(dump_file),
                    "title": title,
                    "excerpt": excerpt,
                    "date": dump_file.stem.split('_')[0] if '_' in dump_file.stem else "Unknown",
                })
        except Exception:
            continue
    
    if not matches:
        return f"No brain dumps found matching '{query}'."
    
    # Sort by date (newest first) and limit
    matches = sorted(matches, key=lambda x: x["date"], reverse=True)[:limit]
    
    lines = [f"# Brain Dumps matching '{query}'\n"]
    lines.append(f"Found {len(matches)} result(s):\n")
    
    for i, match in enumerate(matches, 1):
        lines.append(f"## {i}. {match['title']}")
        lines.append(f"**Date**: {match['date']}")
        lines.append(f"**File**: `{match['file']}`")
        if match['excerpt']:
            lines.append(f"**Excerpt**: ...{match['excerpt']}...")
        lines.append("")
    
    return "\n".join(lines)


@tool
def extract_action_items(brain_dump_path: str) -> str:
    """
    Extract and classify action items from a brain dump.
    
    Args:
        brain_dump_path: Path to the brain dump file
    
    Returns:
    - List of action items
    - Classification as Signal (must do today) or Noise (defer/delete)
    - Project associations
    """
    path = Path(brain_dump_path)
    
    if not path.exists():
        return f"Brain dump not found: {brain_dump_path}"
    
    with open(path, "r") as f:
        content = f.read()
    
    # Use GPT to extract action items
    settings = get_settings()
    llm = ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0.3,
        api_key=settings.openai_api_key,
    )
    
    extraction_prompt = f"""Analyze this brain dump and extract action items.

For each action item, classify it as:
- SIGNAL: Must be done in the next 18 hours, directly moves the needle
- LATER: Important but can wait
- NOISE: Should be deferred, delegated, or deleted

Also identify which project it relates to (if any):
- SigmaView (trading platform)
- SSS (PRD generation)
- RuthlessApp (productivity app)
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
    
    # Append analysis to the brain dump file
    with open(path, "a") as f:
        f.write("\n---\n\n## Extracted Action Items\n\n")
        f.write(response.content)
        f.write(f"\n\n*Analyzed at {datetime.now().strftime('%I:%M %p')}*\n")
    
    return f"""Action items extracted and saved to brain dump!

{response.content}

The analysis has been appended to: `{path}`
"""


