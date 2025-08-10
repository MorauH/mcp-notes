from typing import Any, Dict, List
from mcp.types import Tool, TextContent
import logging

logger = logging.getLogger(__name__)

class ToolRegistry:
    """Registry for managing tools in a modular way"""
    
    def __init__(self):
        self.tools: Dict[str, Tool] = {}
        self.handlers: Dict[str, callable] = {}
    
    def register_tool(self, tool: Tool, handler: callable):
        """Register a tool with its handler"""
        self.tools[tool.name] = tool
        self.handlers[tool.name] = handler
        logger.info(f"Registered tool: {tool.name}")
    
    def get_tools(self) -> List[Tool]:
        """Get all registered tools"""
        return list(self.tools.values())
    
    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> List[TextContent]:
        """Call a tool by name"""
        if name not in self.handlers:
            raise ValueError(f"Unknown tool: {name}")
        
        handler = self.handlers[name]
        result = await handler(arguments)
        
        # Ensure result is always a list of TextContent
        if isinstance(result, str):
            return [TextContent(type="text", text=result)]
        elif isinstance(result, list):
            return result
        else:
            return [TextContent(type="text", text=str(result))]