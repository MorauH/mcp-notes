
from typing import Any, Dict, List, Optional
from mcp.types import Tool, TextContent
import logging

from echo.tools import ToolRegistry
from echo.llm.query_llm import LLMVaultProcessor


logger = logging.getLogger(__name__)


class LLMTools:
    """Tools for working with the vault"""
    
    @staticmethod
    def register_all(registry: ToolRegistry, llm_processor: LLMVaultProcessor):
        """Register all llm-powered tools"""

        summarize_topic_from_notes_tool = Tool(
            name="summarize_topic_from_notes",
            description="Summarize a topic from a list of notes. Save the summary to a new note.",
            inputSchema={
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "Topic to summarize"},
                    "include_extended_context": {"type": "boolean", "description": "Include LLM generated context, not present in original notes"},
                    "output_folder": {"type": "string", "description": "Folder to save summary note in"}
                },
                "required": ["topic"]
            }
        )
        registry.register_tool(summarize_topic_from_notes_tool, lambda arguments: LLMTools.summarize_topic_from_notes(llm_processor, arguments))


    @staticmethod
    async def summarize_topic_from_notes(llm_processor: LLMVaultProcessor, arguments: Dict[str, Any]) -> List[TextContent]:
        """Summarize a topic from a list of notes. Save the summary to a new note."""

        result = llm_processor.summarize_topic_from_notes(**arguments)
        return f"Summary created at: {result}"
