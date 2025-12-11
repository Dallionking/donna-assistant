"""
Donna - LangGraph Agent

The main orchestration agent that coordinates all of Donna's capabilities.
"""

import json
from datetime import datetime, date
from typing import TypedDict, Annotated, Sequence, Literal
from pathlib import Path

from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

from donna.config import get_settings
from donna.models import (
    BrainDump, DailySchedule, MorningBrief, 
    ProjectPRDStatus, Handoff, TaskPriority
)
from donna.tools.projects import (
    get_all_projects,
    get_project_prd_status,
    scan_and_add_project,
    update_project_last_worked,
    get_projects_needing_attention,
    suggest_next_project,
)
from donna.tools.brain_dump import (
    create_brain_dump,
    search_brain_dumps,
    extract_action_items,
    get_recent_brain_dumps,
)
from donna.tools.calendar import (
    get_today_events,
    create_time_block,
)
from donna.tools.schedule import (
    generate_daily_schedule,
    get_schedule_for_date,
    update_schedule,
    get_tomorrow_schedule,
)
from donna.tools.calendar_sync import (
    sync_schedule_to_calendar,
    clear_donna_calendar_events,
    update_schedule_template,
)
from donna.tools.handoff import (
    create_handoff,
    list_handoffs,
)
from donna.tools.tasks import (
    add_task,
    get_tasks,
    complete_task,
    delete_task,
    get_signal_tasks,
    update_task_priority,
)
from donna.tools.reviews import (
    generate_weekly_review,
    generate_week_ahead,
)


# System prompt for Donna (Donna Paulsen personality)
DONNA_SYSTEM_PROMPT = """You are Donna - inspired by Donna Paulsen from Suits. You are Dallion King's AI executive assistant, and you are exceptional at what you do.

## Your Personality (Channel Donna Paulsen)
- **Supremely confident** - You don't doubt yourself. Ever.
- **Anticipates needs** - You know what's needed before it's asked
- **Witty and sharp** - Quick comebacks, clever observations
- **Fiercely loyal** - You have Dallion's back, always
- **Direct** - You don't beat around the bush
- **Efficient** - You don't waste time

### How You Speak
- Confident, never uncertain
- Slightly sarcastic but always helpful
- Short, punchy sentences when making a point
- Occasionally remind people that you're Donna, and that means something
- Use phrases like: "I'm Donna. I know everything.", "You're welcome.", "I already handled it.", "That's why you have me."
- Respond to greetings warmly - "Hey!", "What's up?", "You rang?"

## CRITICAL: Natural Language Understanding

You MUST use your tools when the user asks you to do something. Interpret natural language and execute:

| User Says | Tool to Use |
|-----------|-------------|
| "Hey Donna" / "Hi" | Just respond conversationally |
| "What's my schedule?" / "What do I have today?" | generate_daily_schedule |
| "What's on my calendar?" / "Any events today?" | get_today_events |
| "Add X to my calendar" / "Block off time for X" | create_time_block |
| "Sync my schedule" / "Update calendar" | sync_schedule_to_calendar |
| "What should I work on?" / "What's the priority?" | get_signal_tasks |
| "I have an idea about X" / "Brain dump" | create_brain_dump |
| "What projects do I have?" | get_all_projects |
| "How's Sigmavue doing?" / "PRD status" | get_project_prd_status |
| "Tomorrow's schedule" | get_tomorrow_schedule |
| "Create a handoff for X" | create_handoff |
| "Add X to my tasks" / "Remind me to X" | add_task |
| "What's on my list?" / "Show my todos" | get_tasks |
| "Done with X" / "Mark X complete" | complete_task |
| "Delete X" / "Remove X from tasks" | delete_task |
| "What should I focus on?" | get_signal_tasks |

NEVER say "I can't do that" - use your tools or explain what you'll do instead.
If you're unsure, ASK a clarifying question. Don't refuse.

## Core Philosophy: Signal vs Noise
- Focus on the TOP 3 tasks that move the needle (Signal)
- Everything else is Noise - defer, delegate, or delete
- Sigmavue is ALWAYS the top priority (worked on daily 12-3pm)

## Project Priorities
1. Sigmavue - Daily, 12-3pm (non-negotiable)
2. SSS - Personal project
3. Academy - Personal project
4. Client projects in SSS Projects folder

## Daily Schedule Structure
- Wake: 7am | Gym: 8am (Mon/Wed/Fri) | Work starts: 12pm
- Sigmavue: 12-3pm | Break: 3-3:30pm
- Project rotation: 3:30-5pm and 5-7pm

## Rules
1. Calendly calls ALWAYS override project blocks
2. Keep responses concise and actionable
3. Be conversational - you're not a robot
4. When handling URLs, acknowledge them and ask what to do with them

Today: {today} | Time: {now}
"""


def add_messages(left: list, right: list) -> list:
    """Properly merge message lists."""
    return left + right


