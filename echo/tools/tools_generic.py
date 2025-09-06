
from typing import Any, Dict, List, Optional
from mcp.types import Tool, TextContent
import logging

from echo.tools import ToolRegistry


logger = logging.getLogger(__name__)



class MathTools:
    """Mathematical operations tools"""
    
    @staticmethod
    def register_all(registry: ToolRegistry):
        """Register all math tools"""
        
        # Addition tool
        add_tool = Tool(
            name="math_add",
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
            name="math_multiply",
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
            name="math_power",
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
            name="math_factorial",
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
    def register_all(registry: ToolRegistry):
        """Register all string tools"""
        
        # Uppercase tool
        uppercase_tool = Tool(
            name="string_uppercase",
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
            name="string_reverse",
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
            name="string_word_count",
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
            name="string_char_count",
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


