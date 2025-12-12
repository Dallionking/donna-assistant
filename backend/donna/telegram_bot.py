"""
Telegram Bot for Donna.

Provides mobile access to Donna's capabilities including:
- Morning briefs (with voice notes!)
- Brain dumps via voice/text
- Schedule management
- PRD creation
- Voice note responses on demand
"""

import asyncio
import io
import logging
from datetime import datetime, date, timedelta
from typing import Optional

from telegram import Update, Bot
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from donna.config import get_settings
from donna.agent import chat
from donna.tools.schedule import generate_daily_schedule, get_schedule_for_date
from donna.tools.brain_dump import create_brain_dump, extract_action_items
from donna.tools.projects import get_all_projects, get_project_prd_status
from donna.tools.voice import generate_donna_voice, generate_morning_brief_voice, transcribe_telegram_voice
from donna.tools.calendar_sync import sync_schedule_to_calendar, clear_donna_calendar_events
from donna.tools.clients import add_client, search_clients, get_client_details, list_all_clients
from donna.tools.deals import create_deal, close_deal, get_active_deals, log_payment, get_revenue_summary, get_deals_pending_payment

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Store last response for /voice command
last_responses = {}


# ===========================================
# SECURITY
# ===========================================

def is_authorized(update: Update) -> bool:
    """Check if the user is authorized to use Donna."""
    settings = get_settings()
    authorized_id = settings.telegram_chat_id
    user_id = str(update.effective_user.id)
    
    if user_id != authorized_id:
        logger.warning(f"Unauthorized access attempt from user ID: {user_id}")
        return False
    return True


async def unauthorized_response(update: Update) -> None:
    """Send response to unauthorized users."""
    await update.message.reply_text(
        "I'm Donna. But I'm not YOUR Donna.\n\n"
        "I only work for one person, and it's not you. "
        "Nice try though."
    )


# ===========================================
# VOICE HELPERS
# ===========================================

async def send_voice_note(update: Update, text: str, caption: Optional[str] = None) -> bool:
    """
    Send a voice note to the user.
    
    Returns True if successful, False otherwise.
    """
    try:
        audio_bytes = await generate_donna_voice(text)
        
        if audio_bytes:
            voice_file = io.BytesIO(audio_bytes)
            voice_file.name = "donna_voice.mp3"
            
            await update.message.reply_voice(
                voice=voice_file,
                caption=caption
            )
            return True
        else:
            logger.warning("Failed to generate voice note")
            return False
            
    except Exception as e:
        logger.error(f"Error sending voice note: {e}")
        return False


def store_last_response(user_id: str, response: str) -> None:
    """Store the last response for a user."""
    last_responses[user_id] = response


def get_last_response(user_id: str) -> Optional[str]:
    """Get the last response for a user."""
    return last_responses.get(user_id)


# ===========================================
# COMMAND HANDLERS
# ===========================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    if not is_authorized(update):
        await unauthorized_response(update)
        return
    
    await update.message.reply_text(
        "I'm Donna. I know everything.\n\n"
        "And before you ask - yes, I already know what you need. "
        "But since you're new here, let me spell it out:\n\n"
        "**Schedule:**\n"
        "• `/schedule` - Your day. I've already optimized it.\n"
        "• `/tomorrow` - Tomorrow's plan. You're welcome.\n"
        "• `/approve` - Lock in the schedule.\n\n"
        "**Projects:**\n"
        "• `/projects` - All your projects. I'm tracking them.\n"
        "• `/prd [project]` - PRD status for a project.\n"
        "• `/braindump` - Dump your thoughts.\n\n"
        "**CRM (Clients & Deals):**\n"
        "• `/client [name]` - Look up a client\n"
        "• `/client add [name]` - Add new client\n"
        "• `/clients` - List all clients\n"
        "• `/deal [client] [amount] [type] [title]` - Close a deal\n"
        "• `/deals` - Show active deals\n"
        "• `/payment [client] [amount]` - Log payment received\n"
        "• `/revenue` - Revenue summary\n"
        "• `/pending` - Deals awaiting payment\n\n"
        "• `/voice` - Turn my last response into a voice note.\n\n"
        "Now, what do you need?"
    )


