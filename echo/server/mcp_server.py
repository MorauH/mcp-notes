import logging
from typing import Any, Dict, List
from mcp.server import Server
from mcp.types import Tool, TextContent

from vault import Vault
from tools import ToolRegistry, MathTools, StringTools, VaultTools, LLMTools

from llm.query_llm import LLMVaultProcessor

logger = logging.getLogger(__name__)


class VaultMCPServer:
    """Main MCP server class that handles tool registration and execution"""
    
    def __init__(self, vault: Vault = None, llm_processor: LLMVaultProcessor = None):
        self.vault = vault
        self.llm_processor = llm_processor
        self.registry = ToolRegistry()
        self.mcp_server = Server("vault-mcp-server")
        
        self._setup_handlers()
        self._initialize_tools()
    
    def _setup_handlers(self):
        """Set up MCP server handlers"""
        
        @self.mcp_server.list_tools()
        async def list_tools() -> List[Tool]:
            """List all available tools"""
            return self.registry.get_tools()

        @self.mcp_server.call_tool()
        async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
            """Call a tool by name"""
            try:
                return await self.registry.call_tool(name, arguments)
            except Exception as e:
                logger.error(f"Error calling tool {name}: {str(e)}")
                return [TextContent(type="text", text=f"Error: {str(e)}")]
    
    def _initialize_tools(self):
        """Initialize all tools by registering them with the registry"""
        logger.info("Initializing MCP server tools...")
        
        # Register core tools
        MathTools.register_all(registry=self.registry)
        StringTools.register_all(registry=self.registry)
        
        # Register vault tools if available
        if self.vault is not None:
            VaultTools.register_all(registry=self.registry, vault=self.vault)
            
        # Register LLM tools if available
        if self.llm_processor is not None:
            LLMTools.register_all(registry=self.registry, llm_processor=self.llm_processor)
        
        logger.info(f"Server initialized with {len(self.registry.get_tools())} tools")
        
        # Log all registered tools
        for tool in self.registry.get_tools():
            logger.info(f"  - {tool.name}: {tool.description}")
    
    def get_server(self) -> Server:
        """Get the underlying MCP server instance"""
        return self.mcp_server
    
    async def list_tools(self) -> List[Tool]:
        """List all available tools (convenience method)"""
        return self.registry.get_tools()
    
    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> List[TextContent]:
        """Call a tool by name (convenience method)"""
        try:
            return await self.registry.call_tool(name, arguments)
        except Exception as e:
            logger.error(f"Error calling tool {name}: {str(e)}")
            return [TextContent(type="text", text=f"Error: {str(e)}")]