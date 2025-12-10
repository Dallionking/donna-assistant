"""
Project management tools for Donna.

Handles reading project registry, PRD status, and project discovery.
"""

import json
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime

from langchain_core.tools import tool

from donna.config import get_projects_registry_path
from donna.models import Project, ProjectRegistry, PRDEntry, ProjectPRDStatus, PRDStatus


def load_project_registry() -> ProjectRegistry:
    """Load the project registry from disk."""
    registry_path = get_projects_registry_path()
    
    if not registry_path.exists():
        return ProjectRegistry()
    
    with open(registry_path, "r") as f:
        data = json.load(f)
    
    projects = [Project(**p) for p in data.get("projects", [])]
    return ProjectRegistry(
        version=data.get("version", "1.0.0"),
        last_updated=datetime.fromisoformat(data.get("last_updated", datetime.now().isoformat())),
        projects=projects,
        rotation_config=data.get("rotation_config", {}),
    )


def save_project_registry(registry: ProjectRegistry) -> None:
    """Save the project registry to disk."""
    registry_path = get_projects_registry_path()
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    
    data = {
        "version": registry.version,
        "last_updated": datetime.now().isoformat(),
        "projects": [p.model_dump() for p in registry.projects],
        "rotation_config": registry.rotation_config,
    }
    
    with open(registry_path, "w") as f:
        json.dump(data, f, indent=2, default=str)


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
    registry = load_project_registry()
    
    if not registry.projects:
        return "No projects are currently tracked. Use /project add to add a project."
    
    lines = ["# Tracked Projects\n"]
    
    for p in sorted(registry.projects, key=lambda x: x.priority):
        status = "🟢" if p.path else "🔴"
        daily_marker = " (DAILY)" if p.daily else ""
        last_worked = p.last_worked.strftime("%Y-%m-%d") if p.last_worked else "Never"
        
        lines.append(f"## {status} {p.name}{daily_marker}")
        lines.append(f"- **Type**: {p.type.value}")
        lines.append(f"- **Priority**: {p.priority}")
        lines.append(f"- **Path**: `{p.path or 'Not configured'}`")
        lines.append(f"- **Last Worked**: {last_worked}")
        if p.description:
            lines.append(f"- **Description**: {p.description}")
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
    registry = load_project_registry()
    
    # Find the project
    project = None
    for p in registry.projects:
        if p.id.lower() == project_name.lower() or p.name.lower() == project_name.lower():
            project = p
            break
    
    if not project:
        return f"Project '{project_name}' not found. Available projects: {', '.join(p.name for p in registry.projects)}"
    
    if not project.path:
        return f"Project '{project.name}' does not have a path configured."
    
    if not project.prd_status_path:
        return f"Project '{project.name}' does not have a PRD status file configured."
    
    # Load PRD status
    prd_status_file = Path(project.path) / project.prd_status_path
    
    if not prd_status_file.exists():
        return f"PRD status file not found at: {prd_status_file}"
    
    with open(prd_status_file, "r") as f:
        prd_data = json.load(f)
    
    # Parse PRDs
    prds_raw = prd_data.get("prds", [])
    prds = []
    current_prd = None
    next_prd = None
    
    for prd_raw in prds_raw:
        prd = PRDEntry(
            id=prd_raw.get("id", ""),
            name=prd_raw.get("name", ""),
            file=prd_raw.get("file"),
            file_path=prd_raw.get("file_path"),
            status=PRDStatus(prd_raw.get("status", "not_started")),
            priority=prd_raw.get("priority"),
            phase=prd_raw.get("phase"),
            implementation_notes=prd_raw.get("implementationNotes") or prd_raw.get("implementation_notes"),
            last_updated=prd_raw.get("lastUpdated") or prd_raw.get("last_updated"),
        )
        prds.append(prd)
        
        # Find current (in_progress) and next (not_started with highest priority)
        if prd.status == PRDStatus.IN_PROGRESS and not current_prd:
            current_prd = prd
        elif prd.status == PRDStatus.NOT_STARTED and not next_prd:
            next_prd = prd
    
    # Build response
    lines = [f"# PRD Status: {project.name}\n"]
    lines.append(f"**Total PRDs**: {len(prds)}")
    
    if current_prd:
        lines.append(f"\n## 🔄 Currently Working On")
        lines.append(f"**{current_prd.id}**: {current_prd.name}")
        lines.append(f"- Status: {current_prd.status.value}")
        if current_prd.priority:
            lines.append(f"- Priority: {current_prd.priority}")
        if current_prd.implementation_notes:
            lines.append(f"- Notes: {current_prd.implementation_notes}")
    else:
        lines.append("\n## 🔄 Currently Working On")
        lines.append("No PRD currently in progress.")
    
    if next_prd:
        lines.append(f"\n## ⏭️ Next Up")
        lines.append(f"**{next_prd.id}**: {next_prd.name}")
        if next_prd.priority:
            lines.append(f"- Priority: {next_prd.priority}")
    
    # Summary by status
    by_status = {}
    for prd in prds:
        by_status[prd.status.value] = by_status.get(prd.status.value, 0) + 1
    
    lines.append("\n## 📊 Summary")
    for status, count in by_status.items():
        lines.append(f"- {status}: {count}")
    
    return "\n".join(lines)


