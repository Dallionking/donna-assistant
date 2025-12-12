"""
Deal/Contract management tools for Donna CRM.

Handles:
- Creating and closing deals
- Tracking payment status
- Revenue summaries
"""

import logging
from datetime import datetime
from typing import Optional, List, Dict, Any

from langchain_core.tools import tool

from donna.database import (
    get_supabase_client,
    save_deal,
    update_deal,
    get_deal_by_id,
    get_deals_by_status,
    get_active_deals as db_get_active_deals,
    get_deals_by_client,
    save_payment,
    get_payments_for_deal,
    get_total_payments_for_deal,
    get_revenue_summary as db_get_revenue_summary,
    search_clients,
)

logger = logging.getLogger(__name__)


@tool
def create_deal(
    client_name: str,
    title: str,
    deal_type: str,
    amount: float,
    status: str = "prospect",
    notes: Optional[str] = None
) -> str:
    """
    Create a new deal/contract with a client.
    
    Args:
        client_name: Name of the client (must exist in system)
        title: Short description of the deal (e.g., "Mobile App Build")
        deal_type: Type of work (app_build, consulting, mentorship)
        amount: Contract amount in dollars
        status: Deal status (prospect, negotiating, closed, in_progress)
        notes: Additional notes
    
    Returns:
        Confirmation with deal details
    """
    import asyncio
    
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    # Find the client
    clients = loop.run_until_complete(search_clients(client_name))
    
    if not clients:
        return f"No client found matching '{client_name}'. Add them first with add_client."
    
    client = clients[0]
    client_id = client.get('id')
    
    deal_data = {
        "client_id": client_id,
        "title": title,
        "type": deal_type,
        "amount": amount,
        "status": status,
        "payment_status": "pending",
        "notes": notes,
        "created_at": datetime.now().isoformat(),
    }
    
    if status == "closed":
        deal_data["closed_at"] = datetime.now().isoformat()
    
    deal_id = loop.run_until_complete(save_deal(deal_data))
    
    if deal_id:
        status_emoji = '🟢' if status == 'closed' else '🔵'
        return f"""{status_emoji} **Deal Created**

- **Client**: {client.get('name')}
- **Title**: {title}
- **Type**: {deal_type}
- **Amount**: ${amount:,.2f}
- **Status**: {status}
- **ID**: `{deal_id}`

I'm tracking this. Let me know when you get paid."""
    else:
        return "Failed to create deal. Database may be unavailable."


@tool
def close_deal(
    client_name: str,
    title: str,
    deal_type: str,
    amount: float,
    notes: Optional[str] = None
) -> str:
    """
    Close a new deal - shortcut for creating a deal with status 'closed'.
    
    Use this when you've just signed a contract with a client.
    
    Args:
        client_name: Name of the client
        title: What you're building/consulting on
        deal_type: Type of work (app_build, consulting, mentorship)
        amount: Contract amount in dollars
        notes: Additional context
    
    Returns:
        Confirmation of closed deal
    """
    import asyncio
    
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    # Find the client first, or create if doesn't exist
    clients = loop.run_until_complete(search_clients(client_name))
    
    if not clients:
        # Auto-create the client
        from donna.database import save_client
        client_data = {
            "name": client_name,
            "source": "deal",
            "created_at": datetime.now().isoformat(),
        }
        client_id = loop.run_until_complete(save_client(client_data))
        if not client_id:
            return "Failed to create client. Database may be unavailable."
    else:
        client_id = clients[0].get('id')
        client_name = clients[0].get('name')  # Use exact name
    
    deal_data = {
        "client_id": client_id,
        "title": title,
        "type": deal_type,
        "amount": amount,
        "status": "closed",
        "payment_status": "pending",
        "notes": notes,
        "created_at": datetime.now().isoformat(),
        "closed_at": datetime.now().isoformat(),
    }
    
    deal_id = loop.run_until_complete(save_deal(deal_data))
    
    if deal_id:
        return f"""🎉 **Deal Closed!**

- **Client**: {client_name}
- **Project**: {title}
- **Type**: {deal_type}
- **Value**: ${amount:,.2f}

Congratulations! I'm tracking payment status. Use `log_payment` when you receive funds."""
    else:
        return "Failed to close deal. Database may be unavailable."


@tool
def get_active_deals() -> str:
    """
    Get all active deals (closed or in progress).
    
    Returns:
        List of all active deals with client info
    """
    import asyncio
    
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    deals = loop.run_until_complete(db_get_active_deals())
    
    if not deals:
        return "No active deals. Time to close some!"
    
    lines = ["# Active Deals\n"]
    
    total_value = 0
    by_status = {}
    
    for d in deals:
        status = d.get('status', 'unknown')
        if status not in by_status:
            by_status[status] = []
        by_status[status].append(d)
        total_value += float(d.get('amount', 0) or 0)
    
    for status, status_deals in by_status.items():
        status_emoji = {
            'closed': '🟢',
            'in_progress': '🔄',
        }.get(status, '⚪')
        
        lines.append(f"## {status_emoji} {status.replace('_', ' ').title()}\n")
        
        for d in status_deals:
            client_info = d.get('clients', {})
            client_name = client_info.get('name', 'Unknown') if client_info else 'Unknown'
            amount = float(d.get('amount', 0) or 0)
            payment = d.get('payment_status', 'pending')
            
            payment_emoji = '💰' if payment == 'paid' else '⏳' if payment == 'partial' else '📋'
            
            lines.append(f"### {d.get('title')}")
            lines.append(f"- **Client**: {client_name}")
            lines.append(f"- **Amount**: ${amount:,.2f} {payment_emoji}")
            lines.append(f"- **Type**: {d.get('type', 'unknown')}")
            lines.append("")
    
    lines.append(f"---\n**Total Active Value**: ${total_value:,.2f}")
    
    return "\n".join(lines)


