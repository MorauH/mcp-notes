import os
import logging
import json
from typing import Any, Dict, Optional
import time
import asyncio

from aiohttp import web, WSMsgType
import aiohttp_cors
from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions

from echo.server.mcp_server import VaultMCPServer

logger = logging.getLogger(__name__)


class WebSocketReadStream:
    """Adapter to make an aiohttp WebSocket work as a read stream for MCP."""

    def __init__(self, websocket: web.WebSocketResponse):
        self.websocket = websocket

    async def readline(self) -> bytes:
        """Read a line from the WebSocket, appending a newline for the protocol."""
        async for msg in self.websocket:
            if msg.type == WSMsgType.TEXT:
                # The MCP protocol expects newline-terminated JSON
                return msg.data.encode('utf-8') + b'\n'
            elif msg.type == WSMsgType.ERROR:
                raise ConnectionError(f'WebSocket error: {self.websocket.exception()}')
        return b''


class WebSocketWriteStream:
    """Adapter to make an aiohttp WebSocket work as a write stream for MCP."""

    def __init__(self, websocket: web.WebSocketResponse):
        self.websocket = websocket

    async def write(self, data: bytes):
        """Write data to the WebSocket, stripping the newline."""
        if isinstance(data, bytes):
            # The MCP protocol handler adds a newline, which we must remove for WebSocket messages
            data = data.decode('utf-8').rstrip('\n')
        await self.websocket.send_str(data)

    async def drain(self):
        """Drain is a no-op for aiohttp WebSockets."""
        pass


class MCPWebSocketHandler:
    """Handles the lifecycle of a single WebSocket connection for the MCP protocol."""

    def __init__(self, websocket: web.WebSocketResponse, mcp_server: Server):
        self.websocket = websocket
        self.mcp_server = mcp_server

    async def handle_connection(self):
        """Run an MCP server session over the WebSocket connection."""
        logger.info(f"New WebSocket connection established.")
        try:
            read_stream = WebSocketReadStream(self.websocket)
            write_stream = WebSocketWriteStream(self.websocket)
            
            # The mcp_server.run method processes messages over the provided streams
            await self.mcp_server.run(read_stream, write_stream)
            
        except Exception as e:
            logger.error(f"Error during WebSocket session: {e}", exc_info=True)
        finally:
            logger.info("WebSocket connection closed.")


