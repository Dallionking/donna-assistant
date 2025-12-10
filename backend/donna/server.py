"""
Web server for Donna - enables deployment on Render.

Provides:
- Health check endpoint for Render
- Calendly webhook endpoint for real-time event notifications
- Runs Telegram bot in background
- Handles graceful shutdown
"""

import asyncio
import hashlib
import hmac
import logging
import threading
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse

from donna.telegram_bot import create_bot
from donna.scheduler import DonnaScheduler
from donna.config import get_settings

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Global references
bot_application = None
scheduler = None


async def start_bot():
    """Start the Telegram bot."""
    global bot_application
    
    bot_application = create_bot()
    await bot_application.initialize()
    await bot_application.start()
    await bot_application.updater.start_polling()
    logger.info("Telegram bot started!")


async def stop_bot():
    """Stop the Telegram bot."""
    global bot_application
    
    if bot_application:
        await bot_application.updater.stop()
        await bot_application.stop()
        await bot_application.shutdown()
        logger.info("Telegram bot stopped!")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle."""
    global scheduler
    
    # Startup
    logger.info("Starting Donna services...")
    
    # Start scheduler
    scheduler = DonnaScheduler()
    scheduler.start()
    
    # Start Telegram bot
    await start_bot()
    
    logger.info("Donna is ready!")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Donna...")
    await stop_bot()
    if scheduler:
        scheduler.stop()
    logger.info("Donna shut down gracefully.")


# Create FastAPI app
app = FastAPI(
    title="Donna - Personal Executive Assistant",
    description="I'm Donna. I know everything.",
    version="1.0.0",
    lifespan=lifespan
)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "Donna",
        "status": "I'm Donna. I know everything.",
        "version": "1.0.0"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint for Render."""
    return JSONResponse(
        status_code=200,
        content={
            "status": "healthy",
            "message": "I'm still here. Obviously."
        }
    )


@app.get("/status")
async def status():
    """Detailed status endpoint."""
    return {
        "bot": "running" if bot_application else "stopped",
        "scheduler": "running" if scheduler else "stopped",
        "personality": "Donna Paulsen",
        "sass_level": "maximum"
    }


# ===========================================
# CALENDLY WEBHOOK
# ===========================================

def verify_calendly_signature(payload: bytes, signature: str, secret: str) -> bool:
    """
    Verify Calendly webhook signature.
    
    Calendly signs webhooks with HMAC-SHA256.
    """
    if not secret:
        # No secret configured, skip verification
        return True
    
    expected = hmac.new(
        secret.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(expected, signature)


async def notify_calendly_event(event_type: str, event_data: dict):
    """
    Send Telegram notification about Calendly event.
    """
    global bot_application
    
    settings = get_settings()
    chat_id = settings.telegram_chat_id
    
    if not bot_application or not chat_id:
        logger.warning("Cannot send Calendly notification - bot not ready")
        return
    
    try:
        if event_type == "invitee.created":
            # New booking!
            event = event_data.get("payload", {})
            invitee = event.get("invitee", {})
            scheduled_event = event.get("scheduled_event", {})
            
            name = invitee.get("name", "Someone")
            email = invitee.get("email", "unknown")
            event_name = scheduled_event.get("name", "a call")
            start_time = scheduled_event.get("start_time", "")
            
            # Parse time for nice formatting
            if start_time:
                try:
                    dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
                    time_str = dt.strftime("%A, %B %d at %I:%M %p")
                except Exception:
                    time_str = start_time
            else:
                time_str = "TBD"
            
            message = f"""📞 **New Call Booked!**

Someone just booked a call. I already adjusted your schedule.

**Event**: {event_name}
**With**: {name} ({email})
**When**: {time_str}

Your project block has been moved. You're welcome.
"""
            
        elif event_type == "invitee.canceled":
            event = event_data.get("payload", {})
            invitee = event.get("invitee", {})
            
            name = invitee.get("name", "Someone")
            
            message = f"""❌ **Call Canceled**

{name} canceled their call.

I've already restored your original schedule. More time for Sigmavue.
"""
        else:
            # Other event types
            message = f"📬 Calendly event: {event_type}"
        
        await bot_application.bot.send_message(
            chat_id=chat_id,
            text=message,
            parse_mode='Markdown'
        )
        
        logger.info(f"Sent Calendly notification: {event_type}")
        
    except Exception as e:
        logger.error(f"Error sending Calendly notification: {e}")


@app.post("/webhooks/calendly")
async def calendly_webhook(request: Request):
    """
    Handle Calendly webhook events.
    
    Events:
    - invitee.created: New booking
    - invitee.canceled: Cancellation
    - routing_form_submission.created: Routing form submitted
    
    Calendly webhooks docs:
    https://developer.calendly.com/api-docs/ZG9jOjM2MzE2MDM4-webhooks-overview
    """
    settings = get_settings()
    
    # Get raw body for signature verification
    body = await request.body()
    
    # Verify signature if webhook secret is configured
    signature = request.headers.get("Calendly-Webhook-Signature", "")
    
    if settings.calendly_webhook_secret:
        if not verify_calendly_signature(body, signature, settings.calendly_webhook_secret):
            logger.warning("Invalid Calendly webhook signature")
            raise HTTPException(status_code=401, detail="Invalid signature")
    
    # Parse event
    try:
        import json
        data = json.loads(body)
    except Exception as e:
        logger.error(f"Error parsing Calendly webhook: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON")
    
    event_type = data.get("event", "unknown")
    
    logger.info(f"Received Calendly webhook: {event_type}")
    
    # Handle the event
    await notify_calendly_event(event_type, data)
    
    return JSONResponse(
        status_code=200,
        content={"status": "received", "event": event_type}
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

