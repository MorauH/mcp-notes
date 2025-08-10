import os
import logging
from typing import Any, Dict
from aiohttp import web, WSMsgType
import aiohttp_cors
from mcp.server import Server
from mcp.server.models import InitializationOptions
from mcp.server import NotificationOptions

logger = logging.getLogger(__name__)


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


class MCPWebSocketHandler:
    """Handles WebSocket connections for MCP protocol"""
    
    def __init__(self, websocket, request, mcp_server: Server):
        self.websocket = websocket
        self.request = request
        self.mcp_server = mcp_server
        
    async def handle_connection(self):
        """Handle a WebSocket connection"""
        logger.info(f"New WebSocket connection from {self.request.remote}")
        
        try:
            # Create a custom stream adapter for WebSocket
            read_stream = WebSocketReadStream(self.websocket)
            write_stream = WebSocketWriteStream(self.websocket)
            
            # Initialize and run the MCP server session
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
            logger.error(f"Error in WebSocket connection: {e}", exc_info=True)
        finally:
            logger.info("WebSocket connection closed")


class MCPHttpServer:
    """HTTP server with WebSocket support for MCP protocol"""
    
    def __init__(self, mcp_server: Server):
        self.mcp_server = mcp_server
        self.app = None
        
    async def websocket_handler(self, request):
        """Handle WebSocket connections"""
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        
        handler = MCPWebSocketHandler(ws, request, self.mcp_server)
        await handler.handle_connection()
        
        return ws

    async def http_list_tools(self, request):
        """HTTP endpoint to list tools"""
        try:
            tools = await self.mcp_server.list_tools()
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

    async def http_call_tool(self, request):
        """HTTP endpoint to call a tool"""
        try:
            data = await request.json()
            tool_name = data.get("name")
            arguments = data.get("arguments", {})
            
            if not tool_name:
                return web.json_response({"error": "Tool name is required"}, status=400)
            
            result = await self.mcp_server.call_tool(tool_name, arguments)
            
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

    async def health_check(self, request):
        """Health check endpoint"""
        return web.json_response({"status": "healthy", "server": "vault-mcp-server"})

    async def create_app(self):
        """Create the HTTP application"""
        self.app = web.Application()
        
        # Configure CORS
        cors = aiohttp_cors.setup(self.app, defaults={
            "*": aiohttp_cors.ResourceOptions(
                allow_credentials=True,
                expose_headers="*",
                allow_headers="*",
                allow_methods="*"
            )
        })
        
        # Add routes
        self.app.router.add_get('/ws', self.websocket_handler)
        self.app.router.add_get('/tools', self.http_list_tools)
        self.app.router.add_post('/tools/call', self.http_call_tool)
        self.app.router.add_get('/health', self.health_check)
        
        # Add CORS to all routes
        for route in list(self.app.router.routes()):
            cors.add(route)
        
        return self.app

    async def start_server(self, host='127.0.0.1', port=8080):
        """Start the HTTP server"""
        await self.create_app()
        
        logger.info(f"Starting MCP HTTP server on {host}:{port}")
        logger.info(f"WebSocket endpoint: ws://{host}:{port}/ws")
        logger.info(f"HTTP Tools endpoint: http://{host}:{port}/tools")
        logger.info(f"Health check: http://{host}:{port}/health")
        
        runner = web.AppRunner(self.app)
        await runner.setup()
        
        site = web.TCPSite(runner, host, port)
        await site.start()
        
        return runner