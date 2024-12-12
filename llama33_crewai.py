## crewai==0.80.0 ollama==0.4.4

from crewai import Agent, Crew, Process, Task, LLM
from crewai.tools import BaseTool
from twikit import Client, Tweet
import asyncio
import os
from dotenv import load_dotenv
from pydantic import BaseModel
load_dotenv()

class TwitterScraperTool(BaseTool):
    name: str = "Twitter Scraper"
    description: str = "Scrapes the latest tweets from a specified Twitter/X user"

    def _run(self, username: str) -> str:
        async def get_latest_tweets():
            client = Client('en-US')
            await client.login(
                auth_info_1=os.getenv('AUTH_INFO_1'),
                auth_info_2=os.getenv('AUTH_INFO_2'),
                password=os.getenv('PASSWORD')
            )
            tweets = await client.get_user_tweets(username, 'tweets')
            return tweets[:1] if tweets else []  # Return up to 1 latest tweet

        tweets = asyncio.run(get_latest_tweets())
        return "\n".join([f"Tweet: {tweet.text}" for tweet in tweets])

class Summary(BaseModel):
    product: str
    category: str
    description: str
    highlights: str

collector_agent = Agent(
    role="Twitter Data Collector",
    goal="Get the latest tweet from specified users",
    backstory="""You are a social media collector specialized in gathering tweets from specified users.""",
    verbose=False,
    allow_delegation=False,
    tools=[TwitterScraperTool()],
    llm=LLM(model="ollama/llama3.3", base_url="http://localhost:11434"),
)

analysis_agent = Agent(
    role="Twitter Data Analyst",
    goal="Analyze the latest tweets from the tweet content",
    backstory="""You are a social media analyst specialized in analyzing Twitter data. 
    You help generate a summary of the latest tweet from the tweet content.""",
    verbose=False,
    allow_delegation=False,
    llm=LLM(model="ollama/llama3.3", base_url="http://localhost:11434"),
)

task1 = Task(
    description="""Fetch and analyze the latest tweet from user ID: {user_id}""",
    expected_output="The latest tweet content from the user ID",
    agent=collector_agent,
)
task2 = Task(
    description="""Analyze the latest tweet from the tweet content the collector agent provided""",
    expected_output="The summary of the latest tweet from the tweet content",
    agent=analysis_agent,
    output_pydantic=Summary,
)

crew = Crew(
    agents=[collector_agent, analysis_agent],
    tasks=[task1, task2],
    verbose=True,
    process=Process.sequential,
)

result = crew.kickoff(inputs={"user_id": "1034844617261248512"})
