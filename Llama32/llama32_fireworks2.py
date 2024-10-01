from openai import OpenAI
from os import getenv
import instructor
from typing import List
from pydantic import BaseModel, Field

class CookBook(BaseModel):
    recipe_name: str = Field(..., description="The name of the recipe.")
    ingredients: List[str] = Field(..., description="The ingredients of the recipe.")
    instructions: str = Field(..., description="The instructions of the recipe.")

client = instructor.from_openai(OpenAI(base_url="https://api.fireworks.ai/inference/v1", 
                                        api_key=getenv("FIREWORKS_API_KEY")), mode=instructor.Mode.JSON)

result = client.chat.completions.create(
    model="accounts/fireworks/models/llama-v3p2-90b-vision-instruct",
    response_model=CookBook,
    messages=[
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": "This is a picture of a famous cuisine. Please figure out the recipe name and ingredients and write a recipe instruction."
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": "https://www.howtocook.recipes/wp-content/uploads/2021/05/Ratatouille-recipe-500x500.jpg"
                    }
                }
            ]
        }
    ],
)

print(result)