#!/usr/bin/env python3
"""
Setup Calendly webhook subscription for Donna.

Run this once to register the webhook endpoint with Calendly.

Usage:
    python setup_calendly_webhook.py
"""

import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
from donna.config import get_settings

CALENDLY_API_BASE = "https://api.calendly.com"


def get_current_user(api_key: str) -> dict:
    """Get the current Calendly user."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    
    response = httpx.get(f"{CALENDLY_API_BASE}/users/me", headers=headers)
    response.raise_for_status()
    return response.json()["resource"]


def get_organization(user: dict) -> str:
    """Get the organization URI from user."""
    return user.get("current_organization")


def list_webhooks(api_key: str, organization: str) -> list:
    """List existing webhook subscriptions."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    
    response = httpx.get(
        f"{CALENDLY_API_BASE}/webhook_subscriptions",
        headers=headers,
        params={"organization": organization, "scope": "organization"}
    )
    response.raise_for_status()
    return response.json().get("collection", [])


def create_webhook(api_key: str, organization: str, callback_url: str) -> dict:
    """Create a new webhook subscription."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    
    payload = {
        "url": callback_url,
        "events": [
            "invitee.created",
            "invitee.canceled",
        ],
        "organization": organization,
        "scope": "organization",
    }
    
    response = httpx.post(
        f"{CALENDLY_API_BASE}/webhook_subscriptions",
        headers=headers,
        json=payload
    )
    response.raise_for_status()
    return response.json()["resource"]


def delete_webhook(api_key: str, webhook_uri: str) -> None:
    """Delete a webhook subscription."""
    headers = {
        "Authorization": f"Bearer {api_key}",
    }
    
    # Extract UUID from URI
    webhook_id = webhook_uri.split("/")[-1]
    
    response = httpx.delete(
        f"{CALENDLY_API_BASE}/webhook_subscriptions/{webhook_id}",
        headers=headers
    )
    response.raise_for_status()


def main():
    print("""
╔══════════════════════════════════════════════════════════════╗
║  Calendly Webhook Setup for Donna                             ║
╚══════════════════════════════════════════════════════════════╝
""")
    
    # Get settings
    settings = get_settings()
    
    if not settings.calendly_api_key:
        print("❌ CALENDLY_API_KEY not found in .env")
        print("   Add your Calendly Personal Access Token to .env")
        return
    
    api_key = settings.calendly_api_key
    
    # Webhook URL - your Render deployment
    webhook_url = "https://donna-assistant.onrender.com/webhooks/calendly"
    
    print(f"📌 Webhook URL: {webhook_url}")
    print()
    
    try:
        # Get current user
        print("🔍 Getting Calendly user info...")
        user = get_current_user(api_key)
        print(f"   User: {user.get('name')} ({user.get('email')})")
        
        organization = get_organization(user)
        print(f"   Organization: {organization}")
        print()
        
        # List existing webhooks
        print("📋 Checking existing webhooks...")
        existing = list_webhooks(api_key, organization)
        
        if existing:
            print(f"   Found {len(existing)} existing webhook(s):")
            for wh in existing:
                print(f"   - {wh.get('callback_url')}")
                
                # Check if our webhook already exists
                if webhook_url in wh.get("callback_url", ""):
                    print(f"\n✅ Donna webhook already registered!")
                    print(f"   Events: {wh.get('events')}")
                    print(f"   State: {wh.get('state')}")
                    return
        else:
            print("   No existing webhooks found.")
        
        print()
        
        # Create new webhook
        print("🔗 Creating Donna webhook subscription...")
        webhook = create_webhook(api_key, organization, webhook_url)
        
        print()
        print("✅ Webhook created successfully!")
        print(f"   URL: {webhook.get('callback_url')}")
        print(f"   Events: {webhook.get('events')}")
        print(f"   State: {webhook.get('state')}")
        print()
        print("   Donna will now receive real-time notifications when:")
        print("   - Someone books a call (invitee.created)")
        print("   - Someone cancels a call (invitee.canceled)")
        print()
        
        # Note about webhook secret
        if webhook.get("signing_key"):
            print("🔐 Webhook Signing Key (add to .env as CALENDLY_WEBHOOK_SECRET):")
            print(f"   {webhook.get('signing_key')}")
        
    except httpx.HTTPStatusError as e:
        print(f"❌ API Error: {e.response.status_code}")
        print(f"   {e.response.text}")
    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    main()

