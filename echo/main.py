import os
import sys
import asyncio
import logging

from echo.vault import ObsidianVault
from echo.llm.query_llm import LLMVaultProcessor

from echo.server.mcp_server import VaultMCPServer
from echo.server.http_server import MCPHttpServer
from echo.server.stdio_server import MCPStdioServer


# Configure logging
def configure_logging(use_stdio=False):
    """Configure logging based on server mode"""
    if use_stdio:
        # In stdio mode, ensure all logging goes to stderr
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
        logging.root.addHandler(handler)
        logging.root.setLevel(logging.INFO)
    else:
        # Normal logging configuration for HTTP mode
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
        self.embedding_model = "text-embedding-3-small"


async def initialize_vault(config: ServerConfig):
    """Initialize the vault and LLM processor"""
    logger.info("Initializing vault...")
    
    vault = ObsidianVault(config.vault_path, config.relative_persistant_path, config.embedding_model)
    llm_processor = LLMVaultProcessor(vault=vault)
    
    # Update the index
    num_docs = vault.update_index()
    logger.info(f"Indexed {num_docs} new/changed documents")
    
    return vault, llm_processor


async def main(use_http=True, use_stdio=False):
    """
    Main entry point: Initializes vault and starts requested servers.
    """
    # Configure logging based on server mode
    configure_logging(use_stdio)
    
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
            http_server = MCPHttpServer(mcp_server)
            runner = await http_server.start_server(host=config.host, port=config.port)
            logger.info("HTTP server is running")

        if use_stdio:
            # Create and start stdio server
            stdio_server = MCPStdioServer(base_server)
            await stdio_server.start_server()
            logger.info("stdio server is running")

        logger.info("Server(s) running. Press Ctrl+C to stop.")
        
        # Keep the server running
        while True:
           await asyncio.sleep(1)

    except KeyboardInterrupt:
        logger.info("Server terminated by user (Ctrl+C).") 
    finally:
        logger.info("MCP server stopped.")
        if 'runner' in locals():
            await runner.cleanup()


if __name__ == "__main__":
    try:
        import argparse
        parser = argparse.ArgumentParser(description="Echo MCP Server")
        parser.add_argument("--stdio", action="store_true", help="Run in stdio mode")
        args = parser.parse_args()
        
        # Run in stdio mode if flag is set, otherwise HTTP mode
        asyncio.run(main(use_http=not args.stdio, use_stdio=args.stdio))
    except KeyboardInterrupt:
        logger.info("Server terminated by user (Ctrl+C).")
