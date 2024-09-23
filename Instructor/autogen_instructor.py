from autogen import AssistantAgent, UserProxyAgent, config_list_from_json
from pydantic import BaseModel, Field
from typing import List, Optional, Union
from types import SimpleNamespace
import instructor
from openai import OpenAI
import litellm
from litellm import completion
import os
from dotenv import load_dotenv
load_dotenv()

api_key = os.getenv("OPENROUTER_API_KEY")
print(api_key)

class ExtractedInfo(BaseModel):
    name: str
    department: Optional[str]
    job_title: Optional[str]
    location: Optional[str]
    specialization: List[str] = Field(default_factory=list)

class CustomLLMClient:
    def __init__(self, config, **kwargs):
        print(f"CustomLLMClient config: {config}")

    def create(self, params):
        client = instructor.from_openai(OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key), mode=instructor.Mode.JSON)
        response = client.chat.completions.create(
            model="google/gemma-2-9b-it:free",
            messages=params["messages"],
            response_model=ExtractedInfo, 
        )

        autogen_response = SimpleNamespace()
        autogen_response.choices = []
        autogen_response.model = "custom_llm_extractor"  

        choice = SimpleNamespace()
        choice.message = SimpleNamespace()
        choice.message.content = response.model_dump_json()
        choice.message.function_call = None
        autogen_response.choices.append(choice)
        return autogen_response

    def message_retrieval(self, response):
        choices = response.choices
        return [choice.message.content for choice in choices]

    def cost(self, response) -> float:
        response.cost = 0 
        return 0

    @staticmethod
    def get_usage(response):
        return {}

config_list=[
    {
        "model": "custom_llm_extractor",
        "model_client_cls": "CustomLLMClient",
    }
]

user_proxy = UserProxyAgent("user_proxy", code_execution_config=False)
assistant = AssistantAgent(
    "assistant",
    llm_config={
        "config_list": config_list,  
        "cache": None, 
        "cache_seed": None
    },
)
assistant.register_model_client(model_client_cls=CustomLLMClient)

user_proxy.initiate_chat(
    assistant,
    message="""
    I'm Alice Johnson, or Al for short. 
    I'm a Senior Digital Strategist in the Marketing department at YeyuLab, based in San Diego. 
    My specializations include social media marketing, content strategy, and data analytics. 
    I also dabble in SEO and email marketing. 
    """,
)

assistant_response = assistant.last_message()["content"]
extracted_info = ExtractedInfo.model_validate_json(assistant_response)

print(extracted_info)