from swarm import Swarm, Agent, Result
import os
from llama_index.core import VectorStoreIndex, SimpleDirectoryReader
from llama_index.embeddings.fireworks import FireworksEmbedding
from llama_index.core import Settings
from llama_index.llms.openai import OpenAI

os.environ["OPENAI_API_KEY"] = "sk-your-openai-api-key"
os.environ["FIREWORKS_API_KEY"] = "fw-your-fireworks-api-key"

Settings.embed_model = FireworksEmbedding()
Settings.llm = OpenAI("gpt-4o")

def create_rag_index(pdf_filepath="data"):
    documents = SimpleDirectoryReader(pdf_filepath).load_data()
    index = VectorStoreIndex.from_documents(documents)
    print("Index created.")
    return index

rag_index = create_rag_index()

def query_rag(query_str):
    query_engine = rag_index.as_query_engine()
    response = query_engine.query(query_str)
    return str(response)

context_variables = {}

def triage_agent_instructions(context_variables):
    return """You are a triage agent.
    If the user asks a question related to the document, hand off to the RAG agent.
    """
def rag_agent_instructions(context_variables):
    return """You are a RAG agent. Answer user questions by using the `query_rag` function to retrieve information.
    """

def handoff_to_rag_agent():
    return Result(agent=rag_agent)

triage_agent = Agent(
    name="Triage Agent",
    instructions=triage_agent_instructions,
    functions=[handoff_to_rag_agent]
    )
rag_agent = Agent(
    name="RAG Agent",
    instructions=rag_agent_instructions,
    functions=[query_rag]
    )

client = Swarm()

def run_swarm_app():
    print("Welcome to the RAG Swarm App!")
    current_agent = triage_agent
    messages = []
    while True:
        user_input = input("User: ")
        if user_input.lower() == "exit":
            break
        messages.append({"role": "user", "content": user_input})
        response = client.run(
            agent=current_agent,
            messages=messages,
            )
        print(f"{response.agent.name}: {response.messages[-1]['content']}")
        messages = response.messages
        current_agent = response.agent

if __name__ == "__main__":
    run_swarm_app()