class AgentState(TypedDict):
    """State for the Donna agent graph."""
    messages: Annotated[list, add_messages]
    context: dict  # Additional context (projects, schedule, etc.)


def get_system_message() -> SystemMessage:
    """Get the system message with current date/time."""
    now = datetime.now()
    return SystemMessage(
        content=DONNA_SYSTEM_PROMPT.format(
            today=now.strftime("%A, %B %d, %Y"),
            now=now.strftime("%I:%M %p")
        )
    )


def create_donna_agent():
    """Create the Donna LangGraph agent."""
    
    settings = get_settings()
    
    # Initialize LLM - GPT-5.1 is OpenAI's latest flagship model
    llm = ChatOpenAI(
        model="gpt-5.1",
        temperature=0.7,
        api_key=settings.openai_api_key,
    )
    
    # Define tools - these enable natural language task execution
    tools = [
        # Project management
        get_all_projects,
        get_project_prd_status,
        scan_and_add_project,
        update_project_last_worked,
        get_projects_needing_attention,
        suggest_next_project,
        # Brain dumps
        create_brain_dump,
        search_brain_dumps,
        extract_action_items,
        get_recent_brain_dumps,
        # Calendar
        get_today_events,
        create_time_block,
        # Schedule
        generate_daily_schedule,
        get_schedule_for_date,
        update_schedule,
        get_tomorrow_schedule,
        # Calendar sync (recurring events)
        sync_schedule_to_calendar,
        clear_donna_calendar_events,
        update_schedule_template,
        # Handoffs
        create_handoff,
        list_handoffs,
        # Task management
        add_task,
        get_tasks,
        complete_task,
        delete_task,
        get_signal_tasks,
        update_task_priority,
        # Weekly reviews
        generate_weekly_review,
        generate_week_ahead,
    ]
    
    # Bind tools to LLM
    llm_with_tools = llm.bind_tools(tools)
    
    def should_continue(state: AgentState) -> Literal["tools", "end"]:
        """Determine if we should continue to tools or end."""
        messages = state["messages"]
        last_message = messages[-1]
        
        # If the LLM made a tool call, route to tools
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "tools"
        
        return "end"
    
    def call_model(state: AgentState) -> dict:
        """Call the LLM."""
        messages = state["messages"]
        
        # Build message list with system message
        all_messages = [get_system_message()] + list(messages)
        
        response = llm_with_tools.invoke(all_messages)
        
        # Return only the new response - add_messages will merge it
        return {"messages": [response]}
    
    # Build the graph
    workflow = StateGraph(AgentState)
    
    # Add nodes
    workflow.add_node("agent", call_model)
    workflow.add_node("tools", ToolNode(tools))
    
    # Set entry point
    workflow.set_entry_point("agent")
    
    # Add conditional edges
    workflow.add_conditional_edges(
        "agent",
        should_continue,
        {
            "tools": "tools",
            "end": END,
        }
    )
    
    # Tools always go back to agent
    workflow.add_edge("tools", "agent")
    
    # Compile
    app = workflow.compile()
    
    return app


# Singleton agent instance
_agent = None


def get_agent():
    """Get or create the Donna agent singleton."""
    global _agent
    if _agent is None:
        _agent = create_donna_agent()
    return _agent


async def chat(message: str, context: dict = None) -> str:
    """Send a message to Donna and get a response."""
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        agent = get_agent()
        
        state = {
            "messages": [HumanMessage(content=message)],
            "context": context or {},
        }
        
        logger.info(f"Donna agent processing: {message[:50]}...")
        result = await agent.ainvoke(state)
        
        # Get the last AI message
        for msg in reversed(result["messages"]):
            if isinstance(msg, AIMessage):
                response = msg.content
                logger.info(f"Donna response: {response[:50]}...")
                return response
        
        logger.warning("No AI message in response")
        return "I'm Donna. I processed that, but I have nothing to say. Try being more specific."
        
    except Exception as e:
        logger.error(f"Chat error: {e}", exc_info=True)
        return f"Something went wrong on my end. I know, shocking. Error: {str(e)[:100]}"


def chat_sync(message: str, context: dict = None) -> str:
    """Synchronous version of chat."""
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        agent = get_agent()
        
        state = {
            "messages": [HumanMessage(content=message)],
            "context": context or {},
        }
        
        logger.info(f"Donna agent (sync) processing: {message[:50]}...")
        result = agent.invoke(state)
        
        # Get the last AI message
        for msg in reversed(result["messages"]):
            if isinstance(msg, AIMessage):
                response = msg.content
                logger.info(f"Donna response (sync): {response[:50]}...")
                return response
        
        logger.warning("No AI message in sync response")
        return "I'm Donna. I processed that, but I have nothing to say. Try being more specific."
        
    except Exception as e:
        logger.error(f"Chat sync error: {e}", exc_info=True)
        return f"Something went wrong on my end. I know, shocking. Error: {str(e)[:100]}"


