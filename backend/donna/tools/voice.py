"""
Voice generation tools for Donna using ElevenLabs.

Handles text-to-speech for:
- Morning briefs
- On-demand voice responses
- Donna's signature sassy delivery
"""

import io
import logging
from pathlib import Path
from typing import Optional

import httpx

from donna.config import get_settings

logger = logging.getLogger(__name__)

# ElevenLabs API
ELEVENLABS_API_URL = "https://api.elevenlabs.io/v1"

# Available models (best to worst for natural speech)
ELEVENLABS_MODELS = {
    "turbo_v2_5": "eleven_turbo_v2_5",      # Fast, good quality, 32 languages
    "multilingual_v2": "eleven_multilingual_v2",  # High quality, 29 languages
    "turbo_v2": "eleven_turbo_v2",          # Fast, English optimized
    "monolingual_v1": "eleven_monolingual_v1",    # Legacy, English only
}

# Default model - turbo_v2_5 is best balance of speed and quality
DEFAULT_MODEL = ELEVENLABS_MODELS["turbo_v2_5"]

# Voice settings for Donna's personality
# Based on ElevenLabs best practices for natural conversational speech
DONNA_VOICE_SETTINGS = {
    "stability": 0.35,        # Lower = more expressive/natural (0.3-0.5 recommended)
    "similarity_boost": 0.80, # Higher = more consistent voice
    "style": 0.15,            # Lower = clearer pronunciation (0.0-0.3 for clarity)
    "use_speaker_boost": True,
}


def get_elevenlabs_headers() -> dict:
    """Get headers for ElevenLabs API."""
    settings = get_settings()
    
    if not settings.elevenlabs_api_key:
        return {}
    
    return {
        "xi-api-key": settings.elevenlabs_api_key,
        "Content-Type": "application/json",
    }


async def get_available_voices() -> list:
    """Get list of available ElevenLabs voices."""
    headers = get_elevenlabs_headers()
    
    if not headers:
        return []
    
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{ELEVENLABS_API_URL}/voices",
            headers=headers
        )
        
        if response.status_code == 200:
            return response.json().get("voices", [])
        
        return []


async def text_to_speech(
    text: str,
    voice_id: Optional[str] = None,
    model_id: Optional[str] = None,
    voice_settings: Optional[dict] = None
) -> Optional[bytes]:
    """
    Convert text to speech using ElevenLabs.
    
    Args:
        text: The text to convert to speech
        voice_id: ElevenLabs voice ID (uses default if not provided)
        model_id: ElevenLabs model ID (defaults to turbo_v2_5)
        voice_settings: Custom voice settings (defaults to DONNA_VOICE_SETTINGS)
    
    Returns:
        Audio bytes (MP3 format) or None if failed
    """
    settings = get_settings()
    
    if not settings.elevenlabs_api_key:
        logger.warning("ElevenLabs API key not configured")
        return None
    
    # Use configured voice or default
    voice_id = voice_id or settings.elevenlabs_voice_id
    
    if not voice_id:
        logger.warning("No ElevenLabs voice ID configured")
        return None
    
    # Use provided model or default
    model_id = model_id or DEFAULT_MODEL
    
    headers = get_elevenlabs_headers()
    
    payload = {
        "text": text,
        "model_id": model_id,
        "voice_settings": voice_settings or DONNA_VOICE_SETTINGS,
    }
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{ELEVENLABS_API_URL}/text-to-speech/{voice_id}",
                headers=headers,
                json=payload
            )
            
            if response.status_code == 200:
                logger.info(f"Generated voice with model {model_id}")
                return response.content
            else:
                logger.error(f"ElevenLabs API error: {response.status_code} - {response.text}")
                return None
                
    except Exception as e:
        logger.error(f"Error generating voice: {e}")
        return None