async def schedule_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /schedule command - includes automatic voice note."""
    if not is_authorized(update):
        await unauthorized_response(update)
        return
    
    try:
        schedule = get_schedule_for_date.invoke({"date_str": None})
        store_last_response(str(update.effective_user.id), schedule)
        
        # Send text first
        try:
            await update.message.reply_text(schedule, parse_mode='Markdown')
        except Exception:
            await update.message.reply_text(schedule)
        
        # Auto-send voice note for schedule
        settings = get_settings()
        if settings.elevenlabs_api_key and settings.elevenlabs_voice_id:
            try:
                audio_bytes = await generate_donna_voice(schedule)
                if audio_bytes:
                    voice_file = io.BytesIO(audio_bytes)
                    voice_file.name = "schedule.mp3"
                    await update.message.reply_voice(
                        voice=voice_file,
                        caption="Here's your day. Now go execute."
                    )
            except Exception as e:
                logger.error(f"Voice generation error: {e}")
                
    except Exception as e:
        logger.error(f"Schedule command error: {e}")
        await update.message.reply_text(
            "I'm having trouble generating your schedule. Give me a second and try again."
        )


async def tomorrow_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /tomorrow command - includes automatic voice note."""
    if not is_authorized(update):
        await unauthorized_response(update)
        return
    
    try:
        tomorrow = (datetime.now().date() + timedelta(days=1)).strftime("%Y-%m-%d")
        schedule = generate_daily_schedule.invoke({"date_str": tomorrow})
        store_last_response(str(update.effective_user.id), schedule)
        
        # Send text first
        try:
            await update.message.reply_text(schedule, parse_mode='Markdown')
        except Exception:
            await update.message.reply_text(schedule)
        
        # Auto-send voice note for tomorrow's schedule
        settings = get_settings()
        if settings.elevenlabs_api_key and settings.elevenlabs_voice_id:
            try:
                audio_bytes = await generate_donna_voice(schedule)
                if audio_bytes:
                    voice_file = io.BytesIO(audio_bytes)
                    voice_file.name = "tomorrow.mp3"
                    await update.message.reply_voice(
                        voice=voice_file,
                        caption="Tomorrow's plan. I've already thought ahead for you."
                    )
            except Exception as e:
                logger.error(f"Voice generation error: {e}")
                
    except Exception as e:
        logger.error(f"Tomorrow command error: {e}")
        await update.message.reply_text(
            "I'm having trouble with tomorrow's schedule. Try again in a moment."
        )


async def braindump_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /braindump command."""
    if not is_authorized(update):
        await unauthorized_response(update)
        return
    
    response = (
        "Alright, let it out. I'm listening.\n\n"
        "Text or voice - doesn't matter. I'll make sense of whatever chaos "
        "is bouncing around in that head of yours.\n\n"
        "I'll pull out the action items, separate the Signal from the Noise, "
        "and file it where it belongs. That's what I do.\n\n"
        "Go ahead. I don't have all day. Well, I do - but you don't."
    )
    store_last_response(str(update.effective_user.id), response)
    await update.message.reply_text(response)


async def projects_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /projects command."""
    if not is_authorized(update):
        await unauthorized_response(update)
        return
    
    try:
        projects = get_all_projects.invoke({})
        store_last_response(str(update.effective_user.id), projects)
        
        try:
            await update.message.reply_text(projects, parse_mode='Markdown')
        except Exception:
            await update.message.reply_text(projects)
    except Exception as e:
        logger.error(f"Projects command error: {e}")
        await update.message.reply_text("Error loading projects. Check the project registry.")


async def prd_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /prd [project] command."""
    if not is_authorized(update):
        await unauthorized_response(update)
        return
    
    args = context.args
    
    if not args:
        await update.message.reply_text(
            "Please specify a project:\n"
            "`/prd sigmavue`\n"
            "`/prd sss`\n"
            "`/prd ruthless`"
        )
        return
    
    project_name = args[0]
    status = get_project_prd_status.invoke({"project_name": project_name})
    store_last_response(str(update.effective_user.id), status)
    await update.message.reply_text(status, parse_mode='Markdown')


async def signal_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /signal command."""
    if not is_authorized(update):
        await unauthorized_response(update)
        return
    
    response = await chat("/signal - What are my top 3 tasks today?")
    store_last_response(str(update.effective_user.id), response)
    await update.message.reply_text(response)