@tool
def log_payment(
    client_name: str,
    amount: float,
    method: str = "stripe",
    notes: Optional[str] = None
) -> str:
    """
    Log a payment received from a client.
    
    Args:
        client_name: Name of the client who paid
        amount: Amount received
        method: Payment method (stripe, paypal, wire, cash)
        notes: Additional notes
    
    Returns:
        Confirmation of payment logged
    """
    import asyncio
    
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    # Find client's active deal
    clients = loop.run_until_complete(search_clients(client_name))
    
    if not clients:
        return f"No client found matching '{client_name}'."
    
    client_id = clients[0].get('id')
    client_name = clients[0].get('name')
    
    # Get their deals
    from donna.database import get_deals_by_client
    deals = loop.run_until_complete(get_deals_by_client(client_id))
    
    # Find active deal
    active_deal = None
    for d in deals:
        if d.get('status') in ['closed', 'in_progress'] and d.get('payment_status') != 'paid':
            active_deal = d
            break
    
    if not active_deal:
        return f"No unpaid active deal found for {client_name}."
    
    deal_id = active_deal.get('id')
    deal_amount = float(active_deal.get('amount', 0) or 0)
    
    # Record payment
    payment_data = {
        "deal_id": deal_id,
        "amount": amount,
        "method": method,
        "notes": notes,
        "date": datetime.now().isoformat(),
    }
    
    payment_id = loop.run_until_complete(save_payment(payment_data))
    
    if payment_id:
        # Check if deal is fully paid
        total_paid = loop.run_until_complete(get_total_payments_for_deal(deal_id))
        
        new_status = "paid" if total_paid >= deal_amount else "partial"
        loop.run_until_complete(update_deal(deal_id, {"payment_status": new_status}))
        
        remaining = max(0, deal_amount - total_paid)
        
        if new_status == "paid":
            return f"""💰 **Payment Received - PAID IN FULL**

- **Client**: {client_name}
- **Amount**: ${amount:,.2f}
- **Method**: {method}
- **Deal**: {active_deal.get('title')}

Total received: ${total_paid:,.2f} of ${deal_amount:,.2f}

Nice work. This one's done."""
        else:
            return f"""💰 **Payment Received**

- **Client**: {client_name}
- **Amount**: ${amount:,.2f}
- **Method**: {method}
- **Deal**: {active_deal.get('title')}

Progress: ${total_paid:,.2f} of ${deal_amount:,.2f}
**Remaining**: ${remaining:,.2f}"""
    else:
        return "Failed to log payment. Database may be unavailable."


@tool
def get_revenue_summary() -> str:
    """
    Get a summary of revenue across all deals.
    
    Returns:
        Revenue breakdown: total, paid, pending
    """
    import asyncio
    
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    summary = loop.run_until_complete(db_get_revenue_summary())
    
    total = summary.get('total_deal_value', 0)
    paid = summary.get('total_paid', 0)
    pending = summary.get('pending', 0)
    deal_count = summary.get('deal_count', 0)
    
    collection_rate = (paid / total * 100) if total > 0 else 0
    
    return f"""# 💰 Revenue Summary

## Overview
- **Total Deal Value**: ${total:,.2f}
- **Active Deals**: {deal_count}

## Collection Status
- ✅ **Collected**: ${paid:,.2f}
- ⏳ **Pending**: ${pending:,.2f}
- 📊 **Collection Rate**: {collection_rate:.1f}%

---
*Run `get_active_deals` for details on each deal.*"""


@tool 
def get_deals_pending_payment() -> str:
    """
    Get all deals that still have pending payments.
    
    Returns:
        List of deals waiting for payment
    """
    import asyncio
    
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    deals = loop.run_until_complete(db_get_active_deals())
    
    pending = [d for d in deals if d.get('payment_status') in ['pending', 'partial']]
    
    if not pending:
        return "🎉 All deals are paid! No outstanding payments."
    
    lines = ["# ⏳ Deals Pending Payment\n"]
    
    total_pending = 0
    
    for d in pending:
        client_info = d.get('clients', {})
        client_name = client_info.get('name', 'Unknown') if client_info else 'Unknown'
        amount = float(d.get('amount', 0) or 0)
        
        # Get payments for this deal
        deal_id = d.get('id')
        paid = loop.run_until_complete(get_total_payments_for_deal(deal_id))
        remaining = amount - paid
        total_pending += remaining
        
        status = "⏳ Pending" if d.get('payment_status') == 'pending' else "📊 Partial"
        
        lines.append(f"## {d.get('title')}")
        lines.append(f"- **Client**: {client_name}")
        lines.append(f"- **Total**: ${amount:,.2f}")
        lines.append(f"- **Paid**: ${paid:,.2f}")
        lines.append(f"- **Remaining**: ${remaining:,.2f}")
        lines.append(f"- **Status**: {status}")
        lines.append("")
    
    lines.append(f"---\n**Total Outstanding**: ${total_pending:,.2f}")
    
    return "\n".join(lines)
