import logging
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.server.models import InitializationOptions
from mcp.server import NotificationOptions
import os

logger = logging.getLogger(__name__)

class MCPStdioServer:
    """stdio server for MCP protocol"""
    
    def __init__(self, mcp_server: Server):
        self.mcp_server = mcp_server
    
    async def start_server(self):
        """Start the stdio server"""
        logger.info("Starting MCP stdio server...")
        
        try:
            async with stdio_server() as (read_stream, write_stream):
                logger.info("MCP stdio server running and awaiting client connections...")
                
                await self.mcp_server.run(
                    read_stream,
                    write_stream,
                    InitializationOptions(
                        server_name="Vault MCP Server",
                        server_version=os.environ.get('MCP_VERSION', '1.0.0'),
                        capabilities=self.mcp_server.get_capabilities(
                            notification_options=NotificationOptions(),
                            experimental_capabilities={}
                        )
                    )
                )
        except Exception as e:
            logger.error(f"An error occurred within stdio_server context: {e}", exc_info=True)
            raise