def prepare_text_for_speech(text: str) -> str:
    """
    Prepare text for natural-sounding TTS.
    
    Based on ElevenLabs best practices:
    - Remove markdown but preserve meaning
    - Spell out abbreviations
    - Format times and numbers naturally
    - Add natural pauses with punctuation
    """
    import re
    
    clean_text = text
    
    # === STEP 1: Remove markdown formatting ===
    # Headers become natural sentences
    clean_text = re.sub(r'^#{1,6}\s*', '', clean_text, flags=re.MULTILINE)
    
    # Bold/italic - just remove markers
    clean_text = clean_text.replace("**", "").replace("*", "")
    clean_text = clean_text.replace("__", "").replace("_", " ")
    
    # Code blocks and inline code
    clean_text = clean_text.replace("```", "").replace("`", "")
    
    # === STEP 2: Convert lists to natural speech ===
    # Bullet points become "First,", "Next,", "Also," etc.
    lines = clean_text.split('\n')
    processed_lines = []
    bullet_count = 0
    
    for line in lines:
        stripped = line.strip()
        # Check if it's a bullet point
        if stripped.startswith('- ') or stripped.startswith('• ') or stripped.startswith('* '):
            bullet_count += 1
            content = stripped[2:].strip()
            if bullet_count == 1:
                processed_lines.append(f"First, {content}.")
            elif bullet_count == 2:
                processed_lines.append(f"Second, {content}.")
            elif bullet_count == 3:
                processed_lines.append(f"Third, {content}.")
            else:
                processed_lines.append(f"Also, {content}.")
        else:
            bullet_count = 0  # Reset counter for non-bullet lines
            if stripped:
                processed_lines.append(stripped)
    
    clean_text = ' '.join(processed_lines)
    
    # === STEP 3: Fix time formats for natural speech ===
    # "12:00 PM" -> "12 P.M."
    # "3:30 PM" -> "3:30 P.M."
    clean_text = re.sub(r'(\d{1,2}):00\s*([AaPp][Mm])', r'\1 \2', clean_text)
    clean_text = re.sub(r'\bAM\b', 'A.M.', clean_text)
    clean_text = re.sub(r'\bPM\b', 'P.M.', clean_text)
    clean_text = re.sub(r'\bam\b', 'A.M.', clean_text)
    clean_text = re.sub(r'\bpm\b', 'P.M.', clean_text)
    
    # === STEP 4: Spell out common abbreviations ===
    abbreviations = {
        r'\bPRD\b': 'P.R.D.',
        r'\bAPI\b': 'A.P.I.',
        r'\bUI\b': 'U.I.',
        r'\bUX\b': 'U.X.',
        r'\bETD\b': 'E.T.D.',
        r'\bFYI\b': 'F.Y.I.',
        r'\bASAP\b': 'A.S.A.P.',
        r'\bTBD\b': 'T.B.D.',
        r'\bvs\b': 'versus',
        r'\bw/\b': 'with',
        r'\b&\b': 'and',
    }
    for pattern, replacement in abbreviations.items():
        clean_text = re.sub(pattern, replacement, clean_text, flags=re.IGNORECASE)
    
    # === STEP 5: Remove problematic characters ===
    # Arrows and special chars
    clean_text = clean_text.replace("→", ", then ")
    clean_text = clean_text.replace("←", "")
    clean_text = clean_text.replace("---", ". ")
    clean_text = clean_text.replace("--", ", ")
    clean_text = clean_text.replace("|", ", ")
    clean_text = clean_text.replace("/", " or ")
    
    # Remove emojis (they cause pronunciation issues)
    clean_text = re.sub(r'[^\x00-\x7F]+', '', clean_text)
    
    # === STEP 6: Clean up whitespace and punctuation ===
    # Multiple spaces to single space
    clean_text = re.sub(r'\s+', ' ', clean_text)
    
    # Multiple periods to single
    clean_text = re.sub(r'\.{2,}', '.', clean_text)
    
    # Ensure sentences end properly for natural pauses
    clean_text = re.sub(r'([a-zA-Z])\s+([A-Z])', r'\1. \2', clean_text)
    
    # Remove leading/trailing whitespace
    clean_text = clean_text.strip()
    
    # Ensure it ends with punctuation for proper delivery
    if clean_text and clean_text[-1] not in '.!?':
        clean_text += '.'
    
    return clean_text


async def generate_donna_voice(text: str) -> Optional[bytes]:
    """
    Generate a voice note in Donna's signature style.
    
    Preprocesses text for natural TTS delivery.
    
    Args:
        text: The text to convert
    
    Returns:
        Audio bytes or None
    """
    # Prepare text for natural speech
    clean_text = prepare_text_for_speech(text)
    
    logger.info(f"Prepared text for TTS: {clean_text[:100]}...")
    
    return await text_to_speech(clean_text)


