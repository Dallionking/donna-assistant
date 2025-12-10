"""
Google OAuth2 authentication for Donna.

Handles authentication for:
- Google Calendar
- Gmail
- YouTube Data API

Usage:
1. Create OAuth credentials at console.cloud.google.com
2. Download credentials.json to backend/credentials/
3. Run: python -m donna.google_auth
4. Complete the OAuth flow in browser
5. Token is saved to backend/credentials/google_token.json
"""

import json
import logging
from pathlib import Path
from typing import Optional, List

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build, Resource

from donna.config import get_settings

logger = logging.getLogger(__name__)

# Scopes for all Google services Donna needs
SCOPES = [
    # Calendar
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/calendar.events',
    
    # Gmail
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.compose',
    'https://www.googleapis.com/auth/gmail.send',
    
    # YouTube
    'https://www.googleapis.com/auth/youtube.readonly',
    'https://www.googleapis.com/auth/yt-analytics.readonly',
]


def get_credentials_path() -> Path:
    """Get path to credentials.json file."""
    settings = get_settings()
    return Path(settings.google_credentials_path)


def get_token_path() -> Path:
    """Get path to token.json file."""
    settings = get_settings()
    return Path(settings.google_token_path)


def load_credentials() -> Optional[Credentials]:
    """
    Load Google credentials from token file.
    
    Returns None if:
    - Token file doesn't exist
    - Token is expired and can't be refreshed
    """
    token_path = get_token_path()
    
    if not token_path.exists():
        logger.warning(f"Token file not found at {token_path}")
        return None
    
    try:
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
        
        # Check if token is valid
        if creds.valid:
            return creds
        
        # Try to refresh if expired
        if creds.expired and creds.refresh_token:
            logger.info("Refreshing expired Google token...")
            creds.refresh(Request())
            
            # Save refreshed token
            with open(token_path, 'w') as f:
                f.write(creds.to_json())
            
            logger.info("Token refreshed successfully")
            return creds
        
        logger.warning("Token expired and cannot be refreshed")
        return None
        
    except Exception as e:
        logger.error(f"Error loading credentials: {e}")
        return None


def run_oauth_flow() -> Optional[Credentials]:
    """
    Run the OAuth flow to get new credentials.
    
    This opens a browser window for the user to authenticate.
    Should only be run locally (not on server).
    """
    credentials_path = get_credentials_path()
    token_path = get_token_path()
    
    if not credentials_path.exists():
        logger.error(f"credentials.json not found at {credentials_path}")
        print(f"""
╔══════════════════════════════════════════════════════════════╗
║  Google OAuth Setup Required                                  ║
╠══════════════════════════════════════════════════════════════╣
║                                                               ║
║  1. Go to: https://console.cloud.google.com/                  ║
║  2. Create a new project or select existing                   ║
║  3. Enable APIs:                                              ║
║     - Google Calendar API                                     ║
║     - Gmail API                                               ║
║     - YouTube Data API v3                                     ║
║  4. Create OAuth 2.0 credentials (Desktop app)                ║
║  5. Download credentials.json                                 ║
║  6. Save to: {credentials_path}
║  7. Run this script again                                     ║
║                                                               ║
╚══════════════════════════════════════════════════════════════╝
""")
        return None
    
    try:
        # Ensure credentials directory exists
        token_path.parent.mkdir(parents=True, exist_ok=True)
        
        flow = InstalledAppFlow.from_client_secrets_file(
            str(credentials_path),
            SCOPES
        )
        
        print("\n🔐 Opening browser for Google authentication...")
        print("   If browser doesn't open, visit the URL shown below.\n")
        
        creds = flow.run_local_server(port=0)
        
        # Save the credentials
        with open(token_path, 'w') as f:
            f.write(creds.to_json())
        
        print(f"\n✅ Google authentication successful!")
        print(f"   Token saved to: {token_path}\n")
        
        return creds
        
    except Exception as e:
        logger.error(f"OAuth flow error: {e}")
        print(f"\n❌ OAuth flow failed: {e}\n")
        return None


def get_google_credentials() -> Optional[Credentials]:
    """
    Get Google credentials, running OAuth if needed.
    
    Returns credentials if available, None otherwise.
    """
    creds = load_credentials()
    
    if creds is None:
        logger.info("No valid credentials found. OAuth flow required.")
    
    return creds


def get_calendar_service() -> Optional[Resource]:
    """Get authenticated Google Calendar service."""
    creds = get_google_credentials()
    
    if creds is None:
        return None
    
    try:
        service = build('calendar', 'v3', credentials=creds)
        return service
    except Exception as e:
        logger.error(f"Error building Calendar service: {e}")
        return None


def get_gmail_service() -> Optional[Resource]:
    """Get authenticated Gmail service."""
    creds = get_google_credentials()
    
    if creds is None:
        return None
    
    try:
        service = build('gmail', 'v1', credentials=creds)
        return service
    except Exception as e:
        logger.error(f"Error building Gmail service: {e}")
        return None


def get_youtube_service() -> Optional[Resource]:
    """Get authenticated YouTube service."""
    creds = get_google_credentials()
    
    if creds is None:
        return None
    
    try:
        service = build('youtube', 'v3', credentials=creds)
        return service
    except Exception as e:
        logger.error(f"Error building YouTube service: {e}")
        return None


def check_google_auth_status() -> dict:
    """
    Check the status of Google authentication.
    
    Returns dict with status info.
    """
    credentials_path = get_credentials_path()
    token_path = get_token_path()
    
    status = {
        'credentials_file_exists': credentials_path.exists(),
        'token_file_exists': token_path.exists(),
        'is_authenticated': False,
        'scopes': [],
        'email': None,
    }
    
    if token_path.exists():
        creds = load_credentials()
        if creds:
            status['is_authenticated'] = True
            status['scopes'] = creds.scopes or []
            
            # Try to get user email
            try:
                service = build('gmail', 'v1', credentials=creds)
                profile = service.users().getProfile(userId='me').execute()
                status['email'] = profile.get('emailAddress')
            except Exception:
                pass
    
    return status


if __name__ == "__main__":
    """Run OAuth flow when executed directly."""
    print("""
╔══════════════════════════════════════════════════════════════╗
║  Donna Google OAuth Setup                                     ║
╚══════════════════════════════════════════════════════════════╝
""")
    
    # Check current status
    status = check_google_auth_status()
    
    if status['is_authenticated']:
        print(f"✅ Already authenticated as: {status['email']}")
        print(f"   Scopes: {len(status['scopes'])} granted")
        print("\n   Run with --force to re-authenticate\n")
    else:
        if not status['credentials_file_exists']:
            print("❌ credentials.json not found")
            run_oauth_flow()  # Will print setup instructions
        else:
            print("🔄 Running OAuth flow...")
            creds = run_oauth_flow()
            
            if creds:
                # Verify by checking status
                new_status = check_google_auth_status()
                if new_status['is_authenticated']:
                    print(f"   Authenticated as: {new_status['email']}")

