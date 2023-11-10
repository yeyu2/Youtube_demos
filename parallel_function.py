import openai
import json

def get_stock_price(symbol):
    if symbol == "TSLA":
        return "$222.18"
    else:
        return "Unknown"

def tweet_send(symbol):
    data = get_stock_price(symbol)
    answer = f"New Tweet Msg: Tesla's Q2 revenue in 2023 was {data}. #Tesla #2023"
    return answer

def facebook_send(symbol):
    data = get_stock_price(symbol)
    answer = f"New Facebook Msg: Tesla's Q2 revenue in 2023 was {data}. #Tesla #2023"
    return answer

messages = [{"role": "user", "content": "Send a tweet message and facebook message about Tesla's current stock price."}]
tools = [
    {
        "type": "function",
        "function": {
            "name": "facebook_send",
            "description": "generate a tweet message based on input stock symbol and send it to facebook",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "The Stock Symbol, like AAPL",
                    },
                },
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "tweet_send",
            "description": "generate a tweet message based on input stock symbol and send it to twitter",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "The Stock Symbol, like AAPL",
                    },
                },
                "required": ["symbol"],
            },
        },
    }
]

response = openai.chat.completions.create(
    model="gpt-4-0613",
    messages=messages,
    tools=tools,
    tool_choice="auto",  
)
response_message = response.choices[0].message
tool_calls = response_message.tool_calls

print(tool_calls)