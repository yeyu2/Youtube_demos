import instructor
from typing import Literal
from pydantic import BaseModel, Field
from openai import OpenAI
import os
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("OPENROUTER_API_KEY")

def get_revenue(financial_year: int, company: str) -> str:
    """
    Get revenue data for a company given the year.
    """
    # Dummy implementation
    return f"Revenue for {company} in {financial_year}: $1,000,000,000"

class FunctionCall(BaseModel):
    name: Literal["get_revenue"] = "get_revenue"
    arguments: "FunctionArguments"

class FunctionArguments(BaseModel):
    financial_year: str = Field(..., description="Year for which we want to get revenue data")
    company: str = Field(..., description="Name of the company for which we want to get revenue data")

FunctionCall.model_rebuild()

client = instructor.from_openai(OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key), mode=instructor.Mode.JSON)

# Test FunctionCall
function_result = client.chat.completions.create(
    model="meta-llama/llama-3.2-1b-instruct:free",
    response_model=FunctionCall,
    messages=[
        {"role": "system", "content": "You are an AI assistant that generates function calls based on user requests."},
        {"role": "user", "content": "Get the revenue for Apple Inc. in 2022"}
    ],
)

print(function_result)

if function_result.name == "get_revenue":
    result = get_revenue(**function_result.arguments.dict())
    print(result)
else:
    print("Unknown function call")
