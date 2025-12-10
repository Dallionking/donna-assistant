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

# Default voice settings for Donna's personality
# Confident, slightly playful, professional
DONNA_VOICE_SETTINGS = {
    "stability": 0.5,  # More expressive
    "similarity_boost": 0.75,  # Keep voice consistent
    "style": 0.4,  # Add some style/sass
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
    model_id: str = "eleven_multilingual_v2"
) -> Optional[bytes]:
    """
    Convert text to speech using ElevenLabs.
    
    Args:
        text: The text to convert to speech
        voice_id: ElevenLabs voice ID (uses default if not provided)
        model_id: ElevenLabs model ID
    
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
    
    headers = get_elevenlabs_headers()
    
    payload = {
        "text": text,
        "model_id": model_id,
        "voice_settings": DONNA_VOICE_SETTINGS,
    }
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{ELEVENLABS_API_URL}/text-to-speech/{voice_id}",
                headers=headers,
                json=payload
            )
            
            if response.status_code == 200:
                return response.content
            else:
                logger.error(f"ElevenLabs API error: {response.status_code} - {response.text}")
                return None
                
    except Exception as e:
        logger.error(f"Error generating voice: {e}")
        return None


async def generate_donna_voice(text: str) -> Optional[bytes]:
    """
    Generate a voice note in Donna's signature style.
    
    Adds a touch of sass and personality to the delivery.
    
    Args:
        text: The text to convert
    
    Returns:
        Audio bytes or None
    """
    # Clean up the text for better TTS
    # Remove markdown formatting
    clean_text = text.replace("**", "").replace("*", "")
    clean_text = clean_text.replace("###", "").replace("##", "").replace("#", "")
    clean_text = clean_text.replace("`", "")
    clean_text = clean_text.replace("→", "... ")
    clean_text = clean_text.replace("•", "...")
    clean_text = clean_text.replace("---", "")
    
    # Remove emoji
    import re
    clean_text = re.sub(r'[^\x00-\x7F]+', '', clean_text)
    
    # Trim excessive whitespace
    clean_text = re.sub(r'\s+', ' ', clean_text).strip()
    
    return await text_to_speech(clean_text)


async def generate_morning_brief_voice(brief_text: str) -> Optional[bytes]:
    """
    Generate voice for morning brief with Donna's personality.
    
    Adds intro and outro with personality.
    """
    # Add Donna's signature style
    enhanced_text = f"""
    Good morning. It's Donna.
    
    {brief_text}
    
    Now get moving. You've got a lot to do and I don't have time to repeat myself.
    """
    
    return await generate_donna_voice(enhanced_text)


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


