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
    from langchain_google_genai import ChatGoogleGenerativeAI
    return ChatGoogleGenerativeAI(
        api_key=settings.google_api_key,
        model="gemini-3.5-flash",
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
    
    # Mistral requires the last message to be a HumanMessage
    response = llm_with_tools.invoke([HumanMessage(content=prompt)])
    
    # If the LLM decided to call the tool, execute it and get the result
    if response.tool_calls:
        # We must respond with a ToolMessage immediately after an AIMessage with tool_calls
        messages_to_send = [HumanMessage(content=prompt), response]
        
        for tool_call in response.tool_calls:
            if tool_call["name"] == search_tool.name:
                result = search_tool.invoke(tool_call["args"])
                from langchain_core.messages import ToolMessage
                messages_to_send.append(
                    ToolMessage(
                        content=str(result),
                        tool_call_id=tool_call["id"]
                    )
                )
                
        # Ask for the summary as a follow-up human message
        messages_to_send.append(HumanMessage(content="Now summarize the 3 key strategic facts for the Debater based on the tool results above."))
        final_response = llm.invoke(messages_to_send)
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
    
    Craft a compelling, highly persuasive argument. Do not be generic. Be sharp and structured.
    CRITICAL: DO NOT use any markdown formatting whatsoever. Do not use asterisks (*), hashtags (#), or any other formatting characters. Output plain text only."""
    
    # If there are no messages, or if the last message is an AIMessage, ensure we end with a HumanMessage
    messages_to_send = list(state.get('messages', []))
    messages_to_send.append(HumanMessage(content=prompt))
    
    response = llm.invoke(messages_to_send)
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
    
    Output ONLY the final, polished argument. 
    CRITICAL: DO NOT use any markdown formatting whatsoever. Do not use asterisks (*), hashtags (#), or any other formatting characters. Output plain text only."""
    
    response = llm.invoke([HumanMessage(content=prompt)])
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
