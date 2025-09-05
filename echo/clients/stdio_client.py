import os
import sys
import json
import asyncio
from typing import Dict, Any, List, Optional
from mcp.types import Tool, TextContent

class StdioClient:
    """Simple stdio client for interacting with the MCP server"""
    
    def __init__(self):
        self.process = None
        self.request_id = 0
        self.initialized = False
    
    async def __aenter__(self):
        # Start the server process with stdio enabled
        env = os.environ.copy()
        env.update({
            'PYTHONUNBUFFERED': '1'
        })
        
        # Start the server process with stdio mode enabled
        self.process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "echo.main",
            "--stdio",  # Enable stdio mode explicitly
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env
        )

        # Start stderr reading task
        self._stderr_task = asyncio.create_task(self._read_stderr())
        
        # Give the server process a moment to start up
        await asyncio.sleep(5) 
        
        # Initialize the MCP connection
        await self._initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.process:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self.process.kill()
                await self.process.wait()
        if hasattr(self, '_stderr_task'):
            self._stderr_task.cancel()
            try:
                await self._stderr_task
            except asyncio.CancelledError:
                pass

    async def _read_stderr(self):
        """Continuously read and print stderr from the server process"""
        try:
            while True:
                line = await self.process.stderr.readline()
                if not line:
                    break
                print(f"Server: {line.decode().strip()}", file=sys.stderr)
        except asyncio.CancelledError:
            pass
    
    async def _send_request(self, method: str, params: dict = None) -> dict:
        """Send a JSON-RPC request to the stdio server and get response"""
        if not self.process:
            raise Exception("Client not connected")
            
        self.request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": method
        }
        
        if params is not None:
            request["params"] = params
        
        # Send request
        request_str = json.dumps(request) + "\n"
        print(f"Client -> Server: {request_str.strip()}", file=sys.stderr)
        
        self.process.stdin.write(request_str.encode())
        await self.process.stdin.drain()
        
        # Read response
        try:
            response_line = await asyncio.wait_for(
                self.process.stdout.readline(), 
                timeout=10.0
            )
            
            if not response_line:
                raise Exception("Server closed connection or sent empty response")
                
            response_str = response_line.decode().strip()
            print(f"Server -> Client: {response_str}", file=sys.stderr)
            
            if not response_str:
                raise Exception("Server sent empty response")
            
            try:
                response = json.loads(response_str)
            except json.JSONDecodeError as e:
                raise Exception(f"Invalid JSON response from server: {e}")
            
            # Check for JSON-RPC error
            if "error" in response:
                error = response["error"]
                error_msg = error.get('message', str(error))
                error_code = error.get('code', 'unknown')
                raise Exception(f"Server error [{error_code}]: {error_msg}")
            
            # For requests (not notifications), we expect a result
            if "id" in request and "result" not in response:
                raise Exception("Server response missing 'result' field")
                
            return response.get("result")
            
        except asyncio.TimeoutError:
            raise Exception("Timeout waiting for server response")
        except Exception as e:
            # Add context about which request failed
            raise Exception(f"Request '{method}' failed: {e}")
    
    async def _send_notification(self, method: str, params: dict = None):
        """Send a JSON-RPC notification (no response expected)"""
        if not self.process:
            raise Exception("Client not connected")
        
        notification = {
            "jsonrpc": "2.0",
            "method": method
        }
        
        if params is not None:
            notification["params"] = params
        
        # Send notification
        notification_str = json.dumps(notification) + "\n"
        print(f"Client -> Server (notification): {notification_str.strip()}", file=sys.stderr)
        
        self.process.stdin.write(notification_str.encode())
        await self.process.stdin.drain()
    
    async def _initialize(self):
        """Initialize the MCP connection following the MCP protocol sequence"""
        try:
            # Step 1: Send initialize request and wait for response
            result = await self._send_request("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {}
                },
                "clientInfo": {
                    "name": "test-client",
                    "version": "1.0.0"
                }
            })
            
            # Validate server capabilities
            if not isinstance(result, dict):
                raise Exception("Server returned invalid capabilities format")
                
            server_name = result.get("serverInfo", {}).get("name")
            server_version = result.get("serverInfo", {}).get("version")
            
            if not server_name or not server_version:
                raise Exception("Server did not provide valid server info")
                
            server_capabilities = result.get("capabilities")
            if not isinstance(server_capabilities, dict):
                raise Exception("Server did not provide valid capabilities")
            
            print(f"Connected to {server_name} v{server_version}", file=sys.stderr)
            print(f"Server capabilities: {server_capabilities}", file=sys.stderr)
            
            # Step 2: Send initialized notification (no response expected)
            await self._send_notification("initialized", {})
            
            # Step 3: Wait a brief moment to ensure server processes the notification
            await asyncio.sleep(0.1)
            
            self.initialized = True
            print("MCP connection initialized successfully", file=sys.stderr)
            
        except Exception as e:
            print(f"Failed to initialize MCP connection: {e}", file=sys.stderr)
            self.initialized = False
            raise
    
    async def list_tools(self) -> List[Tool]:
        """List available tools"""
        if not self.initialized:
            raise Exception("Client not initialized - call _initialize() first")
            
        result = await self._send_request("tools/list")
        
        if not isinstance(result, dict):
            raise Exception(f"Expected dict response for tools/list, got {type(result)}")
        
        tools = []
        tools_data = result.get("tools", [])
        
        if not isinstance(tools_data, list):
            raise Exception(f"Expected list in 'tools' field, got {type(tools_data)}")
        
        for tool_data in tools_data:
            if not isinstance(tool_data, dict):
                print(f"Warning: Skipping invalid tool data: {tool_data}", file=sys.stderr)
                continue
                
            try:
                tools.append(Tool(
                    name=tool_data["name"],
                    description=tool_data["description"],
                    inputSchema=tool_data.get("inputSchema", {})
                ))
            except KeyError as e:
                print(f"Warning: Tool missing required field {e}: {tool_data}", file=sys.stderr)
                continue
                
        return tools
    
    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> List[TextContent]:
        """Call a tool by name"""
        if not self.initialized:
            raise Exception("Client not initialized - call _initialize() first")
            
        result = await self._send_request("tools/call", {
            "name": name,
            "arguments": arguments
        })
        
        if not isinstance(result, dict):
            raise Exception(f"Expected dict response for tools/call, got {type(result)}")
        
        content_list = []
        content_data = result.get("content", [])
        
        if not isinstance(content_data, list):
            raise Exception(f"Expected list in 'content' field, got {type(content_data)}")
        
        for item in content_data:
            if not isinstance(item, dict):
                print(f"Warning: Skipping invalid content item: {item}", file=sys.stderr)
                continue
                
            try:
                content_list.append(TextContent(
                    type=item["type"],
                    text=item["text"]
                ))
            except KeyError as e:
                print(f"Warning: Content item missing required field {e}: {item}", file=sys.stderr)
                continue
                
        return content_list

