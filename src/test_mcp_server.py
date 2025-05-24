#!/usr/bin/env python3
import os
import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import logging

# Configure logging to see what's happening
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def simple_mcp_test():
    logger.info("Starting simple MCP server test...")
    logger.info("-" * 40)

    server_params = StdioServerParameters(
        command="python",
        args=["src/mcp_server.py"],
        env=os.environ.copy() # Pass all environment variables (req for numpy on nixos)
    )
    # -------------------

    try:
        async with stdio_client(server_params) as (read, write):
            logger.info("Successfully spawned MCP server process.")

            async with ClientSession(read, write) as session:
                # Give the server a moment to start up
                await asyncio.sleep(1)

                logger.info("1. Initializing MCP session...")
                await session.initialize()
                logger.info("MCP session initialized successfully!")

                logger.info("\n2. Listing available tools...")
                tools_result = await session.list_tools()

                if tools_result.tools:
                    logger.info(f"Found {len(tools_result.tools)} tools:")
                    for tool in tools_result.tools:
                        logger.info(f"  - {tool.name}: {tool.description}")
                    
                    logger.info("\n3. Calling 'vector_query' tool...")
                    query_result = await session.call_tool(
                        name="vector_query",
                        arguments={
                            "query_text": "Artificial Intelligence",
                            "top_k": 2
                        }
                    )
                    logger.info(f"Query result: {query_result}")

                    logger.info("\n4. Calling 'summarize_topic_from_notes' tool...")
                    summarize_result = await session.call_tool(
                        name="summarize_topic_from_notes",
                        arguments={
                            "topic": "Artificial Intelligence",
                            "include_extended_context": True
                        }
                    )
                    logger.info(f"Summarize result: {summarize_result}")
                    
                else:
                    logger.warning("No tools found on the server.")

                logger.info("\nSimple MCP test completed.")
                logger.info("-" * 40)

    except FileNotFoundError:
        logger.error(
            f"Error: Could not find the server script at '{server_params.args[0]}'. "
            "Please check the path in 'server_params'."
        )
    except Exception as e:
        logger.error(f"An error occurred during the MCP test: {e}")
        logger.error("Make sure your 'mcp_server.py' is running correctly.")

if __name__ == "__main__":
    asyncio.run(simple_mcp_test())