async def approve_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /approve command."""
    if not is_authorized(update):
        await unauthorized_response(update)
        return
    
    response = (
        "Good choice. I knew you'd agree with me.\n\n"
        "Your schedule is locked. If Calendly throws a wrench in it, "
        "I'll handle it before you even notice.\n\n"
        "Now stop looking at your phone and go be brilliant. "
        "That's what I keep you around for."
    )
    store_last_response(str(update.effective_user.id), response)
    await update.message.reply_text(response)


async def adjust_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /adjust command."""
    if not is_authorized(update):
        await unauthorized_response(update)
        return
    
    response = (
        "Fine. What do you want to change?\n\n"
        "Just tell me:\n"
        "• 'Move Sigmavue to 3pm'\n"
        "• 'Add a call at 2pm'\n"
        "• 'Skip gym today' (I'll pretend I didn't hear that)\n"
        "• 'Work on Ruthless instead of AdForge'\n\n"
        "But just so we're clear - my original schedule was perfect. "
        "I'm only doing this because I'm gracious like that."
    )
    store_last_response(str(update.effective_user.id), response)
    await update.message.reply_text(response)


async def voice_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /voice command - convert last response to voice note."""
    if not is_authorized(update):
        await unauthorized_response(update)
        return
    
    user_id = str(update.effective_user.id)
    last_response = get_last_response(user_id)
    
    if not last_response:
        await update.message.reply_text(
            "I don't have anything to read to you yet. "
            "Ask me something first, then use /voice."
        )
        return
    
    # Check if ElevenLabs is configured
    settings = get_settings()
    if not settings.elevenlabs_api_key:
        await update.message.reply_text(
            "Voice notes aren't set up yet. "
            "Add your ElevenLabs API key to make me talk.\n\n"
            "Add ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID to your .env file."
        )
        return
    
    await update.message.reply_text("One moment. Recording my dulcet tones...")
    
    success = await send_voice_note(update, last_response)
    
    if not success:
        await update.message.reply_text(
            "Hmm. My voice isn't cooperating right now. "
            "Check the ElevenLabs configuration."
        )


async def idea_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /idea [project] [description] command."""
    if not is_authorized(update):
        await unauthorized_response(update)
        return
    
    args = context.args
    
    if len(args) < 2:
        await update.message.reply_text(
            "Usage: `/idea [project] [description]`\n\n"
            "Example: `/idea sigmavue Add dark mode to dashboard`"
        )
        return
    
    project = args[0]
    description = " ".join(args[1:])
    
    # Create brain dump with project reference
    result = create_brain_dump.invoke({
        "content": f"Feature idea for {project}: {description}",
        "title": f"Idea: {description[:30]}"
    })
    
    response = (
        f"Idea logged for **{project}**.\n\n"
        f"{description}\n\n"
        f"I've filed it. Want me to create a PRD? "
        f"Reply `/createprd {project} {description[:20]}`"
    )
    store_last_response(str(update.effective_user.id), response)
    await update.message.reply_text(response)


async def create_prd_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /createprd [project] [feature] command."""
    if not is_authorized(update):
        await unauthorized_response(update)
        return
    
    args = context.args
    
    if len(args) < 2:
        await update.message.reply_text(
            "Usage: `/createprd [project] [feature name]`\n\n"
            "Example: `/createprd sigmavue Dark Mode Support`"
        )
        return
    
    project = args[0]
    feature = " ".join(args[1:])
    
    response = (
        f"PRD Creation Request\n\n"
        f"**Project**: {project}\n"
        f"**Feature**: {feature}\n\n"
        f"I'll handle this. Open Cursor and I'll have the PRD ready."
    )
    store_last_response(str(update.effective_user.id), response)
    await update.message.reply_text(response)


# ===========================================
# CALENDAR SYNC COMMANDS
# ===========================================

async def sync_calendar_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /sync_calendar command - sync schedule to Google Calendar."""
    if not is_authorized(update):
        await unauthorized_response(update)
        return
    
    await update.message.reply_text("🔄 Syncing your schedule to Google Calendar...")
    
    try:
        # Call the sync tool
        result = sync_schedule_to_calendar.invoke({
            "include_morning": True,
            "include_work": True,
            "include_evening": False,
            "clear_existing": True
        })
        
        store_last_response(str(update.effective_user.id), result)
        await update.message.reply_text(result)
        
        # Send voice confirmation
        await send_voice_note(update, "Your schedule has been synced to Google Calendar. All your time blocks are now recurring. You're welcome.")
        
    except Exception as e:
        logger.error(f"Calendar sync error: {e}")
        await update.message.reply_text(
            f"❌ Failed to sync calendar. Error: {str(e)[:100]}\n\n"
            "Make sure Google Calendar is connected."
        )


