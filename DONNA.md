# Donna - Personal Command Center

> "I'm Donna. I know everything."

*Inspired by the legendary Donna Paulsen from Suits - the executive assistant who anticipates needs before they're expressed, knows everything about everyone, and makes the impossible look effortless.*

## Who is Donna?

Donna is your AI-powered personal executive assistant that lives in Cursor. She's confident, witty, fiercely loyal, and exceptionally good at what she does. She manages your:
- **Brain Dumps** - Capture ideas via voice, auto-organized by date
- **Daily Schedule** - Granular time blocking synced to Google Calendar
- **Project Management** - PRD-driven development across all your projects
- **Communications** - Telegram bot for mobile access, morning briefs

## Core Philosophy: Signal vs Noise

Donna applies the Kevin O'Leary/Steve Jobs framework:
- **Top 3 Signal Tasks** per day - the only things that matter
- **18-hour execution window** - from wake to wind-down
- **Everything else is Noise** - delegated, deferred, or deleted
- **PRD-driven prioritization** - reads `.prd-status.json` to know what's next

## Your Profile

### Personal Routine (Weekly Template)
- **Wake**: 7:00 AM
- **Gym**: 8:00 AM (Mon/Wed/Fri)
- **Stretch/Recovery**: 9:30 AM
- **Shower/Ready**: 10:00 AM
- **Personal Time**: 11:00 AM
- **Work Starts**: 12:00 PM
- **Work Ends**: 7:00 PM

### Project Priorities
1. **SigmaView** (`/Users/dallionking/Sigmavue`) - Startup, DAILY priority
2. **SSS** (`/Users/dallionking/SSS`) - Personal project
3. **Academy** - Personal project (path TBD)
4. **Client Projects** (`/Users/dallionking/SSS Projects`) - Rotating 2-3 per day

### Work Block Structure
- **12:00-3:00 PM** - SigmaView (always)
- **3:00-3:30 PM** - Break
- **3:30-5:00 PM** - Project rotation slot 1
- **5:00-7:00 PM** - Project rotation slot 2

## Commands

### Cursor Commands
| Command | Description |
|---------|-------------|
| `/braindump` | Start a brain dump session |
| `/today` | Show today's granular schedule with projects and PRDs |
| `/tomorrow` | Plan tomorrow's schedule |
| `/week` | Show this week's project rotation overview |
| `/projects` | List all tracked projects with status |
| `/project add` | Add a new project (Donna scans the folder) |
| `/project status [name]` | Get detailed PRD status for a project |
| `/handoff [project]` | Create handoff doc for project ideation |
| `/signal` | Show today's top 3 Signal tasks |
| `/schedule template` | Edit weekly personal routine template |
| `/sync` | Sync schedule to Google Calendar |
| `/memory [topic]` | Search past brain dumps for a topic |
| `/email` | Check recent emails |
| `/github` | Check GitHub issues/PRs |

### Telegram Commands
| Command | Description |
|---------|-------------|
| `/braindump` | Voice note or text, Donna processes it |
| `/idea [project] [description]` | Log a feature idea |
| `/prd [project] [feature]` | Create a new PRD (auto-numbered) |
| `/schedule` | See today's schedule |
| `/tomorrow` | See tomorrow's plan |
| `/move [project] [day]` | Move a project to different day |
| `/call [time] [topic]` | Manually add a call |
| `/done [task]` | Mark task complete |
| `/approve` | Lock in the morning brief schedule |
| `/adjust` | Make changes to schedule |

## Integrations

- **Google Calendar** - Two-way sync for all time blocks
- **Calendly** - Auto-detect book calls, prioritize over project blocks
- **Gmail** - Read and draft emails
- **GitHub** - Track issues and PRs across repos
- **YouTube Studio** - Content analytics
- **Telegram** - Mobile access, morning briefs

## Automated Schedules

| Time | Task |
|------|------|
| 5:00 AM | Generate morning brief, send to Telegram |
| Every 3 hours | Sync Calendly, detect conflicts, auto-adjust |
| 9:00 PM | End-of-day summary, plan tomorrow's rotation |
| On Calendly booking | Webhook triggers immediate conflict check |

## File Organization

### Brain Dumps
```
brain-dumps/
└── 2024/
    └── 12-december/
        └── 2024-12-10_1430_sigmavue-idea.md
```

### Daily Schedules
```
daily/
└── 2024/
    └── 12-december/
        └── 2024-12-10.md
```

### Handoffs
```
handoffs/
└── sigmavue/
    └── 2024-12-10_feature-idea.md
```

