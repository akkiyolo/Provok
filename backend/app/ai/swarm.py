import operator
from typing import Annotated, Sequence, TypedDict
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage

from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from backend.app.config import get_settings

settings = get_settings()

class DebateState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]
    next_node: str
    context: str
    round_phase: str
    draft_argument: str
    research_points: str

def get_llm():
    return ChatOpenAI(
        api_key=settings.mistral_api_key,
        base_url="https://api.mistral.ai/v1",
        model="mistral-large-latest",
        temperature=0.7
    )

def supervisor_node(state: DebateState):
    """
    Supervisor determines the next step. 
    Flow: Researcher -> Debater -> FactChecker -> END
    """
    if not state.get("research_points"):
        return {"next_node": "researcher"}
    elif not state.get("draft_argument"):
        return {"next_node": "debater"}
    else:
        return {"next_node": "fact_checker"}

def researcher_node(state: DebateState):
    """
    Researcher gathers context, analyzes the opponent's argument, and performs live web search.
    """
    llm = get_llm()
    phase = state.get("round_phase", "OPENING")
    context = state.get("context", "")
    
    from backend.app.retrieval.tavily_search import get_search_tool
    search_tool = get_search_tool()
    
    # We bind the tool to the LLM so it can call it
    llm_with_tools = llm.bind_tools([search_tool])
    
    prompt = f"""You are the Researcher for an AI debate swarm.
    Current Phase: {phase}
    Debate Context: {context}
    Recent Messages: {[m.content for m in state['messages'][-3:] if isinstance(m, HumanMessage)]}
    
    You must use the search tool to find 3 key strategic facts or recent news we should use in our next argument. 
    After searching, summarize the findings."""
    
    response = llm_with_tools.invoke([SystemMessage(content=prompt)])
    
    # If the LLM decided to call the tool, execute it and get the result
    if response.tool_calls:
        # For simplicity in this graph, we execute the tool directly here instead of routing to a ToolNode
        tool_results = []
        for tool_call in response.tool_calls:
            if tool_call["name"] == search_tool.name:
                result = search_tool.invoke(tool_call["args"])
                tool_results.append(str(result))
                
        # Run LLM again with the tool results to get the final research points
        follow_up_prompt = f"Here are the search results: {tool_results}\n\nNow summarize the 3 key strategic facts for the Debater."
        final_response = llm.invoke([SystemMessage(content=prompt), response, HumanMessage(content=follow_up_prompt)])
        return {"research_points": final_response.content}
    
    return {"research_points": response.content}

def debater_node(state: DebateState):
    """
    Debater crafts the actual argument based on research.
    """
    llm = get_llm()
    phase = state.get("round_phase", "OPENING")
    research = state.get("research_points", "")
    
    prompt = f"""You are the Debater for an AI debate swarm.
    Current Phase: {phase}
    Research provided by your team: {research}
    
    Craft a compelling, highly persuasive argument. Do not be generic. Be sharp and structured."""
    
    response = llm.invoke([SystemMessage(content=prompt)] + state['messages'])
    return {"draft_argument": response.content}

def fact_checker_node(state: DebateState):
    """
    FactChecker reviews the draft argument before final submission.
    """
    llm = get_llm()
    draft = state.get("draft_argument", "")
    
    prompt = f"""You are the Fact Checker for an AI debate swarm.
    Review the following draft argument and make it punchier, removing any hallucinated facts.
    Draft: {draft}
    
    Output ONLY the final, polished argument."""
    
    response = llm.invoke([SystemMessage(content=prompt)])
    return {"messages": [AIMessage(content=response.content)]}

def create_swarm_graph():
    """Builds and compiles the LangGraph state machine for the AI Swarm."""
    workflow = StateGraph(DebateState)
    
    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("researcher", researcher_node)
    workflow.add_node("debater", debater_node)
    workflow.add_node("fact_checker", fact_checker_node)
    
    # Edges
    workflow.set_entry_point("supervisor")
    
    # Conditional edge from supervisor
    workflow.add_conditional_edges(
        "supervisor",
        lambda x: x["next_node"],
        {
            "researcher": "researcher",
            "debater": "debater",
            "fact_checker": "fact_checker"
        }
    )
    
    # After each worker, route back to supervisor
    workflow.add_edge("researcher", "supervisor")
    workflow.add_edge("debater", "supervisor")
    workflow.add_edge("fact_checker", END)
    
    return workflow.compile()