async def main():
    try:
        async with StdioClient() as client:
            print("Connected to MCP server via stdio")
            
            # List available tools
            print("\nListing available tools:")
            try:
                tools = await client.list_tools()
                if not tools:
                    print("No tools available")
                    return 0
                    
                for tool in tools:
                    print(f"- {tool.name}: {tool.description}")
                    if hasattr(tool, 'inputSchema') and tool.inputSchema:
                        properties = tool.inputSchema.get('properties', {})
                        if properties:
                            params = ", ".join(properties.keys())
                            print(f"  Parameters: {params}")
            except Exception as e:
                print(f"Failed to list tools: {e}")
                return 1
            
            # Example tool calls - adjust based on your actual tools
            test_cases = [
                {
                    "name": "math.add",
                    "args": {"a": 2, "b": 3},
                    "description": "Testing math.add"
                },
                {
                    "name": "string.reverse",
                    "args": {"text": "hello"},
                    "description": "Testing string.reverse"
                },
                {
                    "name": "math.subtract",
                    "args": {"a": 10, "b": 4},
                    "description": "Testing math.subtract"
                }
            ]
            
            print("\nTesting tools:")
            available_tool_names = [tool.name for tool in tools]
            
            for case in test_cases:
                if case["name"] not in available_tool_names:
                    print(f"\nSkipping {case['name']} - not available")
                    continue
                    
                print(f"\n{case['description']}:")
                try:
                    result = await client.call_tool(case["name"], case["args"])
                    if result:
                        print(f"Result: {result[0].text}")
                    else:
                        print("No result returned")
                except Exception as e:
                    print(f"Error: {e}")
                    
    except Exception as e:
        print(f"Failed to connect to server: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)