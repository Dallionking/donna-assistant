"""
Configuration settings for Donna.
"""

from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Donna configuration settings loaded from environment."""
    
    # Supabase
    supabase_url: str = Field(..., env="SUPABASE_URL")
    supabase_service_key: Optional[str] = Field(None, env="SUPABASE_SERVICE_KEY")
    supabase_anon_key: str = Field(..., env="SUPABASE_ANON_KEY")
    
    # LLM Providers
    openai_api_key: str = Field(..., env="OPENAI_API_KEY")
    anthropic_api_key: Optional[str] = Field(None, env="ANTHROPIC_API_KEY")
    
    # Google APIs
    google_credentials_path: Path = Field(
        Path("./credentials/google_credentials.json"),
        env="GOOGLE_CREDENTIALS_PATH"
    )
    google_token_path: Path = Field(
        Path("./credentials/google_token.json"),
        env="GOOGLE_TOKEN_PATH"
    )
    google_calendar_id: str = Field("primary", env="GOOGLE_CALENDAR_ID")
    
    # Telegram
    telegram_bot_token: str = Field(..., env="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: str = Field(..., env="TELEGRAM_CHAT_ID")
    
    # Calendly
    calendly_api_key: Optional[str] = Field(None, env="CALENDLY_API_KEY")
    calendly_webhook_secret: Optional[str] = Field(None, env="CALENDLY_WEBHOOK_SECRET")
    
    # GitHub
    github_token: Optional[str] = Field(None, env="GITHUB_TOKEN")
    github_username: Optional[str] = Field(None, env="GITHUB_USERNAME")
    
    # ElevenLabs (Voice)
    elevenlabs_api_key: Optional[str] = Field(None, env="ELEVENLABS_API_KEY")
    elevenlabs_voice_id: Optional[str] = Field(None, env="ELEVENLABS_VOICE_ID")
    
    # Donna Config
    donna_workspace: Path = Field(
        Path("/Users/dallionking/Donna"),
        env="DONNA_WORKSPACE"
    )
    donna_timezone: str = Field("America/New_York", env="DONNA_TIMEZONE")
    donna_morning_brief_time: str = Field("05:00", env="DONNA_MORNING_BRIEF_TIME")
    donna_calendly_sync_interval_hours: int = Field(3, env="DONNA_CALENDLY_SYNC_INTERVAL_HOURS")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"  # Ignore extra env variables


# Singleton settings instance
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get or create settings singleton."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


# Path constants
def get_brain_dumps_path() -> Path:
    """Get the brain dumps directory path."""
    return get_settings().donna_workspace / "brain-dumps"


def get_daily_path() -> Path:
    """Get the daily schedules directory path."""
    return get_settings().donna_workspace / "daily"


def get_handoffs_path() -> Path:
    """Get the handoffs directory path."""
    return get_settings().donna_workspace / "handoffs"


def get_projects_registry_path() -> Path:
    """Get the projects registry file path."""
    return get_settings().donna_workspace / "projects" / "registry.json"


def get_schedule_template_path() -> Path:
    """Get the weekly schedule template path."""
    return get_settings().donna_workspace / "schedule" / "weekly-template.json"

