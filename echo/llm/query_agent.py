import asyncio
import os
from typing import Any, Dict, List, Optional, Annotated, Sequence
from pydantic import BaseModel, Field
from langchain_core.tools import tool
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import CallToolRequest, ListToolsRequest
from langchain_mcp_adapters.tools import load_mcp_tools
import logging
from contextlib import asynccontextmanager


logger = logging.getLogger(__name__)

class AgentState(BaseModel):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    available_tools: List[Dict[str, Any]] = Field(default_factory=list)

class EchoAgent:
    """LangGraph agent with MCP tool integration and discovery"""
    
    def __init__(self, llm=None):
        self.llm = llm or ChatOpenAI(model="gpt-5-nano", temperature=0)
        self.mcp_sessions: Dict[str, (ClientSession, List[tool])] = {}
        self.tools = []
        
    @asynccontextmanager
    async def connect_mcp_server(self, server_name: str, server_params: StdioServerParameters):
        """Connect to an MCP server and discover its tools"""
        try:
            async with stdio_client(server_params) as (read, write):
                logger.info("Successfully spawned MCP server process.")

                async with ClientSession(read, write) as session:
                    await session.initialize()

                    # Discover tools from this server
                    tools = await load_mcp_tools(session)
                    # self.tools.extend(tools)

                    # self.mcp_sessions[server_name] = (session, tools)
                    
                    logger.info(f"Connected to MCP server: {server_name}")

                    yield tools

                    #await session.call_tool("create_new_note", {"title": "Test note", "content": "This is a test note."})


            
        except Exception as e:
            logger.error(f"Failed to connect to {server_name}: {e}")
            raise
        
    
    def create_agent(self, tools, system_message: str = None):
        """Create the LangGraph agent with tool awareness"""
        
        default_system = f"""You are a helpful assistant with access to various tools from MCP servers.

Guidelines:
1. Always consider which tools might be helpful for the user's request
2. Use tools when they can provide better information than your general knowledge
3. Explain what you're doing when using tools
4. If a tool fails, try alternative approaches or explain the limitation
5. Be aware of the parameters each tool requires

Provide clear, helpful responses and make good use of the available tools."""
        
        final_system_message = system_message or default_system
        
        # Create the react agent with tools
        self.agent = create_react_agent(
            self.llm, 
            tools,
            prompt=final_system_message
        )
        
        return self.agent
    
    async def run(self, message: str, chat_history: List[BaseMessage] = None) -> str:
        """Run the agent with a message"""
        try:
            # Prepare messages
            messages = chat_history or []
            messages.append(HumanMessage(content=message))
            
            # Run the agent
            state = {"messages": messages}
            
            # Execute the agent graph
            result = await self.agent.ainvoke(state)
            
            # Extract the final response
            if result and "messages" in result:
                last_message = result["messages"][-1]
                if hasattr(last_message, 'content'):
                    return last_message.content
                else:
                    return str(last_message)
            else:
                return "No response generated"
                
        except Exception as e:
            logger.error(f"Error running agent: {e}")
            return f"Error: {str(e)}"
    
    def run_sync(self, message: str, chat_history: List[BaseMessage] = None) -> str:
        """Synchronous version of run"""
        try:
            return asyncio.run(self.run(message, chat_history))
        except Exception as e:
            return f"Error: {str(e)}"
    
    async def close_all(self):
        """Close all MCP connections"""
        for server_name, (session, _) in self.mcp_sessions.items():
            try:
                del session
                logger.info(f"Closed connection to {server_name}")
            except Exception as e:
                logger.error(f"Error closing {server_name}: {e}")
        
        self.mcp_sessions.clear()
        self.tools.clear()

    

# Usage examples
async def example_usage():
    """Example of using the LangGraph MCP agent"""
    
    agent = EchoAgent()
    
    try:
        # Connect to MCP servers
        mcp_server_params = StdioServerParameters(
            command="python",
            args=["src/mcp_server.py"],
            env=os.environ.copy()  # Pass all environment variables (req for numpy on nixos)
        )
        #await agent.connect_mcp_server(
        #    server_name="mcp_server",
        #    server_params=mcp_server_params
        #)

        async with agent.connect_mcp_server("mcp_server", mcp_server_params) as tools:
        
            # Create the agent (it's now aware of all tools)
            agent.create_agent(tools)
            
            # Use the agent
            print("\n=== AGENT CONVERSATION ===")
            
            print("TESTING PINGING SESSION...")
            for name, (session, _) in agent.mcp_sessions.items():
                try:
                    response = await session.send_ping()
                    print(f"Ping response from {name}: {response}")
                except Exception as e:
                    print(f"Error pinging {name}: {e}")

            response = await agent.run("Create a new note called 'test_note' with the content 'This is a test note.'")
            print(f"Agent: {response}")
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        await agent.close_all()


if __name__ == "__main__":
    # Run the example
    asyncio.run(example_usage())