class JSONRPCHandler:
    """Handles stateless JSON-RPC 2.0 requests over HTTP for the MCP protocol."""

    def __init__(self, vault_mcp_server: VaultMCPServer, session_id: str):
        self.vault_mcp_server = vault_mcp_server
        self.mcp_server = vault_mcp_server.get_server()
        self.initialized = False
        self.session_id = session_id
        self.created_at = time.time()
        self.last_used = time.time()

    def touch(self):
        """Update last used timestamp"""
        self.last_used = time.time()

    async def handle_request(self, request_data: Dict) -> Optional[Dict]:
        """Process a single JSON-RPC request and return a response."""
        self.touch()  # Update last used timestamp
        
        method = request_data.get("method")
        params = request_data.get("params", {})
        request_id = request_data.get("id")

        logger.info(f"[{self.session_id}] Handling method: {method}")

        if not method:
            return self._create_error(request_id, -32600, "Invalid Request", "Method not specified.")

        # Route the request to the appropriate handler method
        handler_method = getattr(self, f"_handle_{method.replace('/', '_')}", self._handle_not_found)
        return await handler_method(request_id, params)

    async def _handle_initialize(self, request_id: int, params: Dict) -> Dict:
        logger.info(f"[{self.session_id}] Initializing...")
        server_info = {
            "name": "vault-mcp-server",
            "version": os.environ.get('MCP_VERSION', '1.0.0')
        }
        capabilities = self.mcp_server.get_capabilities(notification_options=NotificationOptions(),experimental_capabilities={}).dict()
        return self._create_success(request_id, {"serverInfo": server_info, "capabilities": capabilities})

    async def _handle_notifications_initialized(self, request_id: Optional[int], params: Dict) -> None:
        # This is a notification, so it has no response
        self.initialized = True
        logger.info(f"[{self.session_id}] Client signaled initialized.")
        return None

    async def _handle_tools_list(self, request_id: int, params: Dict) -> Dict:
        logger.info(f"[{self.session_id}] Listing tools, initialized: {self.initialized}")
        if not self.initialized:
            return self._create_error(request_id, -32002, "Server Not Initialized")
        
        tools = self.vault_mcp_server.list_tools()
        tools_data = [{
            "name": tool.name,
            "description": tool.description,
            "inputSchema": getattr(tool, 'inputSchema', None)
        } for tool in tools]
        return self._create_success(request_id, {"tools": tools_data})

    async def _handle_tools_call(self, request_id: int, params: Dict) -> Dict:
        logger.info(f"[{self.session_id}] Calling tool, initialized: {self.initialized}")
        if not self.initialized:
            return self._create_error(request_id, -32002, "Server Not Initialized")
            
        tool_name = params.get("name")
        if not tool_name:
            return self._create_error(request_id, -32602, "Invalid Params", "Tool name is required.")

        arguments = params.get("arguments", {})
        logger.info(f"[{self.session_id}] Calling tool {tool_name} with args: {arguments}")
        
        try:
            result = await self.vault_mcp_server.call_tool(tool_name, arguments)
            result_data = [{"type": content.type, "text": content.text} for content in result]
            logger.info(f"[{self.session_id}] Tool call successful, result: {result_data}")
            return self._create_success(request_id, {"content": result_data})
        except Exception as e:
            logger.error(f"[{self.session_id}] Tool call failed: {e}", exc_info=True)
            return self._create_error(request_id, -32603, "Internal error", str(e))

    async def _handle_not_found(self, request_id: int, params: Dict) -> Dict:
        method = params.get("method", "unknown")
        return self._create_error(request_id, -32601, "Method Not Found", f"The method '{method}' does not exist.")
    
    # --- JSON-RPC Response Helpers ---
    def _create_success(self, req_id: int, result: Any) -> Dict:
        return {"jsonrpc": "2.0", "id": req_id, "result": result}

    def _create_error(self, req_id: Optional[int], code: int, message: str, data: Any = None) -> Dict:
        error_obj = {"code": code, "message": message}
        if data:
            error_obj["data"] = data
        return {"jsonrpc": "2.0", "id": req_id, "error": error_obj}


class ClientSession:
    """Represents a client session for stateful interactions."""

    def __init__(self, session_id: str, vault_mcp_server: VaultMCPServer):
        self.session_id = session_id
        self.rpc_handler = JSONRPCHandler(vault_mcp_server, session_id)
        self.created_at = time.time()

    def is_initialized(self) -> bool:
        return self.rpc_handler.initialized
    
    def touch(self):
        """Update last used timestamp"""
        self.rpc_handler.touch()

    def is_expired(self, timeout_seconds: int = 3600) -> bool:
        """Check if session has expired (default 1 hour)"""
        return (time.time() - self.rpc_handler.last_used) > timeout_seconds


