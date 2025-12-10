"""
Pydantic models for Donna's data structures.
"""

from datetime import datetime, date, time
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from uuid import UUID, uuid4


class ProjectType(str, Enum):
    """Type of project."""
    STARTUP = "startup"
    PERSONAL = "personal"
    CLIENT = "client"


class PRDStatus(str, Enum):
    """Status of a PRD."""
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    PARTIAL = "partial"
    COMPLETE = "complete"


class TaskPriority(str, Enum):
    """Priority level for tasks."""
    SIGNAL = "signal"  # Top priority - must do today
    LATER = "later"    # Important but can wait
    NOISE = "noise"    # Should be deferred/deleted


# ===========================================
# PROJECT MODELS
# ===========================================

class Project(BaseModel):
    """A tracked project."""
    id: str
    name: str
    path: Optional[str] = None
    type: ProjectType
    priority: int
    daily: bool = False
    work_block: Optional[str] = None
    prd_status_path: Optional[str] = None
    claude_md_path: Optional[str] = None
    description: Optional[str] = None
    last_worked: Optional[datetime] = None
    notes: Optional[str] = None


class ProjectRegistry(BaseModel):
    """Registry of all tracked projects."""
    version: str = "1.0.0"
    last_updated: datetime = Field(default_factory=datetime.now)
    projects: List[Project] = []
    rotation_config: Dict[str, Any] = {}


class PRDEntry(BaseModel):
    """A PRD entry from .prd-status.json."""
    id: str
    name: str
    file: Optional[str] = None
    file_path: Optional[str] = None
    status: PRDStatus = PRDStatus.NOT_STARTED
    priority: Optional[str] = None
    phase: Optional[int] = None
    implementation_notes: Optional[str] = None
    last_updated: Optional[str] = None


class ProjectPRDStatus(BaseModel):
    """PRD status for a project."""
    project_id: str
    project_name: str
    total_prds: int = 0
    current_prd: Optional[PRDEntry] = None
    next_prd: Optional[PRDEntry] = None
    prds: List[PRDEntry] = []


# ===========================================
# BRAIN DUMP MODELS
# ===========================================

class ActionItem(BaseModel):
    """An action item extracted from a brain dump."""
    id: UUID = Field(default_factory=uuid4)
    text: str
    priority: TaskPriority = TaskPriority.LATER
    project_ref: Optional[str] = None
    completed: bool = False


class BrainDump(BaseModel):
    """A brain dump entry."""
    id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=datetime.now)
    title: str
    content: str
    file_path: Optional[str] = None
    project_refs: List[str] = []
    action_items: List[ActionItem] = []
    tags: List[str] = []


# ===========================================
# SCHEDULE MODELS
# ===========================================

class TimeBlock(BaseModel):
    """A time block in the schedule."""
    id: UUID = Field(default_factory=uuid4)
    start: time
    end: time
    title: str
    type: str  # "personal", "work", "break", "call"
    project_id: Optional[str] = None
    prd_info: Optional[str] = None
    color: Optional[str] = None
    synced_to_calendar: bool = False
    calendar_event_id: Optional[str] = None


class DailySchedule(BaseModel):
    """A daily schedule."""
    date: date
    time_blocks: List[TimeBlock] = []
    signal_tasks: List[str] = []  # Top 3 tasks
    notes: Optional[str] = None
    synced_to_calendar: bool = False
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class WeeklyTemplate(BaseModel):
    """Weekly schedule template."""
    version: str = "1.0.0"
    timezone: str = "America/New_York"
    personal_blocks: Dict[str, Any] = {}
    work_blocks: Dict[str, Any] = {}
    day_overrides: Dict[str, Any] = {}
    automation_schedule: Dict[str, Any] = {}
    priority_rules: Dict[str, Any] = {}


# ===========================================
# HANDOFF MODELS
# ===========================================

class Handoff(BaseModel):
    """A handoff document for a project."""
    id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=datetime.now)
    project_id: str
    project_name: str
    title: str
    context: str
    current_prd: Optional[str] = None
    next_prd: Optional[str] = None
    action_items: List[str] = []
    file_path: Optional[str] = None


# ===========================================
# MORNING BRIEF MODEL
# ===========================================

class MorningBrief(BaseModel):
    """The morning brief sent to Telegram."""
    date: date
    schedule: DailySchedule
    signal_tasks: List[str]
    calls_today: List[Dict[str, str]] = []
    projects_today: List[Dict[str, Any]] = []
    notes: Optional[str] = None


