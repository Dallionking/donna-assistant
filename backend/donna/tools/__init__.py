"""
Donna Tools

Collection of tools that Donna can use to interact with
various services and perform actions.
"""

from donna.tools.projects import (
    get_all_projects,
    get_project_prd_status,
    scan_and_add_project,
)
from donna.tools.brain_dump import (
    create_brain_dump,
    search_brain_dumps,
    extract_action_items,
)
from donna.tools.calendar import (
    get_today_events,
    create_time_block,
    sync_schedule_to_calendar,
)
from donna.tools.schedule import (
    generate_daily_schedule,
    get_schedule_for_date,
    update_schedule,
)
from donna.tools.clients import (
    add_client,
    search_clients,
    get_client_details,
    list_all_clients,
)
from donna.tools.deals import (
    create_deal,
    close_deal,
    get_active_deals,
    log_payment,
    get_revenue_summary,
    get_deals_pending_payment,
)

__all__ = [
    # Projects
    "get_all_projects",
    "get_project_prd_status", 
    "scan_and_add_project",
    # Brain Dumps
    "create_brain_dump",
    "search_brain_dumps",
    "extract_action_items",
    # Calendar
    "get_today_events",
    "create_time_block",
    "sync_schedule_to_calendar",
    # Schedule
    "generate_daily_schedule",
    "get_schedule_for_date",
    "update_schedule",
    # Clients (CRM)
    "add_client",
    "search_clients",
    "get_client_details",
    "list_all_clients",
    # Deals & Revenue (CRM)
    "create_deal",
    "close_deal",
    "get_active_deals",
    "log_payment",
    "get_revenue_summary",
    "get_deals_pending_payment",
]


