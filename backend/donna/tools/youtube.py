"""
YouTube Studio integration tools for Donna.

Handles analytics, video management, and content planning.
"""

from typing import Optional, List
from datetime import datetime, timedelta

from langchain_core.tools import tool

from donna.config import get_settings


def get_youtube_service():
    """
    Get YouTube Data API service.
    
    Note: Uses same Google OAuth as Calendar.
    """
    settings = get_settings()
    
    if not settings.google_credentials_path.exists():
        return None
    
    # TODO: Implement OAuth flow for YouTube
    return None


@tool
def get_youtube_channel_stats() -> str:
    """
    Get YouTube channel statistics.
    
    Returns:
    - Subscriber count
    - Total views
    - Video count
    - Recent performance
    """
    service = get_youtube_service()
    
    if service is None:
        return """⚠️ YouTube not configured.

To set up YouTube Studio integration:
1. Enable YouTube Data API v3 in Google Cloud Console
2. Use the same OAuth credentials as Calendar
3. Add 'youtube.readonly' scope

This will allow me to:
- View channel analytics
- Track video performance
- Help plan content strategy
"""
    
    try:
        # Get channel info
        request = service.channels().list(
            part="statistics,snippet",
            mine=True
        )
        response = request.execute()
        
        if not response.get("items"):
            return "No YouTube channel found for this account."
        
        channel = response["items"][0]
        stats = channel["statistics"]
        snippet = channel["snippet"]
        
        lines = [
            f"# YouTube Channel: {snippet['title']}\n",
            f"**Subscribers**: {int(stats.get('subscriberCount', 0)):,}",
            f"**Total Views**: {int(stats.get('viewCount', 0)):,}",
            f"**Videos**: {stats.get('videoCount', 0)}",
            "",
        ]
        
        return "\n".join(lines)
        
    except Exception as e:
        return f"Error fetching YouTube stats: {str(e)}"


@tool
def get_recent_videos(limit: int = 5) -> str:
    """
    Get recent video performance.
    
    Args:
        limit: Number of recent videos to show
    
    Returns video titles with view counts.
    """
    service = get_youtube_service()
    
    if service is None:
        return "⚠️ YouTube not configured. See get_youtube_channel_stats for setup."
    
    try:
        # Get uploads playlist
        channels_response = service.channels().list(
            part="contentDetails",
            mine=True
        ).execute()
        
        if not channels_response.get("items"):
            return "No channel found."
        
        uploads_id = channels_response["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
        
        # Get recent videos
        videos_response = service.playlistItems().list(
            part="snippet",
            playlistId=uploads_id,
            maxResults=limit
        ).execute()
        
        videos = videos_response.get("items", [])
        
        if not videos:
            return "No videos found."
        
        lines = ["# Recent Videos\n"]
        
        for video in videos:
            snippet = video["snippet"]
            title = snippet["title"]
            published = snippet.get("publishedAt", "")[:10]
            video_id = snippet["resourceId"]["videoId"]
            
            # Get video stats
            stats_response = service.videos().list(
                part="statistics",
                id=video_id
            ).execute()
            
            if stats_response.get("items"):
                stats = stats_response["items"][0]["statistics"]
                views = int(stats.get("viewCount", 0))
                likes = int(stats.get("likeCount", 0))
                
                lines.append(f"## {title}")
                lines.append(f"- Published: {published}")
                lines.append(f"- Views: {views:,}")
                lines.append(f"- Likes: {likes:,}")
                lines.append("")
        
        return "\n".join(lines)
        
    except Exception as e:
        return f"Error fetching videos: {str(e)}"


@tool
def add_content_idea(platform: str, idea: str, notes: Optional[str] = None) -> str:
    """
    Add a content idea for YouTube, TikTok, or Instagram.
    
    Args:
        platform: "youtube", "tiktok", or "instagram"
        idea: The content idea
        notes: Additional notes
    
    Saves the idea to the content planning files.
    """
    from pathlib import Path
    from donna.config import get_settings
    
    settings = get_settings()
    
    platform = platform.lower()
    if platform not in ["youtube", "tiktok", "instagram"]:
        return f"Unknown platform: {platform}. Use youtube, tiktok, or instagram."
    
    content_path = settings.donna_workspace / "content" / platform / "ideas.md"
    
    if not content_path.exists():
        content_path.parent.mkdir(parents=True, exist_ok=True)
        content_path.write_text(f"# {platform.title()} Content Ideas\n\n## Pending Ideas\n\n")
    
    # Read existing content
    content = content_path.read_text()
    
    # Find the Pending Ideas section and add the new idea
    timestamp = datetime.now().strftime("%Y-%m-%d")
    
    new_entry = f"\n### [{timestamp}] {idea}\n"
    if notes:
        new_entry += f"{notes}\n"
    
    # Insert after "## Pending Ideas"
    if "## Pending Ideas" in content:
        parts = content.split("## Pending Ideas")
        content = parts[0] + "## Pending Ideas" + new_entry + parts[1]
    else:
        content += f"\n## Pending Ideas\n{new_entry}"
    
    content_path.write_text(content)
    
    return f"""✅ Content idea saved!

**Platform**: {platform.title()}
**Idea**: {idea}
**File**: `{content_path}`

Use `/braindump` to expand on this idea or create a full content plan.
"""


