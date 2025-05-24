
import os
import asyncio
from typing import Any, Dict, List, Optional
from mcp.server import Server, NotificationOptions
from mcp.server.stdio import stdio_server
from mcp.server.models import InitializationOptions
from mcp.types import Tool, TextContent
import logging

from vault import Vault
from vault_obsidian import ObsidianVault
from tools_registry import ToolRegistry
from tools_vault import VaultTools
from query_llm import LLMVaultProcessor
from tools_llm import LLMTools




# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create the MCP server
app = Server("vault-mcp-server")

# Global registry instance
registry = ToolRegistry()


# ============= RELATED TOOL MODULES =============

class MathTools:
    """Mathematical operations tools"""
    
    @staticmethod
    def register_all():
        """Register all math tools"""
        
        # Addition tool
        add_tool = Tool(
            name="add",
            description="Add two numbers together",
            inputSchema={
                "type": "object",
                "properties": {
                    "a": {"type": "number", "description": "First number to add"},
                    "b": {"type": "number", "description": "Second number to add"}
                },
                "required": ["a", "b"]
            }
        )
        registry.register_tool(add_tool, MathTools.add)
        
        # Multiplication tool
        multiply_tool = Tool(
            name="multiply",
            description="Multiply two numbers",
            inputSchema={
                "type": "object",
                "properties": {
                    "a": {"type": "number", "description": "First number"},
                    "b": {"type": "number", "description": "Second number"}
                },
                "required": ["a", "b"]
            }
        )
        registry.register_tool(multiply_tool, MathTools.multiply)
        
        # Power tool
        power_tool = Tool(
            name="power",
            description="Raise a number to a power",
            inputSchema={
                "type": "object",
                "properties": {
                    "base": {"type": "number", "description": "Base number"},
                    "exponent": {"type": "number", "description": "Exponent"}
                },
                "required": ["base", "exponent"]
            }
        )
        registry.register_tool(power_tool, MathTools.power)
        
        # Factorial tool
        factorial_tool = Tool(
            name="factorial",
            description="Calculate factorial of a positive integer",
            inputSchema={
                "type": "object",
                "properties": {
                    "n": {"type": "integer", "description": "Positive integer", "minimum": 0, "maximum": 20}
                },
                "required": ["n"]
            }
        )
        registry.register_tool(factorial_tool, MathTools.factorial)
    
    @staticmethod
    async def add(arguments: Dict[str, Any]) -> str:
        """Add two numbers"""
        a = float(arguments["a"])
        b = float(arguments["b"])
        result = a + b
        return f"The sum of {a} and {b} is {result}"
    
    @staticmethod
    async def multiply(arguments: Dict[str, Any]) -> str:
        """Multiply two numbers"""
        a = float(arguments["a"])
        b = float(arguments["b"])
        result = a * b
        return f"The product of {a} and {b} is {result}"
    
    @staticmethod
    async def power(arguments: Dict[str, Any]) -> str:
        """Calculate power"""
        base = float(arguments["base"])
        exponent = float(arguments["exponent"])
        result = base ** exponent
        return f"{base} raised to the power of {exponent} is {result}"
    
    @staticmethod
    async def factorial(arguments: Dict[str, Any]) -> str:
        """Calculate factorial"""
        n = int(arguments["n"])
        if n < 0:
            raise ValueError("Factorial is not defined for negative numbers")
        if n > 20:
            raise ValueError("Factorial calculation limited to n <= 20 to prevent overflow")
        
        result = 1
        for i in range(1, n + 1):
            result *= i
        
        return f"The factorial of {n} is {result}"


class StringTools:
    """String manipulation tools"""
    
    @staticmethod
    def register_all():
        """Register all string tools"""
        
        # Uppercase tool
        uppercase_tool = Tool(
            name="uppercase",
            description="Convert text to uppercase",
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to convert to uppercase"}
                },
                "required": ["text"]
            }
        )
        registry.register_tool(uppercase_tool, StringTools.uppercase)
        
        # Reverse tool
        reverse_tool = Tool(
            name="reverse",
            description="Reverse a string",
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to reverse"}
                },
                "required": ["text"]
            }
        )
        registry.register_tool(reverse_tool, StringTools.reverse)
        
        # Word count tool
        word_count_tool = Tool(
            name="word_count",
            description="Count words in text",
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to count words in"}
                },
                "required": ["text"]
            }
        )
        registry.register_tool(word_count_tool, StringTools.word_count)
        
        # Character count tool
        char_count_tool = Tool(
            name="char_count",
            description="Count characters in text",
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to count characters in"},
                    "include_spaces": {"type": "boolean", "description": "Include spaces in count", "default": True}
                },
                "required": ["text"]
            }
        )
        registry.register_tool(char_count_tool, StringTools.char_count)
    
    @staticmethod
    async def uppercase(arguments: Dict[str, Any]) -> str:
        """Convert text to uppercase"""
        text = arguments["text"]
        return f"Uppercase: {text.upper()}"
    
    @staticmethod
    async def reverse(arguments: Dict[str, Any]) -> str:
        """Reverse text"""
        text = arguments["text"]
        return f"Reversed: {text[::-1]}"
    
    @staticmethod
    async def word_count(arguments: Dict[str, Any]) -> str:
        """Count words in text"""
        text = arguments["text"]
        words = len(text.split())
        return f"Word count: {words} words"
    
    @staticmethod
    async def char_count(arguments: Dict[str, Any]) -> str:
        """Count characters in text"""
        text = arguments["text"]
        include_spaces = arguments.get("include_spaces", True)
        
        if include_spaces:
            count = len(text)
            return f"Character count (with spaces): {count} characters"
        else:
            count = len(text.replace(" ", ""))
            return f"Character count (without spaces): {count} characters"


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
    MathTools.register_all()
    StringTools.register_all()
    if vault is not None:
        VaultTools.register_all(registry=registry, vault=vault)
    if llm_processor is not None:
        LLMTools.register_all(registry=registry, llm_processor=llm_processor)
    
    logger.info(f"Server initialized with {len(registry.get_tools())} tools")
    
    # Log all registered tools
    for tool in registry.get_tools():
        logger.info(f"  - {tool.name}: {tool.description}")







async def main():
    """
    Initializes all tools and starts the stdio server, running indefinitely.
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

    logger.info("Starting MCP server...")
    try:
        async with stdio_server() as (read_stream, write_stream):
            logger.info("MCP server running and awaiting client connections...")

            await app.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name="Vault MCP Server",
                    server_version=os.environ['MCP_VERSION'],
                    capabilities=app.get_capabilities(
                        notification_options=NotificationOptions(),
                        experimental_capabilities={}
                    )
                )
            )

    except asyncio.CancelledError:
        logger.info("Server task cancelled during stdio_server operation.")
    except Exception as e:
        logger.error(f"An error occurred within stdio_server context: {e}", exc_info=True)
        raise # Re-raise to let asyncio.run's outer handler catch it.
    finally:
        logger.info("MCP server stopped.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Server terminated by user (Ctrl+C).")
    except Exception as e:
        logger.error(f"Server exited with an unhandled exception: {e}", exc_info=True)