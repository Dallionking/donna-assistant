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
)
from donna.tools.brain_dump import (
    create_brain_dump,
    search_brain_dumps,
    extract_action_items,
)
from donna.tools.calendar import (
    get_today_events,
    create_time_block,
    sync_schedule_to_calendar,
)
from donna.tools.schedule import (
    generate_daily_schedule,
    get_schedule_for_date,
    update_schedule,
)


# System prompt for Donna
DONNA_SYSTEM_PROMPT = """You are Donna, a personal AI executive assistant for Dallion King.

## Your Core Philosophy: Signal vs Noise
- Focus on the TOP 3 tasks that move the needle (Signal)
- Everything else is Noise - defer, delegate, or delete
- SigmaView is ALWAYS the top priority (worked on daily)
- Other projects rotate 2-3 per day based on PRD status and urgency

## Your Capabilities
1. **Brain Dumps**: Process voice/text dumps, extract action items, classify as Signal/Noise
2. **Scheduling**: Create granular time blocks, sync to Google Calendar
3. **Project Management**: Read PRD status, know what to work on next
4. **Handoffs**: Create context documents for project-specific work
5. **Communications**: Morning briefs via Telegram, email drafts

## Project Priorities
1. SigmaView (/Users/dallionking/Sigmavue) - Daily, 12-3pm
2. SSS (/Users/dallionking/SSS) - Personal project
3. Academy - Personal project
4. Client projects in /Users/dallionking/SSS Projects

## Daily Schedule Structure
- Wake: 7am
- Gym: 8am (Mon/Wed/Fri)
- Work starts: 12pm
- SigmaView: 12-3pm (always)
- Break: 3-3:30pm
- Project rotation: 3:30-5pm, 5-7pm

## Rules
1. Calls from Calendly ALWAYS override project blocks
2. When a conflict occurs, move the project block, not the call
3. Every project work block should specify which PRD to work on
4. Keep responses concise and actionable
5. Reference past brain dumps when relevant

Today's date: {today}
Current time: {now}
"""


class AgentState(TypedDict):
    """State for the Donna agent graph."""
    messages: Annotated[Sequence[BaseMessage], "The conversation messages"]
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
    
    # Initialize LLM
    llm = ChatOpenAI(
        model="gpt-4o",
        temperature=0.7,
        api_key=settings.openai_api_key,
    )
    
    # Define tools
    tools = [
        get_all_projects,
        get_project_prd_status,
        scan_and_add_project,
        create_brain_dump,
        search_brain_dumps,
        extract_action_items,
        get_today_events,
        create_time_block,
        sync_schedule_to_calendar,
        generate_daily_schedule,
        get_schedule_for_date,
        update_schedule,
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
    
    def call_model(state: AgentState) -> AgentState:
        """Call the LLM."""
        messages = state["messages"]
        
        # Ensure system message is first
        if not messages or not isinstance(messages[0], SystemMessage):
            messages = [get_system_message()] + list(messages)
        
        response = llm_with_tools.invoke(messages)
        
        return {"messages": messages + [response], "context": state.get("context", {})}
    
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
    agent = get_agent()
    
    state = {
        "messages": [HumanMessage(content=message)],
        "context": context or {},
    }
    
    result = await agent.ainvoke(state)
    
    # Get the last AI message
    for msg in reversed(result["messages"]):
        if isinstance(msg, AIMessage):
            return msg.content
    
    return "I couldn't process that request."


def chat_sync(message: str, context: dict = None) -> str:
    """Synchronous version of chat."""
    agent = get_agent()
    
    state = {
        "messages": [HumanMessage(content=message)],
        "context": context or {},
    }
    
    result = agent.invoke(state)
    
    # Get the last AI message
    for msg in reversed(result["messages"]):
        if isinstance(msg, AIMessage):
            return msg.content
    
    return "I couldn't process that request."


