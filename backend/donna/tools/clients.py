"""
Client management tools for Donna CRM.

Handles:
- Adding new clients
- Searching clients
- Getting client details with deals
"""

import logging
from datetime import datetime
from typing import Optional, List, Dict, Any

from langchain_core.tools import tool

from donna.database import (
    get_supabase_client,
    save_client,
    search_clients as db_search_clients,
    get_client_by_id,
    get_all_clients,
    get_deals_by_client,
)

logger = logging.getLogger(__name__)


@tool
def add_client(
    name: str,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    company: Optional[str] = None,
    source: str = "manual",
    notes: Optional[str] = None
) -> str:
    """
    Add a new client to the CRM.
    
    Args:
        name: Client's full name (required)
        email: Client's email address
        phone: Client's phone number
        company: Client's company name
        source: How they found you (calendly, referral, instagram, etc.)
        notes: Additional notes about the client
    
    Returns:
        Confirmation message with client ID
    """
    import asyncio
    
    client_data = {
        "name": name,
        "email": email,
        "phone": phone,
        "company": company,
        "source": source,
        "notes": notes,
        "first_contact": datetime.now().isoformat(),
        "created_at": datetime.now().isoformat(),
    }
    
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    client_id = loop.run_until_complete(save_client(client_data))
    
    if client_id:
        return f"""✅ **Client Added**

- **Name**: {name}
- **Email**: {email or 'Not provided'}
- **Company**: {company or 'Not provided'}
- **Source**: {source}
- **ID**: `{client_id}`

I've got them in the system. Ready to track deals for this client."""
    else:
        return f"Failed to add client. Database may be unavailable."


@tool
def search_clients(query: str) -> str:
    """
    Search for clients by name, email, or company.
    
    Args:
        query: Search term to find clients
    
    Returns:
        List of matching clients
    """
    import asyncio
    
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    clients = loop.run_until_complete(db_search_clients(query))
    
    if not clients:
        return f"No clients found matching '{query}'."
    
    lines = [f"# Clients matching '{query}'\n"]
    
    for c in clients:
        company_info = f" ({c.get('company')})" if c.get('company') else ""
        lines.append(f"## {c.get('name')}{company_info}")
        if c.get('email'):
            lines.append(f"- **Email**: {c.get('email')}")
        if c.get('phone'):
            lines.append(f"- **Phone**: {c.get('phone')}")
        lines.append(f"- **Source**: {c.get('source', 'unknown')}")
        lines.append(f"- **ID**: `{c.get('id')}`")
        lines.append("")
    
    return "\n".join(lines)


@tool
def get_client_details(client_name: str) -> str:
    """
    Get full details for a client including their deals.
    
    Args:
        client_name: Name of the client to look up
    
    Returns:
        Full client profile with all deals
    """
    import asyncio
    
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    # Search for the client
    clients = loop.run_until_complete(db_search_clients(client_name))
    
    if not clients:
        return f"No client found matching '{client_name}'."
    
    # Get the first match
    client = clients[0]
    client_id = client.get('id')
    
    # Get their deals
    deals = loop.run_until_complete(get_deals_by_client(client_id))
    
    lines = [f"# Client: {client.get('name')}\n"]
    
    if client.get('company'):
        lines.append(f"**Company**: {client.get('company')}")
    if client.get('email'):
        lines.append(f"**Email**: {client.get('email')}")
    if client.get('phone'):
        lines.append(f"**Phone**: {client.get('phone')}")
    lines.append(f"**Source**: {client.get('source', 'unknown')}")
    lines.append(f"**First Contact**: {client.get('first_contact', 'unknown')[:10] if client.get('first_contact') else 'unknown'}")
    
    if client.get('notes'):
        lines.append(f"\n**Notes**: {client.get('notes')}")
    
    lines.append("\n---\n")
    lines.append("## Deals\n")
    
    if not deals:
        lines.append("No deals with this client yet.")
    else:
        total_value = 0
        for d in deals:
            status_emoji = {
                'prospect': '🔵',
                'negotiating': '🟡',
                'closed': '🟢',
                'in_progress': '🔄',
                'completed': '✅',
                'cancelled': '❌'
            }.get(d.get('status', ''), '⚪')
            
            amount = float(d.get('amount', 0) or 0)
            if d.get('status') in ['closed', 'in_progress', 'completed']:
                total_value += amount
            
            lines.append(f"### {status_emoji} {d.get('title')}")
            lines.append(f"- **Type**: {d.get('type', 'unknown')}")
            lines.append(f"- **Amount**: ${amount:,.2f}")
            lines.append(f"- **Status**: {d.get('status')}")
            lines.append(f"- **Payment**: {d.get('payment_status', 'pending')}")
            lines.append("")
        
        lines.append(f"**Total Deal Value**: ${total_value:,.2f}")
    
    return "\n".join(lines)


@tool
def list_all_clients() -> str:
    """
    List all clients in the CRM.
    
    Returns:
        Summary of all clients
    """
    import asyncio
    
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    clients = loop.run_until_complete(get_all_clients())
    
    if not clients:
        return "No clients in the system yet. Add your first client!"
    
    lines = ["# All Clients\n"]
    
    by_source = {}
    for c in clients:
        source = c.get('source', 'unknown')
        if source not in by_source:
            by_source[source] = []
        by_source[source].append(c)
    
    for source, source_clients in by_source.items():
        lines.append(f"## From {source.title()} ({len(source_clients)})")
        for c in source_clients:
            company = f" - {c.get('company')}" if c.get('company') else ""
            lines.append(f"- **{c.get('name')}**{company}")
        lines.append("")
    
    lines.append(f"---\n**Total Clients**: {len(clients)}")
    
    return "\n".join(lines)
