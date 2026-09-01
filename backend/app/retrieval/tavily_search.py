"""Tavily search integration for RAG tools."""
import os
import logging
from langchain_tavily import TavilySearch
from backend.app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

def get_search_tool() -> TavilySearch:
    """Initialize and return the Tavily Search tool."""
    # Ensure environment variable is set for LangChain
    if not os.environ.get("TAVILY_API_KEY") and settings.search_api_key:
        os.environ["TAVILY_API_KEY"] = settings.search_api_key
        
    try:
        tool = TavilySearch(
            max_results=settings.max_search_results,
            search_depth="advanced",
            include_answer=True,
            include_raw_content=False,
            include_images=False,
        )
        return tool
    except Exception as e:
        logger.error(f"Failed to initialize Tavily search tool: {e}")
        # Fallback to a dummy tool if initialization fails
        from langchain_core.tools import tool
        
        @tool
        def dummy_search(query: str) -> str:
            """Dummy search tool when Tavily fails to initialize."""
            return "Search is currently unavailable."
            
        return dummy_search
