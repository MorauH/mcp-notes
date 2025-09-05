import os
import sys
import logging
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.server.models import InitializationOptions
from mcp.server import NotificationOptions

logger = logging.getLogger(__name__)

class LoggedStream:
    def __init__(self, stream, name):
        self.stream = stream
        self.name = name

    async def readline(self):
        data = await self.stream.readline()
        if data:
            logger.info(f"{self.name} READ: {data.decode().strip()}")
        return data

    async def write(self, data):
        if data:
            logger.info(f"{self.name} WRITE: {data.decode().strip()}")
        await self.stream.write(data)
        
    async def drain(self):
        await self.stream.drain()

class AsyncStdinReader:
    """Async wrapper for stdin"""
    def __init__(self):
        self._buffer = bytearray()

    async def readline(self):
        while b'\n' not in self._buffer:
            chunk = sys.stdin.buffer.read1(1024)  # Non-blocking read
            if not chunk:
                break
            self._buffer.extend(chunk)
        
        if b'\n' in self._buffer:
            line, remaining = self._buffer.split(b'\n', 1)
            self._buffer = remaining
            return line + b'\n'
        elif self._buffer:
            line = bytes(self._buffer)
            self._buffer.clear()
            return line
        return b''

class AsyncStdoutWriter:
    """Async wrapper for stdout"""
    async def write(self, data):
        sys.stdout.buffer.write(data)
        sys.stdout.buffer.flush()
    
    async def drain(self):
        sys.stdout.buffer.flush()

class MCPStdioServer:
    """stdio server for MCP protocol"""
    
    def __init__(self, mcp_server: Server):
        self.mcp_server = mcp_server
    
    async def start_server(self):
        """Start the stdio server"""
        logger.info("Starting MCP stdio server...")
        
        try:
            # Create async wrappers for stdin/stdout
            stdin_reader = AsyncStdinReader()
            stdout_writer = AsyncStdoutWriter()
            
            await self.mcp_server.run(
                stdin_reader,
                stdout_writer,
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