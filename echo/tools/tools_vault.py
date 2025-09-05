
from typing import Any, Dict, List, Optional
from mcp.types import Tool, TextContent
import logging

from echo.vault import Vault
from echo.tools import ToolRegistry


logger = logging.getLogger(__name__)


class VaultTools:
    """Tools for working with the vault"""
    
    @staticmethod
    def register_all(registry: ToolRegistry, vault: Vault):
        """Register all vault tools"""

        fetch_note_paths_tool = Tool(
            name="fetch_note_paths",
            description="Fetch a list of notes relative paths from the database",
            inputSchema={
                "type": "object",
                "properties": { 
                    # TODO: additional instructions required for available SQL columns
                    # "where_clause": {"type": "string", "description": "Optional SQL WHERE clause to filter the results"},
                    # "where_args": {"type": "array", "items": {"type": "string"}, "description": "Arguments to be used in the WHERE clause"}
                }
            }
        )
        registry.register_tool(fetch_note_paths_tool, lambda arguments: VaultTools.fetch_note_paths(vault, arguments))

        vector_query_tool = Tool(
            name="vector_query",
            description="Query the vault using a vector",
            inputSchema={
                "type": "object",
                "properties": {
                    "query_text": {"type": "string", "description": "Query text"},
                    "top_k": {"type": "integer", "description": "Number of results to return"}
                },
                "required": ["query_text"]
            }
        )
        registry.register_tool(vector_query_tool, lambda arguments: VaultTools.vector_query(vault, arguments))

        get_note_content_tool = Tool(
            name="get_note_content",
            description="Get the content of a note",
            inputSchema={
                "type": "object",
                "properties": {
                    "note_path": {"type": "string", "description": "Relative path to the note"}
                },
                "required": ["note_path"]
            }
        )
        registry.register_tool(get_note_content_tool, lambda arguments: VaultTools.get_note_content(vault, arguments))

        save_note_tool = Tool(
            name="save_note",
            description="Save content to a note",
            inputSchema={
                "type": "object",
                "properties": {
                    "note_path": {"type": "string", "description": "Relative path to the note"},
                    "content": {"type": "string", "description": "Content to save"}
                },
                "required": ["note_path", "content"]
            }
        )
        registry.register_tool(save_note_tool, lambda arguments: VaultTools.save_note(vault, arguments))

        create_new_note_tool = Tool(
            name="create_new_note",
            description="Create a new note in the vault",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Title of the note"},
                    "content": {"type": "string", "description": "Content of the note"},
                    "folder": {"type": "string", "description": "Folder to create the note in"}
                },
                "required": ["title", "content"]
            }
        )
        registry.register_tool(create_new_note_tool, lambda arguments: VaultTools.create_new_note(vault, arguments))

        remove_note_tool = Tool(
            name="remove_note",
            description="Remove a note from the vault",
            inputSchema={
                "type": "object",
                "properties": {
                    "note_path": {"type": "string", "description": "Relative path to the note"}
                },
                "required": ["note_path"]
            }
        )
        registry.register_tool(remove_note_tool, lambda arguments: VaultTools.remove_note(vault, arguments))


    @staticmethod
    async def fetch_note_paths(vault: Vault, arguments: Dict[str, Any]) -> List[TextContent]:
        """Fetch a list of note paths from the database based on an optional WHERE clause"""

        result = vault.fetch_note_paths(**arguments)
        result = [TextContent(type="text", text=str(item)) for item in result]

        return result

    @staticmethod
    async def vector_query(vault: Vault, arguments: Dict[str, Any]) -> List[TextContent]:
        """Query the vault using a vector"""

        result = vault.vector_query(**arguments)
        result = [TextContent(type="text", text=str(item)) for item in result]

        return result
    
    @staticmethod
    async def get_note_content(vault: Vault, arguments: Dict[str, Any]) -> List[TextContent]:
        """Get the content of a note"""

        result = vault.get_note_content(**arguments)

        return f"Note content: {result}"
    
    @staticmethod
    async def save_note(vault: Vault, arguments: Dict[str, Any]) -> List[TextContent]:
        """Save content to a note"""

        vault.save_note(**arguments)
        return "Note saved"
    
    @staticmethod
    async def create_new_note(vault: Vault, arguments: Dict[str, Any]) -> List[TextContent]:
        """Create a new note in the vault"""

        note_path = vault.create_new_note(**arguments)
        return f"Note created at: {note_path}"
    
    @staticmethod
    async def remove_note(vault: Vault, arguments: Dict[str, Any]) -> List[TextContent]:
        """Remove a note from the vault"""

        vault.remove_note(**arguments)
        return "Note removed"
    