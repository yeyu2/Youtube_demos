from openai import OpenAI
from os import getenv
import instructor
from pydantic import BaseModel, Field

class MovieRate(BaseModel):
    movie_name: str = Field(..., description="The name of the movie on the post.")
    movie_rate: str = Field(..., description="Your rating of the movie.")
    movie_review: str = Field(..., description="Your review of the movie.")

client = instructor.from_openai(OpenAI(base_url="https://api.fireworks.ai/inference/v1", 
                                        api_key=getenv("FIREWORKS_API_KEY")), mode=instructor.Mode.JSON)

result = client.chat.completions.create(
    model="accounts/fireworks/models/llama-v3p2-90b-vision-instruct",
    response_model=MovieRate,
    messages=[
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": "This is a picture about a movie. Please figure out the movie name, rate the movie and review comment."
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": "https://mickeyblog.com/wp-content/uploads/2018/11/2018-11-05-20_41_02-Toy-Story-4_-Trailer-Story-Cast-Every-Update-You-Need-To-Know-720x340.png"
                    }
                }
            ]
        }
    ],
)

print(result)
  