async def clear_calendar_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /clear_calendar command - remove all Donna events."""
    if not is_authorized(update):
        await unauthorized_response(update)
        return
    
    try:
        result = clear_donna_calendar_events.invoke({})
        store_last_response(str(update.effective_user.id), result)
        await update.message.reply_text(result)
    except Exception as e:
        logger.error(f"Clear calendar error: {e}")
        await update.message.reply_text(f"❌ Failed to clear calendar. Error: {str(e)[:100]}")


# ===========================================
# CRM COMMANDS (Clients, Deals, Revenue)
# ===========================================

async def client_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /client command - add or search clients.
    
    Usage:
    - /client add John Doe - Add a new client
    - /client John - Search for a client
    - /clients - List all clients
    """
    if not is_authorized(update):
        await unauthorized_response(update)
        return
    
    args = context.args
    
    if not args:
        # Show all clients
        try:
            result = list_all_clients.invoke({})
            store_last_response(str(update.effective_user.id), result)
            try:
                await update.message.reply_text(result, parse_mode='Markdown')
            except Exception:
                await update.message.reply_text(result)
        except Exception as e:
            logger.error(f"Client list error: {e}")
            await update.message.reply_text("Error loading clients.")
        return
    
    if args[0].lower() == "add":
        # Add new client
        if len(args) < 2:
            await update.message.reply_text(
                "Usage: `/client add [name]`\n\n"
                "Example: `/client add John Smith`"
            )
            return
        
        name = " ".join(args[1:])
        try:
            result = add_client.invoke({"name": name, "source": "telegram"})
            store_last_response(str(update.effective_user.id), result)
            await update.message.reply_text(result)
        except Exception as e:
            logger.error(f"Add client error: {e}")
            await update.message.reply_text(f"Failed to add client: {str(e)[:50]}")
    else:
        # Search for client
        query = " ".join(args)
        try:
            result = get_client_details.invoke({"client_name": query})
            store_last_response(str(update.effective_user.id), result)
            try:
                await update.message.reply_text(result, parse_mode='Markdown')
            except Exception:
                await update.message.reply_text(result)
        except Exception as e:
            logger.error(f"Client search error: {e}")
            await update.message.reply_text(f"Error searching clients: {str(e)[:50]}")


async def clients_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /clients command - list all clients."""
    if not is_authorized(update):
        await unauthorized_response(update)
        return
    
    try:
        result = list_all_clients.invoke({})
        store_last_response(str(update.effective_user.id), result)
        try:
            await update.message.reply_text(result, parse_mode='Markdown')
        except Exception:
            await update.message.reply_text(result)
    except Exception as e:
        logger.error(f"Clients command error: {e}")
        await update.message.reply_text("Error loading clients.")


async def deal_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /deal command - close a deal.
    
    Usage: /deal [client] [amount] [type] [title]
    Example: /deal John 5000 app_build Mobile App
    """
    if not is_authorized(update):
        await unauthorized_response(update)
        return
    
    args = context.args
    
    if len(args) < 3:
        await update.message.reply_text(
            "Usage: `/deal [client] [amount] [type] [title]`\n\n"
            "Types: `app_build`, `consulting`, `mentorship`\n\n"
            "Example:\n"
            "`/deal John 5000 app_build Mobile App for Acme Corp`"
        )
        return
    
    client_name = args[0]
    
    try:
        amount = float(args[1].replace("$", "").replace(",", ""))
    except ValueError:
        await update.message.reply_text("Invalid amount. Use a number like `5000` or `5000.00`")
        return
    
    deal_type = args[2] if len(args) > 2 else "app_build"
    title = " ".join(args[3:]) if len(args) > 3 else f"{deal_type.replace('_', ' ').title()}"
    
    try:
        result = close_deal.invoke({
            "client_name": client_name,
            "title": title,
            "deal_type": deal_type,
            "amount": amount
        })
        store_last_response(str(update.effective_user.id), result)
        await update.message.reply_text(result)
        
        # Voice celebration for closed deals
        settings = get_settings()
        if settings.elevenlabs_api_key and settings.elevenlabs_voice_id:
            await send_voice_note(
                update, 
                f"Deal closed! {title} for ${amount:,.0f}. I love it when the money comes in."
            )
            
    except Exception as e:
        logger.error(f"Deal command error: {e}")
        await update.message.reply_text(f"Failed to close deal: {str(e)[:50]}")


