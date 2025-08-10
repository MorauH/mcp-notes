
import os
import asyncio
from typing import Any, Dict, List, Optional
from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.types import Tool, TextContent
import logging
from aiohttp import web, WSMsgType
import aiohttp_cors
import json

from vault import Vault, ObsidianVault

from tools import ToolRegistry, MathTools, StringTools, VaultTools, LLMTools

from llm.query_llm import LLMVaultProcessor




# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create the MCP server
app = Server("vault-mcp-server")

# Global registry instance
registry = ToolRegistry()


# ============= MCP SERVER HANDLERS =============

@app.list_tools()
async def list_tools() -> List[Tool]:
    """List all available tools"""
    return registry.get_tools()


@app.call_tool()
async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
    """Call a tool by name"""
    try:
        return await registry.call_tool(name, arguments)
    except Exception as e:
        logger.error(f"Error calling tool {name}: {str(e)}")
        return [TextContent(type="text", text=f"Error: {str(e)}")]


def initialize_server(vault: Vault=None, llm_processor: LLMVaultProcessor=None):
    """Initialize the server by registering all tools"""
    logger.info("Initializing MCP server...")
    
    # Register all tool modules
    MathTools.register_all(registry=registry)
    StringTools.register_all(registry=registry)
    if vault is not None:
        VaultTools.register_all(registry=registry, vault=vault)
    if llm_processor is not None:
        LLMTools.register_all(registry=registry, llm_processor=llm_processor)
    
    logger.info(f"Server initialized with {len(registry.get_tools())} tools")
    
    # Log all registered tools
    for tool in registry.get_tools():
        logger.info(f"  - {tool.name}: {tool.description}")


# ============= HTTP SERVER HANDLERS =============

class MCPWebSocketHandler:
    """Handles WebSocket connections for MCP protocol"""
    
    def __init__(self, websocket, request, app:Server):
        self.websocket = websocket
        self.request = request
        self.app = app
        
    async def handle_connection(self):
        """Handle a WebSocket connection"""
        logger.info(f"New WebSocket connection from {self.request.remote}")
        
        try:
            # Create a custom stream adapter for WebSocket
            read_stream = WebSocketReadStream(self.websocket)
            write_stream = WebSocketWriteStream(self.websocket)
            
            # Initialize and run the MCP server session
            await self.app.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name="Vault MCP Server",
                    server_version=os.environ.get('MCP_VERSION', '1.0.0'),
                    capabilities=self.app.get_capabilities(
                        notification_options=NotificationOptions(),
                        experimental_capabilities={}
                    )
                )
            )
            
        except Exception as e:
            logger.error(f"Error in WebSocket connection: {e}", exc_info=True)
        finally:
            logger.info("WebSocket connection closed")

class WebSocketReadStream:
    """Adapter to make WebSocket work as a read stream for MCP"""
    
    def __init__(self, websocket):
        self.websocket = websocket
    
    async def readline(self):
        """Read a line from the WebSocket"""
        async for msg in self.websocket:
            if msg.type == WSMsgType.TEXT:
                return msg.data.encode() + b'\n'
            elif msg.type == WSMsgType.ERROR:
                raise Exception(f'WebSocket error: {self.websocket.exception()}')
        return b''

class WebSocketWriteStream:
    """Adapter to make WebSocket work as a write stream for MCP"""
    
    def __init__(self, websocket):
        self.websocket = websocket
        
    async def write(self, data):
        """Write data to the WebSocket"""
        if isinstance(data, bytes):
            data = data.decode().strip()
        await self.websocket.send_str(data)
        
    async def drain(self):
        """Drain the stream (no-op for WebSocket)"""
        pass

async def websocket_handler(request):
    """Handle WebSocket connections"""
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    
    handler = MCPWebSocketHandler(ws, request)
    await handler.handle_connection()
    
    return ws

async def http_list_tools(request):
    """HTTP endpoint to list tools"""
    try:
        tools = await list_tools()
        tools_data = [
            {
                "name": tool.name,
                "description": tool.description,
                "inputSchema": tool.inputSchema
            }
            for tool in tools
        ]
        return web.json_response({"tools": tools_data})
    except Exception as e:
        logger.error(f"Error listing tools: {e}")
        return web.json_response({"error": str(e)}, status=500)

async def http_call_tool(request):
    """HTTP endpoint to call a tool"""
    try:
        data = await request.json()
        tool_name = data.get("name")
        arguments = data.get("arguments", {})
        
        if not tool_name:
            return web.json_response({"error": "Tool name is required"}, status=400)
        
        result = await call_tool(tool_name, arguments)
        
        # Convert TextContent to dict for JSON serialization
        result_data = [
            {
                "type": content.type,
                "text": content.text
            }
            for content in result
        ]
        
        return web.json_response({"result": result_data})
        
    except Exception as e:
        logger.error(f"Error calling tool: {e}")
        return web.json_response({"error": str(e)}, status=500)

async def create_http_app():
    """Create the HTTP application"""
    http_app = web.Application()
    
    # Configure CORS
    cors = aiohttp_cors.setup(http_app, defaults={
        "*": aiohttp_cors.ResourceOptions(
            allow_credentials=True,
            expose_headers="*",
            allow_headers="*",
            allow_methods="*"
        )
    })
    
    # Add routes
    http_app.router.add_get('/ws', websocket_handler)
    http_app.router.add_get('/tools', http_list_tools)
    http_app.router.add_post('/tools/call', http_call_tool)
    
    # Add CORS to all routes
    for route in list(http_app.router.routes()):
        cors.add(route)
    
    # Health check endpoint
    async def health_check(request):
        return web.json_response({"status": "healthy", "server": "vault-mcp-server"})
    
    cors.add(http_app.router.add_get('/health', health_check))
    
    return http_app



async def main():
    """
    Initializes all tools and starts the HTTP server with WebSocket support.
    """
    
    # Set paths
    curr_path = os.path.dirname(os.path.abspath(__file__))
    vault_path = f"{curr_path}/../persistant/test_vault"
    relative_persistant_path = "./persistant"
    
    vault = ObsidianVault(vault_path, relative_persistant_path)
    llm_processor = LLMVaultProcessor(vault=vault)
    
    # Update the index
    num_docs = vault.update_index()
    print(f"Indexed {num_docs} new/changed documents")
    
    # Initialize MCP server
    initialize_server(vault=vault, llm_processor=llm_processor)
    
    # Create HTTP application
    http_app = await create_http_app()
    
    # Configure server settings
    host = os.environ.get('MCP_HOST', '127.0.0.1')
    port = int(os.environ.get('MCP_PORT', '8080'))
    
    logger.info(f"Starting MCP HTTP server on {host}:{port}")
    logger.info(f"WebSocket endpoint: ws://{host}:{port}/ws")
    logger.info(f"HTTP Tools endpoint: http://{host}:{port}/tools")
    logger.info(f"Health check: http://{host}:{port}/health")
    
    try:
        # Start the server
        runner = web.AppRunner(http_app)
        await runner.setup()
        
        site = web.TCPSite(runner, host, port)
        await site.start()
        
        logger.info("MCP server is running. Press Ctrl+C to stop.")
        
        # Keep the server running
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            logger.info("Server terminated by user (Ctrl+C).")
        
    except Exception as e:
        logger.error(f"An error occurred: {e}", exc_info=True)
        raise
    finally:
        logger.info("MCP server stopped.")
        if 'runner' in locals():
            await runner.cleanup()




if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Server terminated by user (Ctrl+C).")
    except Exception as e:
        logger.error(f"Server exited with an unhandled exception: {e}", exc_info=True)