async def generate_morning_brief_voice(brief_text: str) -> Optional[bytes]:
    """
    Generate voice for morning brief with Donna's personality.
    
    Adds intro and outro with personality for natural conversational delivery.
    """
    # Clean the brief text first
    clean_brief = prepare_text_for_speech(brief_text)
    
    # Add Donna's signature conversational style
    # Written as natural speech, not text
    enhanced_text = f"""
    Good morning. It's Donna.
    
    Here's your day.
    
    {clean_brief}
    
    Now get moving. You've got a lot to do, and I don't have time to repeat myself.
    """
    
    # Don't double-process - just clean whitespace
    import re
    enhanced_text = re.sub(r'\s+', ' ', enhanced_text).strip()
    
    return await text_to_speech(enhanced_text)


def get_voice_settings(
    stability: float = 0.35,
    similarity_boost: float = 0.80,
    style: float = 0.15,
    use_speaker_boost: bool = True
) -> dict:
    """
    Get custom voice settings.
    
    Args:
        stability: 0.0-1.0, lower = more expressive, higher = more stable
                   Recommended: 0.3-0.5 for natural speech
        similarity_boost: 0.0-1.0, how closely to match original voice
                          Recommended: 0.75-0.85
        style: 0.0-1.0, style exaggeration (can affect clarity)
               Recommended: 0.0-0.3 for clear pronunciation
        use_speaker_boost: Enhances voice similarity (slight latency increase)
    
    Returns:
        Voice settings dict for ElevenLabs API
    """
    return {
        "stability": max(0.0, min(1.0, stability)),
        "similarity_boost": max(0.0, min(1.0, similarity_boost)),
        "style": max(0.0, min(1.0, style)),
        "use_speaker_boost": use_speaker_boost,
    }


async def test_voice_settings(
    test_text: str = "Hello! I'm Donna, your executive assistant. Let me tell you about your schedule for today.",
    stability: float = 0.35,
    style: float = 0.15
) -> Optional[bytes]:
    """
    Test voice with custom settings.
    
    Useful for finding the right balance of expressiveness and clarity.
    """
    settings = get_voice_settings(stability=stability, style=style)
    return await text_to_speech(test_text, voice_settings=settings)


def sync_text_to_speech(text: str) -> Optional[bytes]:
    """
    Synchronous wrapper for text_to_speech.
    
    Used when async is not available.
    """
    import asyncio
    
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    return loop.run_until_complete(generate_donna_voice(text))


# ===========================================
# WHISPER TRANSCRIPTION (Speech-to-Text)
# ===========================================

async def transcribe_audio(audio_bytes: bytes, filename: str = "audio.ogg") -> Optional[str]:
    """
    Transcribe audio using OpenAI Whisper API.
    
    Args:
        audio_bytes: The audio data as bytes
        filename: The original filename (helps Whisper understand format)
    
    Returns:
        Transcribed text or None if failed
    """
    import openai
    
    settings = get_settings()
    
    if not settings.openai_api_key:
        logger.warning("OpenAI API key not configured for Whisper")
        return None
    
    try:
        client = openai.OpenAI(api_key=settings.openai_api_key)
        
        # Create a file-like object from bytes
        audio_file = io.BytesIO(audio_bytes)
        audio_file.name = filename
        
        # Call Whisper API
        transcript = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            response_format="text"
        )
        
        logger.info(f"Transcribed audio: {transcript[:50]}...")
        return transcript
        
    except Exception as e:
        logger.error(f"Whisper transcription error: {e}")
        return None


async def transcribe_telegram_voice(voice_file) -> Optional[str]:
    """
    Transcribe a Telegram voice message using Whisper.
    
    Args:
        voice_file: Telegram Voice file object
    
    Returns:
        Transcribed text or None
    """
    try:
        # Download the voice file
        audio_bytes = await voice_file.download_as_bytearray()
        
        # Telegram voice messages are in OGG format
        return await transcribe_audio(bytes(audio_bytes), "voice.ogg")
        
    except Exception as e:
        logger.error(f"Error transcribing Telegram voice: {e}")
        return None


def sync_transcribe_audio(audio_bytes: bytes, filename: str = "audio.ogg") -> Optional[str]:
    """
    Synchronous wrapper for transcribe_audio.
    """
    import asyncio
    
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    return loop.run_until_complete(transcribe_audio(audio_bytes, filename))


