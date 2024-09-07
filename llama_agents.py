#
# pip install --upgrade llama-agents==0.0.14 llama-index-agent-openai==0.3.0 llama-index-tools-duckduckgo==0.2.1
#
from llama_agents import (
    AgentService,
    ControlPlaneServer,
    SimpleMessageQueue,
    PipelineOrchestrator,
    ServiceComponent,
    LocalLauncher,
    AgentOrchestrator,
    HumanService,
)

from llama_index.core.agent import FunctionCallingAgentWorker
from llama_index.core.tools import FunctionTool
from llama_index.core.query_pipeline import QueryPipeline
from llama_index.llms.openai import OpenAI
from llama_index.agent.openai import OpenAIAgent

from llama_agents import HumanService

import nest_asyncio

nest_asyncio.apply()

def get_a_topic() -> str:
    """Returns a topic name."""
    return "The topic is: gpt-5."

def get_a_view() -> str:
    """Returns the view."""
    return "This GPT model is positive."

message_queue = SimpleMessageQueue()

from llama_index.tools.duckduckgo import DuckDuckGoSearchToolSpec

tool_spec = DuckDuckGoSearchToolSpec()

worker_search = FunctionCallingAgentWorker.from_tools(DuckDuckGoSearchToolSpec().to_tool_list(), llm=OpenAI(model="gpt-4o"))
agent_search = worker_search.as_agent()

agent_search_server = AgentService(
    agent=agent_search,
    message_queue=message_queue,
    description="Useful for Internet search",
    service_name="search_agent",
)

tool = FunctionTool.from_defaults(fn=get_a_topic)

worker1 = FunctionCallingAgentWorker.from_tools([tool], llm=OpenAI(model="gpt-4o"))
agent1 = worker1.as_agent()

agent1_server = AgentService(
    agent=agent1,
    message_queue=message_queue,
    description="Useful for getting the topic.",
    service_name="topic_agent",
)

tool2 = FunctionTool.from_defaults(fn=get_a_view)

agent2 = OpenAIAgent.from_tools(
    [tool2],
    system_prompt="Get a view of positive or negative from perform the task tool.",
    llm=OpenAI(model="gpt-4o"),
)

agent2_server = AgentService(
    agent=agent2,
    message_queue=message_queue,
    description="Useful for getting view of positive or negative.",
    service_name="view_agent",
)

human_service = HumanService(
    service_name="Human_Service", description="Answer question about the topic.", 
      message_queue=message_queue,
)

agent2_component = ServiceComponent.from_service_definition(agent2_server)
agent_human_component = ServiceComponent.from_service_definition(human_service)

agent_search_component = ServiceComponent.from_service_definition(agent_search_server)

pipeline = QueryPipeline(chain=[agent_search_component, agent2_component, ])

pipeline_orchestrator = PipelineOrchestrator(pipeline)

control_plane = ControlPlaneServer(message_queue, pipeline_orchestrator)

launcher = LocalLauncher([agent_search_server, agent2_server], control_plane, message_queue)
result = launcher.launch_single("What is the latest gpt model and what is your view of it?")

print(f"Result: {result}")