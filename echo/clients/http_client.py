import os
import json
import asyncio
from typing import Dict, Any, List
from aiohttp import ClientSession
from mcp.types import Tool, TextContent

class HTTPClient:
    """Simple HTTP client for interacting with the MCP server"""
    def __init__(self, host: str = "127.0.0.1", port: int = 8080):
        self.base_url = f"http://{host}:{port}"
        self.session = None

    async def __aenter__(self):
        self.session = ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def list_tools(self) -> List[Tool]:
        """List available tools"""
        async with self.session.get(f"{self.base_url}/tools") as response:
            data = await response.json()
            return [Tool(**tool) for tool in data["tools"]]

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> List[TextContent]:
        """Call a tool by name"""
        async with self.session.post(
            f"{self.base_url}/tools/call",
            json={"name": name, "arguments": arguments}
        ) as response:
            data = await response.json()
            return [TextContent(**content) for content in data["result"]]

async def main():
    # Get host and port from environment or use defaults
    host = os.environ.get("MCP_HOST", "127.0.0.1")
    port = int(os.environ.get("MCP_PORT", "8080"))

    async with HTTPClient(host, port) as client:
        print(f"Connected to MCP server at {host}:{port}")
        
        # List available tools
        print("\nListing available tools:")
        tools = await client.list_tools()
        for tool in tools:
            print(f"- {tool.name}: {tool.description}")

        # Example tool calls
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
            }
        ]

        print("\nTesting tools:")
        for case in test_cases:
            print(f"\n{case['description']}:")
            try:
                result = await client.call_tool(case["name"], case["args"])
                print(f"Result: {result[0].text}")
            except Exception as e:
                print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
