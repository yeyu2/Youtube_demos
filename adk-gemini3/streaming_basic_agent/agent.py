import asyncio
from typing import AsyncGenerator

from google.adk.agents.llm_agent import Agent
from google.adk.tools.function_tool import FunctionTool


async def monitor_stock_price(stock_symbol: str) -> AsyncGenerator[str, None]:
    """
    Monitor the price for the given stock symbol in a continuous, streaming way.
    
    This is a basic example of a streaming tool that yields multiple results over time.
    In a real application, this would connect to a stock price API.
    
    Args:
        stock_symbol: The stock ticker symbol to monitor (e.g., 'AAPL', 'GOOGL')
    """
    import random
    
    print(f"Start monitoring stock price for {stock_symbol}!")
    
    # Start with a base price
    current_price = 300
    
    # Continuous monitoring loop
    while True:
        await asyncio.sleep(10)
        
        # Simulate price change (±10%)
        change = random.randint(-10, 10)
        current_price += change
        
        price_alert = f"The price for {stock_symbol} is ${current_price}"
        yield price_alert
        print(price_alert)


def stop_streaming(function_name: str):
    """
    Stop a currently running streaming function.
    
    Args:
        function_name: The name of the streaming function to stop (e.g., 'monitor_stock_price')
    """
    print(f"Stopping streaming function: {function_name}")
    return f"Stopped {function_name}"


# Create the root agent
root_agent = Agent(
    model="gemini-2.5-flash-native-audio-preview-09-2025",
    name="basic_streaming_agent",
    description=(
        "A basic streaming agent that demonstrates ADK streaming tool capabilities.\n\n"
        "This agent can monitor stock prices in real-time using streaming tools.\n\n"
        "Example usage:\n"
        "- 'Monitor the stock price for AAPL'\n"
        "- 'Start monitoring GOOGL stock'\n"
        "- 'Stop monitoring'\n\n"
        "Streaming tools allow the agent to continuously yield results over time, "
        "rather than returning a single response."
    ),
    tools=[
        FunctionTool(monitor_stock_price),
        FunctionTool(stop_streaming),
    ],
)
