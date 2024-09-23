import instructor
from typing import List
from pydantic import BaseModel, Field
from openai import OpenAI
import os
from dotenv import load_dotenv
load_dotenv()

api_key = os.getenv("OPENROUTER_API_KEY")

class ReasoningSteps(BaseModel):
    reasoning_steps: List[str] = Field(
        ..., description="The detailed reasoning steps leading to the final conclusion."
    )
    answer: str = Field(..., description="The final answer, taking into account the reasoning steps.")

client = instructor.from_openai(OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key), mode=instructor.Mode.JSON)


result = client.chat.completions.create(
    model="mistralai/mistral-large",
    response_model=ReasoningSteps,
    messages=[{"role": "user", "content": "Compare three deminal numbers 9.11, 9.9, 9.10, which is bigger?"}],
)

print(result)