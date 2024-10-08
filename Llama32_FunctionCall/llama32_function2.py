import instructor
from typing import Literal, Optional
from pydantic import BaseModel, Field
from openai import OpenAI
import os
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("OPENROUTER_API_KEY")

def set_temperature(room: str, temperature: float) -> str:
    """
    Set the temperature for a specific room in the smart home.
    """
    return f"Temperature in {room} set to {temperature}°C"

def toggle_lights(room: str, state: bool) -> str:
    """
    Turn the lights on or off in a specific room.
    """
    action = "on" if state else "off"
    return f"Lights in {room} turned {action}"

class FunctionCall(BaseModel):
    name: Literal["set_temperature", "toggle_lights"]
    arguments: "FunctionArguments"

class FunctionArguments(BaseModel):
    room: str = Field(..., description="The name of the room in the house")
    temperature: Optional[float] = Field(None, description="The desired temperature in Celsius")
    state: Optional[bool] = Field(None, description="True to turn on lights, False to turn off")

FunctionCall.model_rebuild()

client = instructor.from_openai(OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key), mode=instructor.Mode.JSON)

def process_command(user_input: str) -> str:
    function_result = client.chat.completions.create(
        model="meta-llama/llama-3.2-3b-instruct:free",
        response_model=FunctionCall,
        messages=[
            {"role": "system", "content": "You are an AI assistant that controls a smart home system. Generate appropriate function calls based on user requests."},
            {"role": "user", "content": user_input}
        ],
    )

    if function_result.name == "set_temperature":
        return set_temperature(function_result.arguments.room, function_result.arguments.temperature)
    elif function_result.name == "toggle_lights":
        return toggle_lights(function_result.arguments.room, function_result.arguments.state)
    else:
        return "Unknown command"

# Simulate user interactions
commands = [
    "Hey, can you make the living room a bit warmer? Like 22 degrees or so?",
    "It's too bright in here. Turn off the bedroom lights, please.",
    "I'm heading to the kitchen. Could you turn the lights on for me?",
    "The study's a bit chilly. Set it to 19 degrees, would you?"
]

for command in commands:
    print(f"User: {command}")
    result = process_command(command)
    print(f"System: {result}\n")