"""
Database operations for Donna using Supabase.

Handles:
- Brain dump storage with vector embeddings
- Schedule persistence
- Project tracking
- Conversation memory
"""

from datetime import datetime, date
from typing import Optional, List, Dict, Any
from uuid import UUID

from supabase import create_client, Client

from donna.config import get_settings
from donna.models import BrainDump, DailySchedule, Project


# Singleton Supabase client
_client: Optional[Client] = None


def get_supabase_client() -> Client:
    """Get or create Supabase client."""
    global _client
    if _client is None:
        settings = get_settings()
        _client = create_client(
            settings.supabase_url,
            settings.supabase_service_key
        )
    return _client


# ===========================================
# BRAIN DUMPS
# ===========================================

async def save_brain_dump(brain_dump: BrainDump) -> str:
    """Save a brain dump to Supabase."""
    client = get_supabase_client()
    
    data = {
        "id": str(brain_dump.id),
        "created_at": brain_dump.created_at.isoformat(),
        "title": brain_dump.title,
        "content": brain_dump.content,
        "file_path": brain_dump.file_path,
        "project_refs": brain_dump.project_refs,
        "action_items": [item.model_dump() for item in brain_dump.action_items],
        "tags": brain_dump.tags,
    }
    
    result = client.table("brain_dumps").insert(data).execute()
    return str(brain_dump.id)


async def search_brain_dumps_vector(query: str, limit: int = 5) -> List[Dict[str, Any]]:
    """
    Search brain dumps using vector similarity.
    
    Requires embedding the query and using Supabase's vector search.
    """
    client = get_supabase_client()
    
    # TODO: Generate embedding for query using OpenAI
    # Then use Supabase's vector similarity search
    
    # For now, do a simple text search
    result = client.table("brain_dumps")\
        .select("*")\
        .ilike("content", f"%{query}%")\
        .limit(limit)\
        .execute()
    
    return result.data


async def get_brain_dumps_by_date(target_date: date) -> List[Dict[str, Any]]:
    """Get all brain dumps for a specific date."""
    client = get_supabase_client()
    
    start = datetime.combine(target_date, datetime.min.time())
    end = datetime.combine(target_date, datetime.max.time())
    
    result = client.table("brain_dumps")\
        .select("*")\
        .gte("created_at", start.isoformat())\
        .lte("created_at", end.isoformat())\
        .order("created_at", desc=True)\
        .execute()
    
    return result.data


# ===========================================
# SCHEDULES
# ===========================================

async def save_daily_schedule(schedule: DailySchedule) -> str:
    """Save a daily schedule to Supabase."""
    client = get_supabase_client()
    
    data = {
        "date": schedule.date.isoformat(),
        "time_blocks": [block.model_dump() for block in schedule.time_blocks],
        "signal_tasks": schedule.signal_tasks,
        "notes": schedule.notes,
        "synced_to_calendar": schedule.synced_to_calendar,
        "updated_at": datetime.now().isoformat(),
    }
    
    # Upsert by date
    result = client.table("daily_schedules")\
        .upsert(data, on_conflict="date")\
        .execute()
    
    return schedule.date.isoformat()


async def get_daily_schedule(target_date: date) -> Optional[Dict[str, Any]]:
    """Get the schedule for a specific date."""
    client = get_supabase_client()
    
    result = client.table("daily_schedules")\
        .select("*")\
        .eq("date", target_date.isoformat())\
        .single()\
        .execute()
    
    return result.data if result.data else None


# ===========================================
# PROJECTS
# ===========================================

async def sync_projects_to_db(projects: List[Project]) -> None:
    """Sync project registry to Supabase."""
    client = get_supabase_client()
    
    for project in projects:
        data = {
            "id": project.id,
            "name": project.name,
            "path": project.path,
            "type": project.type.value if hasattr(project.type, 'value') else project.type,
            "priority": project.priority,
            "daily": project.daily,
            "prd_status_path": project.prd_status_path,
            "description": project.description,
            "last_worked": project.last_worked.isoformat() if project.last_worked else None,
        }
        
        client.table("projects")\
            .upsert(data, on_conflict="id")\
            .execute()