async def deals_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /deals command - show active deals."""
    if not is_authorized(update):
        await unauthorized_response(update)
        return
    
    try:
        result = get_active_deals.invoke({})
        store_last_response(str(update.effective_user.id), result)
        try:
            await update.message.reply_text(result, parse_mode='Markdown')
        except Exception:
            await update.message.reply_text(result)
    except Exception as e:
        logger.error(f"Deals command error: {e}")
        await update.message.reply_text("Error loading deals.")


async def revenue_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /revenue command - show revenue summary."""
    if not is_authorized(update):
        await unauthorized_response(update)
        return
    
    try:
        result = get_revenue_summary.invoke({})
        store_last_response(str(update.effective_user.id), result)
        try:
            await update.message.reply_text(result, parse_mode='Markdown')
        except Exception:
            await update.message.reply_text(result)
    except Exception as e:
        logger.error(f"Revenue command error: {e}")
        await update.message.reply_text("Error calculating revenue.")


async def payment_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /payment command - log a payment.
    
    Usage: /payment [client] [amount] [method]
    Example: /payment John 2500 stripe
    """
    if not is_authorized(update):
        await unauthorized_response(update)
        return
    
    args = context.args
    
    if len(args) < 2:
        await update.message.reply_text(
            "Usage: `/payment [client] [amount] [method]`\n\n"
            "Methods: `stripe`, `paypal`, `wire`, `cash`\n\n"
            "Example: `/payment John 2500 stripe`"
        )
        return
    
    client_name = args[0]
    
    try:
        amount = float(args[1].replace("$", "").replace(",", ""))
    except ValueError:
        await update.message.reply_text("Invalid amount.")
        return
    
    method = args[2] if len(args) > 2 else "stripe"
    
    try:
        result = log_payment.invoke({
            "client_name": client_name,
            "amount": amount,
            "method": method
        })
        store_last_response(str(update.effective_user.id), result)
        await update.message.reply_text(result)
    except Exception as e:
        logger.error(f"Payment command error: {e}")
        await update.message.reply_text(f"Failed to log payment: {str(e)[:50]}")


async def pending_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /pending command - show deals pending payment."""
    if not is_authorized(update):
        await unauthorized_response(update)
        return
    
    try:
        result = get_deals_pending_payment.invoke({})
        store_last_response(str(update.effective_user.id), result)
        try:
            await update.message.reply_text(result, parse_mode='Markdown')
        except Exception:
            await update.message.reply_text(result)
    except Exception as e:
        logger.error(f"Pending command error: {e}")
        await update.message.reply_text("Error loading pending deals.")


# ===========================================
# MESSAGE HANDLERS
# ===========================================

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle regular text messages - conversational AI."""
    if not is_authorized(update):
        await unauthorized_response(update)
        return
    
    user_message = update.message.text
    logger.info(f"Received message: {user_message}")
    
    try:
        # Send to Donna agent
        response = await chat(user_message)
        
        if response:
            store_last_response(str(update.effective_user.id), response)
            await update.message.reply_text(response)
        else:
            await update.message.reply_text(
                "I'm thinking, but nothing's coming to mind. Try again?"
            )
    except Exception as e:
        logger.error(f"Chat error: {e}")
        await update.message.reply_text(
            "Something went wrong on my end. I know, shocking. "
            "Give me a second and try again."
        )


async def handle_voice_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle voice messages (brain dumps) with Whisper transcription."""
    if not is_authorized(update):
        await unauthorized_response(update)
        return
    
    voice = update.message.voice
    
    await update.message.reply_text("🎙️ Got it. Listening...")
    
    try:
        # Download voice file
        voice_file = await voice.get_file()
        
        # Transcribe with Whisper
        transcription = await transcribe_telegram_voice(voice_file)
        
        if transcription:
            logger.info(f"Transcribed voice: {transcription[:50]}...")
            
            # Show the transcription
            await update.message.reply_text(
                f"📝 **Heard you say:**\n\n_{transcription}_",
                parse_mode='Markdown'
            )
            
            # Process as a regular message (could be brain dump, command, etc.)
            # Send to Donna agent for processing
            response = await chat(transcription)
            
            if response:
                store_last_response(str(update.effective_user.id), response)
                await update.message.reply_text(response)
            
        else:
            await update.message.reply_text(
                "I heard you, but I couldn't make out what you said. "
                "Try again or just type it out."
            )
            
    except Exception as e:
        logger.error(f"Voice transcription error: {e}")
        await update.message.reply_text(
            "Something went wrong transcribing your voice note. "
            "Give me a second and try again, or type it out."
        )


