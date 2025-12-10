# Donna Backend

AI-powered personal assistant backend using LangGraph and Supabase.

## Quick Start

### 1. Set Up Python Environment

```bash
cd /Users/dallionking/Donna/backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
# Copy the example environment file
cp env-example.txt .env

# Edit .env with your API keys
```

Required API Keys:
- `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` - Supabase project
- `OPENAI_API_KEY` - For LLM and embeddings
- `TELEGRAM_BOT_TOKEN` - Create via @BotFather
- `TELEGRAM_CHAT_ID` - Your Telegram user ID

Optional (for full functionality):
- `CALENDLY_API_KEY` - For call scheduling
- `GITHUB_TOKEN` - For issue tracking
- Google OAuth credentials - For Calendar/Gmail

### 3. Set Up Database

Run this SQL in Supabase SQL Editor:

```sql
-- See donna/database.py for full schema
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE brain_dumps (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    title TEXT,
    content TEXT,
    file_path TEXT,
    project_refs TEXT[],
    action_items JSONB,
    embedding VECTOR(1536)
);

-- ... (see database.py for complete schema)
```

### 4. Run Donna

```bash
# Start the Telegram bot and scheduler
python -m donna.main
```

This starts:
- **Telegram Bot** - For mobile access
- **Scheduler** - For morning briefs and Calendly sync

## Architecture

```
donna/
├── agent.py          # LangGraph agent orchestration
├── config.py         # Configuration and settings
├── models.py         # Pydantic data models
├── database.py       # Supabase operations
├── telegram_bot.py   # Telegram bot handlers
├── scheduler.py      # Automated task scheduler
├── main.py           # Entry point
└── tools/
    ├── projects.py   # Project registry and PRD status
    ├── brain_dump.py # Brain dump processing
    ├── schedule.py   # Daily schedule generation
    ├── calendar.py   # Google Calendar integration
    ├── calendly.py   # Calendly integration
    ├── gmail.py      # Gmail integration
    ├── github.py     # GitHub integration
    └── handoff.py    # Handoff document generation
```

## Automated Schedules

| Time | Task |
|------|------|
| 5:00 AM | Morning brief sent to Telegram |
| Every 3 hours | Calendly sync + conflict detection |
| 9:00 PM | Evening summary + tomorrow planning |

## Telegram Commands

| Command | Description |
|---------|-------------|
| `/start` | Introduction and help |
| `/schedule` | Today's schedule |
| `/tomorrow` | Tomorrow's plan |
| `/braindump` | Start a brain dump |
| `/projects` | List all projects |
| `/prd [project]` | PRD status for a project |
| `/signal` | Top 3 tasks today |
| `/approve` | Lock in schedule |
| `/adjust` | Make changes |

## Google OAuth Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a new project or select existing
3. Enable these APIs:
   - Google Calendar API
   - Gmail API
   - YouTube Data API v3
4. Create OAuth 2.0 credentials (Desktop app)
5. Download `credentials.json` to `backend/credentials/`
6. Run OAuth flow once to generate `token.json`

## Development

```bash
# Run tests
pytest

# Format code
black donna/
ruff donna/
```

## License

MIT


