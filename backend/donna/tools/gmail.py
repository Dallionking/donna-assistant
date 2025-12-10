"""
Gmail integration tools for Donna.

Handles reading emails, drafting responses, and email search.
"""

from typing import Optional, List
from datetime import datetime

from langchain_core.tools import tool

from donna.config import get_settings


def get_gmail_service():
    """
    Get Gmail API service.
    
    Note: Requires OAuth setup similar to Calendar.
    """
    settings = get_settings()
    
    # Check if credentials exist
    if not settings.google_credentials_path.exists():
        return None
    
    # TODO: Implement OAuth flow for Gmail
    return None


@tool
def get_recent_emails(limit: int = 10, unread_only: bool = False) -> str:
    """
    Get recent emails from Gmail.
    
    Args:
        limit: Maximum number of emails to return
        unread_only: If True, only return unread emails
    
    Returns list of emails with sender, subject, and snippet.
    """
    service = get_gmail_service()
    
    if service is None:
        return """⚠️ Gmail not configured.

To set up Gmail:
1. Enable Gmail API in Google Cloud Console
2. Use the same OAuth credentials as Calendar
3. Add 'gmail.readonly' scope

This will allow me to:
- Read your recent emails
- Search for specific emails
- Draft responses
"""
    
    try:
        # Build query
        query = "is:unread" if unread_only else ""
        
        results = service.users().messages().list(
            userId='me',
            q=query,
            maxResults=limit
        ).execute()
        
        messages = results.get('messages', [])
        
        if not messages:
            return "No emails found."
        
        lines = ["# Recent Emails\n"]
        
        for msg in messages:
            # Get full message
            full_msg = service.users().messages().get(
                userId='me',
                id=msg['id']
            ).execute()
            
            # Extract headers
            headers = {h['name']: h['value'] for h in full_msg['payload']['headers']}
            
            sender = headers.get('From', 'Unknown')
            subject = headers.get('Subject', 'No Subject')
            date = headers.get('Date', '')
            snippet = full_msg.get('snippet', '')[:100]
            
            # Unread indicator
            unread = "📬" if 'UNREAD' in full_msg.get('labelIds', []) else "📭"
            
            lines.append(f"## {unread} {subject}")
            lines.append(f"**From**: {sender}")
            lines.append(f"**Date**: {date}")
            lines.append(f"**Preview**: {snippet}...")
            lines.append("")
        
        return "\n".join(lines)
        
    except Exception as e:
        return f"Error fetching emails: {str(e)}"


@tool
def search_emails(query: str, limit: int = 10) -> str:
    """
    Search emails in Gmail.
    
    Args:
        query: Search query (uses Gmail search syntax)
        limit: Maximum number of results
    
    Examples:
    - "from:john@example.com"
    - "subject:invoice"
    - "after:2024/01/01"
    - "has:attachment"
    """
    service = get_gmail_service()
    
    if service is None:
        return "⚠️ Gmail not configured. See get_recent_emails for setup instructions."
    
    try:
        results = service.users().messages().list(
            userId='me',
            q=query,
            maxResults=limit
        ).execute()
        
        messages = results.get('messages', [])
        
        if not messages:
            return f"No emails matching '{query}'"
        
        lines = [f"# Emails matching: {query}\n"]
        lines.append(f"Found {len(messages)} result(s)\n")
        
        for msg in messages[:limit]:
            full_msg = service.users().messages().get(
                userId='me',
                id=msg['id']
            ).execute()
            
            headers = {h['name']: h['value'] for h in full_msg['payload']['headers']}
            
            subject = headers.get('Subject', 'No Subject')
            sender = headers.get('From', 'Unknown')
            
            lines.append(f"- **{subject}** from {sender}")
        
        return "\n".join(lines)
        
    except Exception as e:
        return f"Error searching emails: {str(e)}"


@tool
def draft_email(to: str, subject: str, body: str) -> str:
    """
    Create an email draft.
    
    Args:
        to: Recipient email address
        subject: Email subject
        body: Email body content
    
    Creates a draft in Gmail that you can review and send.
    """
    service = get_gmail_service()
    
    if service is None:
        return f"""⚠️ Gmail not configured.

Would draft email:
**To**: {to}
**Subject**: {subject}

{body}

---
Configure Gmail OAuth to enable drafting.
"""
    
    try:
        import base64
        from email.mime.text import MIMEText
        
        message = MIMEText(body)
        message['to'] = to
        message['subject'] = subject
        
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        
        draft = service.users().drafts().create(
            userId='me',
            body={'message': {'raw': raw}}
        ).execute()
        
        return f"""✅ Draft created!

**To**: {to}
**Subject**: {subject}

The draft is saved in Gmail. Open Gmail to review and send.
"""
        
    except Exception as e:
        return f"Error creating draft: {str(e)}"