async def update_project_last_worked(project_id: str) -> None:
    """Update the last_worked timestamp for a project."""
    client = get_supabase_client()
    
    client.table("projects")\
        .update({"last_worked": datetime.now().isoformat()})\
        .eq("id", project_id)\
        .execute()


# ===========================================
# MEMORY (Conversation History)
# ===========================================

async def save_memory(topic: str, content: str) -> str:
    """Save a conversation memory entry."""
    client = get_supabase_client()
    
    data = {
        "topic": topic,
        "content": content,
        "created_at": datetime.now().isoformat(),
    }
    
    result = client.table("memory").insert(data).execute()
    return result.data[0]["id"] if result.data else ""


async def search_memory(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Search conversation memory."""
    client = get_supabase_client()
    
    # Simple text search for now
    result = client.table("memory")\
        .select("*")\
        .or_(f"topic.ilike.%{query}%,content.ilike.%{query}%")\
        .order("created_at", desc=True)\
        .limit(limit)\
        .execute()
    
    return result.data


# ===========================================
# SCHEMA SETUP
# ===========================================

SCHEMA_SQL = """
-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Brain dumps with vector embeddings
CREATE TABLE IF NOT EXISTS brain_dumps (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    title TEXT,
    content TEXT,
    file_path TEXT,
    project_refs TEXT[],
    action_items JSONB,
    tags TEXT[],
    embedding VECTOR(1536)
);

-- Create index for vector similarity search
CREATE INDEX IF NOT EXISTS brain_dumps_embedding_idx 
ON brain_dumps USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- Daily schedules
CREATE TABLE IF NOT EXISTS daily_schedules (
    date DATE PRIMARY KEY,
    time_blocks JSONB,
    signal_tasks TEXT[],
    notes TEXT,
    synced_to_calendar BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Project registry
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    path TEXT,
    type TEXT,
    priority INTEGER,
    daily BOOLEAN DEFAULT FALSE,
    prd_status_path TEXT,
    description TEXT,
    last_worked TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Conversation memory with embeddings
CREATE TABLE IF NOT EXISTS memory (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    topic TEXT,
    content TEXT,
    embedding VECTOR(1536)
);

-- Create index for memory vector search
CREATE INDEX IF NOT EXISTS memory_embedding_idx 
ON memory USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- Calendly events cache
CREATE TABLE IF NOT EXISTS calendly_events (
    id TEXT PRIMARY KEY,
    event_type TEXT,
    start_time TIMESTAMPTZ,
    end_time TIMESTAMPTZ,
    invitee_name TEXT,
    invitee_email TEXT,
    status TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Row Level Security (RLS) policies
-- Note: For a personal assistant, you might not need RLS
-- but it's good practice for future multi-user support

-- Enable RLS
ALTER TABLE brain_dumps ENABLE ROW LEVEL SECURITY;
ALTER TABLE daily_schedules ENABLE ROW LEVEL SECURITY;
ALTER TABLE projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE memory ENABLE ROW LEVEL SECURITY;
ALTER TABLE calendly_events ENABLE ROW LEVEL SECURITY;

-- Create policies (allow all for service role)
CREATE POLICY "Allow all for service role" ON brain_dumps FOR ALL USING (true);
CREATE POLICY "Allow all for service role" ON daily_schedules FOR ALL USING (true);
CREATE POLICY "Allow all for service role" ON projects FOR ALL USING (true);
CREATE POLICY "Allow all for service role" ON memory FOR ALL USING (true);
CREATE POLICY "Allow all for service role" ON calendly_events FOR ALL USING (true);
"""


async def setup_schema() -> str:
    """
    Set up the database schema.
    
    Run this once to create all tables.
    """
    # This should be run via Supabase SQL editor or migrations
    return f"""
To set up the database schema, run this SQL in Supabase:

{SCHEMA_SQL}

You can run this via:
1. Supabase Dashboard > SQL Editor
2. Or use the Supabase MCP to execute it
"""