# ===========================================
# MORNING BRIEF WITH VOICE
# ===========================================

async def send_morning_brief(bot: Bot, chat_id: str) -> None:
    """Send the morning brief to Telegram with optional voice note."""
    today = datetime.now().date()
    
    # Generate schedule
    schedule = generate_daily_schedule.invoke({"date_str": None})
    
    # Build morning brief
    brief = f"""Rise and shine. It's Donna.

I've already optimized your day, checked Calendly for conflicts, and made sure Sigmavue gets the attention it deserves. You're welcome.

{schedule}

---

Now, before you start questioning my decisions:
• `/approve` - Smart move. Lock it in.
• `/adjust` - If you must. But I was right.
• `/braindump` - Got ideas? I'm listening.
• `/voice` - Hear me say it.

Don't be late. I hate late.
"""
    
    # Send text brief
    await bot.send_message(chat_id=chat_id, text=brief)
    
    # Try to send voice note
    settings = get_settings()
    if settings.elevenlabs_api_key and settings.elevenlabs_voice_id:
        try:
            audio_bytes = await generate_morning_brief_voice(schedule)
            
            if audio_bytes:
                voice_file = io.BytesIO(audio_bytes)
                voice_file.name = "morning_brief.mp3"
                
                await bot.send_voice(
                    chat_id=chat_id,
                    voice=voice_file,
                    caption="Your morning brief. Now you can't say you didn't hear me."
                )
        except Exception as e:
            logger.error(f"Failed to send voice morning brief: {e}")


# ===========================================
# BOT SETUP
# ===========================================

def create_bot() -> Application:
    """Create and configure the Telegram bot."""
    settings = get_settings()
    
    # Create application
    application = Application.builder().token(settings.telegram_bot_token).build()
    
    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("schedule", schedule_command))
    application.add_handler(CommandHandler("tomorrow", tomorrow_command))
    application.add_handler(CommandHandler("braindump", braindump_command))
    application.add_handler(CommandHandler("projects", projects_command))
    application.add_handler(CommandHandler("prd", prd_command))
    application.add_handler(CommandHandler("signal", signal_command))
    application.add_handler(CommandHandler("approve", approve_command))
    application.add_handler(CommandHandler("adjust", adjust_command))
    application.add_handler(CommandHandler("voice", voice_command))
    application.add_handler(CommandHandler("idea", idea_command))
    application.add_handler(CommandHandler("createprd", create_prd_command))
    application.add_handler(CommandHandler("sync_calendar", sync_calendar_command))
    application.add_handler(CommandHandler("clear_calendar", clear_calendar_command))
    
    # CRM commands
    application.add_handler(CommandHandler("client", client_command))
    application.add_handler(CommandHandler("clients", clients_command))
    application.add_handler(CommandHandler("deal", deal_command))
    application.add_handler(CommandHandler("deals", deals_command))
    application.add_handler(CommandHandler("revenue", revenue_command))
    application.add_handler(CommandHandler("payment", payment_command))
    application.add_handler(CommandHandler("pending", pending_command))
    
    # Add message handlers
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    application.add_handler(MessageHandler(filters.VOICE, handle_voice_message))
    
    return application


async def run_bot():
    """Run the Telegram bot."""
    application = create_bot()
    
    # Start polling
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    
    logger.info("Donna Telegram bot started!")
    
    # Keep running until interrupted
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        await application.updater.stop()
        await application.stop()
        await application.shutdown()


if __name__ == "__main__":
    asyncio.run(run_bot())