@tool
def scan_and_add_project(project_path: str, project_name: Optional[str] = None, project_type: str = "client") -> str:
    """
    Scan a project folder and add it to the registry.
    
    Args:
        project_path: Full path to the project folder
        project_name: Optional name for the project (auto-detected if not provided)
        project_type: Type of project (startup/personal/client)
    
    Scans for:
    - .prd-status.json
    - MASTER_PRD.md
    - CLAUDE.md or agent.md
    """
    path = Path(project_path)
    
    if not path.exists():
        return f"Path does not exist: {project_path}"
    
    if not path.is_dir():
        return f"Path is not a directory: {project_path}"
    
    # Auto-detect project name
    if not project_name:
        project_name = path.name
    
    # Scan for key files
    prd_status_path = None
    claude_md_path = None
    
    # Check common locations for .prd-status.json
    prd_locations = [
        "docs/prds/.prd-status.json",
        ".prd-status.json",
        "frontend/docs/prds/.prd-status.json",
    ]
    
    for loc in prd_locations:
        if (path / loc).exists():
            prd_status_path = loc
            break
    
    # Check for CLAUDE.md or agent.md
    claude_locations = [
        "CLAUDE.md",
        "agent.md",
        "frontend/CLAUDE.md",
    ]
    
    for loc in claude_locations:
        if (path / loc).exists():
            claude_md_path = loc
            break
    
    # Load registry and add project
    registry = load_project_registry()
    
    # Check if already exists
    for p in registry.projects:
        if p.path == str(path):
            return f"Project already registered: {p.name}"
    
    # Determine priority (add at end)
    max_priority = max((p.priority for p in registry.projects), default=0)
    
    # Create project
    project = Project(
        id=project_name.lower().replace(" ", "-").replace("_", "-"),
        name=project_name,
        path=str(path),
        type=project_type,
        priority=max_priority + 1,
        daily=False,
        prd_status_path=prd_status_path,
        claude_md_path=claude_md_path,
        description=f"Added on {datetime.now().strftime('%Y-%m-%d')}",
    )
    
    registry.projects.append(project)
    save_project_registry(registry)
    
    # Build response
    lines = [f"✅ Added project: **{project_name}**\n"]
    lines.append(f"- **Path**: `{path}`")
    lines.append(f"- **Type**: {project_type}")
    lines.append(f"- **Priority**: {project.priority}")
    
    if prd_status_path:
        lines.append(f"- **PRD Status**: Found at `{prd_status_path}`")
    else:
        lines.append("- **PRD Status**: Not found")
    
    if claude_md_path:
        lines.append(f"- **CLAUDE.md**: Found at `{claude_md_path}`")
    else:
        lines.append("- **CLAUDE.md**: Not found")
    
    return "\n".join(lines)