class MCPHttpServer:
    """HTTP server that provides MCP endpoints using aiohttp."""

    def __init__(self, vault_mcp_server: VaultMCPServer):
        self.vault_mcp_server = vault_mcp_server
        self.mcp_server = vault_mcp_server.get_server()
        self.app = None
        self.client_sessions: Dict[str, ClientSession] = {}
        self._cleanup_task = None

    async def _cleanup_expired_sessions(self):
        """Periodically clean up expired sessions"""
        while True:
            try:
                await asyncio.sleep(300)  # Check every 5 minutes
                expired_sessions = [
                    session_id for session_id, session in self.client_sessions.items()
                    if session.is_expired()
                ]
                for session_id in expired_sessions:
                    logger.info(f"Cleaning up expired session: {session_id}")
                    del self.client_sessions[session_id]
            except Exception as e:
                logger.error(f"Error during session cleanup: {e}")

    async def websocket_handler(self, request: web.Request) -> web.WebSocketResponse:
        """Handle WebSocket connections."""
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        
        handler = MCPWebSocketHandler(ws, self.mcp_server)
        await handler.handle_connection()
        return ws

    async def jsonrpc_handler(self, request: web.Request) -> web.Response:
        """Handle JSON-RPC requests."""
        try:
            data = await request.json()
            session_id = request.headers.get('X-Session-ID')
            
            logger.info(f"Received request with session_id: {session_id}, method: {data.get('method')}")
            
            # Handle session management
            if session_id:
                # Existing session
                if session_id not in self.client_sessions:
                    logger.warning(f"Session {session_id} not found, creating new one")
                    # Create new session instead of failing
                    self.client_sessions[session_id] = ClientSession(session_id, self.vault_mcp_server)
                
                session = self.client_sessions[session_id]
                session.touch()  # Update last used timestamp
                handler = session.rpc_handler
                
            else:
                # New session
                session_id = os.urandom(16).hex()
                logger.info(f"Creating new session: {session_id}")
                session = ClientSession(session_id, self.vault_mcp_server)
                self.client_sessions[session_id] = session
                handler = session.rpc_handler

            # Process the request
            response = await handler.handle_request(data)
            
            if response is None:
                # For notifications, which don't have a response body
                return web.Response(status=204, headers={'X-Session-ID': session_id})
            
            json_response = web.json_response(response)
            json_response.headers['X-Session-ID'] = session_id
            logger.info(f"Returning response with session_id: {session_id}")
            return json_response

        except json.JSONDecodeError:
            return web.json_response({
                "jsonrpc": "2.0", "id": None, 
                "error": {"code": -32700, "message": "Parse error"}
            }, status=400)
        except Exception as e:
            logger.error(f"Unhandled error in JSON-RPC handler: {e}", exc_info=True)
            return web.json_response({
                "jsonrpc": "2.0", "id": None,
                "error": {"code": -32603, "message": "Internal error", "data": str(e)}
            }, status=500)

    async def health_check(self, request: web.Request) -> web.Response:
        """Health check endpoint."""
        return web.json_response({
            "status": "healthy", 
            "server": "vault-mcp-server",
            "active_sessions": len(self.client_sessions)
        })

    async def create_app(self) -> web.Application:
        """Create and configure the aiohttp web application."""
        self.app = web.Application()
        
        cors = aiohttp_cors.setup(self.app, defaults={
            "*": aiohttp_cors.ResourceOptions(
                allow_credentials=True, expose_headers="*", allow_headers="*", allow_methods="*"
            )
        })

        self.app.router.add_get('/ws', self.websocket_handler)
        self.app.router.add_post('/mcp', self.jsonrpc_handler)
        self.app.router.add_get('/health', self.health_check)

        for route in self.app.router.routes():
            cors.add(route)
            
        return self.app

    async def start_server(self, host: str = '127.0.0.1', port: int = 8080) -> web.AppRunner:
        """Initializes and starts the HTTP server."""
        await self.create_app()
        
        # Start session cleanup task
        self._cleanup_task = asyncio.create_task(self._cleanup_expired_sessions())
        
        logger.info(f"Starting MCP HTTP server on {host}:{port}")
        logger.info(f"WebSocket endpoint: ws://{host}:{port}/ws")
        logger.info(f"JSON-RPC endpoint: http://{host}:{port}/mcp")
        logger.info(f"Health check: http://{host}:{port}/health")

        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, host, port)
        await site.start()
        
        return runner

    async def cleanup(self):
        """Clean up resources"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
