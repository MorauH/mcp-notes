import os
import asyncio
import logging

from vault import ObsidianVault
from llm.query_llm import LLMVaultProcessor
from server.mcp_server import VaultMCPServer
from server.http_server import MCPHttpServer

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ServerConfig:
    """Server configuration class"""
    
    def __init__(self):
        self.host = os.environ.get('MCP_HOST', '127.0.0.1')
        self.port = int(os.environ.get('MCP_PORT', '8080'))
        self.curr_path = os.path.dirname(os.path.abspath(__file__))
        self.vault_path = f"{self.curr_path}/../persistant/test_vault"
        self.relative_persistant_path = "./persistant"


async def initialize_vault(config: ServerConfig):
    """Initialize the vault and LLM processor"""
    logger.info("Initializing vault...")
    
    vault = ObsidianVault(config.vault_path, config.relative_persistant_path)
    llm_processor = LLMVaultProcessor(vault=vault)
    
    # Update the index
    num_docs = vault.update_index()
    logger.info(f"Indexed {num_docs} new/changed documents")
    
    return vault, llm_processor


async def main(use_http=True, use_stdio=False):
    """
    Main entry point: Initializes vault and starts requested servers.
    """
    config = ServerConfig()
    
    try:
        # Initialize vault and LLM processor
        vault, llm_processor = await initialize_vault(config)
        
        # Create MCP server with tools
        mcp_server = VaultMCPServer(vault=vault, llm_processor=llm_processor)
        base_server = mcp_server.get_server()

        runner = None
        if use_http:
            # Create and start HTTP server
            http_server = MCPHttpServer(base_server)
            runner = await http_server.start_server(host=config.host, port=config.port)
            logger.info("HTTP server is running")

        if use_stdio:
            # Create and start stdio server
            from server.mcp_stdio import MCPStdioServer
            stdio_server = MCPStdioServer(base_server)
            await stdio_server.start_server()
            logger.info("stdio server is running")

        logger.info("Server(s) running. Press Ctrl+C to stop.")
        
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
        # Run both servers by default
        use_http = os.environ.get('MCP_HTTP_ENABLED', 'true').lower() == 'true'
        use_stdio = os.environ.get('MCP_STDIO_ENABLED', 'false').lower() == 'true'
        
        asyncio.run(main(use_http=use_http, use_stdio=True))
    except KeyboardInterrupt:
        logger.info("Server terminated by user (Ctrl+C).")
    except Exception as e:
        logger.error(f"Server exited with an unhandled exception: {e}", exc_info=True)