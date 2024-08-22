#
# pip install --upgrade crewai==0.30.8 mesop=0.12.0 
#
from crewai import Crew, Process, Agent, Task
from langchain_openai import ChatOpenAI
from langchain_core.callbacks import BaseCallbackHandler
from typing import  Any, Dict, Optional

import mesop as me
import mesop.labs as mel

llm = ChatOpenAI(model="gpt-4o", openai_api_key="sk-your-openai-key")

@me.stateclass
class State:
  agent_messages: list[str]

_DEFAULT_BORDER = me.Border.all(
  me.BorderSide(color="#e0e0e0", width=1, style="solid")
)
_BOX_STYLE = me.Style(display="grid",border=_DEFAULT_BORDER,
                              padding=me.Padding.all(15),
                              overflow_y="scroll",
                              box_shadow=("0 3px 1px -2px #0003, 0 2px 2px #00000024, 0 1px 5px #0000001f"),
                              )

class MyCustomHandler(BaseCallbackHandler):
    def __init__(self, agent_name: str) -> None:
        self.agent_name = agent_name

    def on_chain_start(
        self, serialized: Dict[str, Any], inputs: Dict[str, Any], **kwargs: Any
    ) -> None:
        state = me.state(State)
        state.agent_messages.append(f"## Assistant: \r{inputs['input']}")

    def on_chain_end(self, outputs: Dict[str, Any], **kwargs: Any) -> None:
        state = me.state(State)
        state.agent_messages.append(f"## {self.agent_name}: \r{outputs['output']}")
        
writer = Agent(
    role='Tech Writer',
    backstory='''You are a tech writer who is capable of writing 
                tech blog post in depth.
              ''',
    goal="Write and iterate a high quality blog post.",
    llm=llm,
    callbacks=[MyCustomHandler("Writer")],
)
researcher = Agent(
    role='Tech Researcher',
    backstory='''You are a professional researcher for many technical topics. 
                You are good at list potential knowledge and trend of 
                the given topic
              ''',
    goal="list builtins about what key knowledge and trend of a given topic",
    llm=llm,
    callbacks=[MyCustomHandler("Researcher")],
)

def StartCrew(prompt):
    
    task1 = Task(
      description=f"""list builtins about what key knowledge 
                    and trend of a given topic: {prompt}.
                    """,
      agent=researcher,
      expected_output="Builtin points about where need to be improved.",

    )
    task2 = Task(
      description=f"""Based on the given research outcomes, 
                    write a blog post of {prompt}. 
                    """,
      agent=writer,
      expected_output="an article"
    )

    project_crew = Crew(
        tasks=[task1, task2],
        agents=[researcher, writer],
        manager_llm=llm,
        process=Process.sequential
    )

    result = project_crew.kickoff()

    return result

@me.page(
  security_policy=me.SecurityPolicy(
    allowed_iframe_parents=["https://google.github.io"]
  ),
  path="/crewai",
  title="CrewAI on Mesop",
)
def app():
  state = me.state(State)
  with me.box():
    mel.text_to_text(
      StartCrew,
      title="CrewAI Chat",
    )
  with me.box(style=_BOX_STYLE):
      me.text(text="Workflow...", type="headline-6")
      for message in state.agent_messages:
        with me.box(style=_BOX_STYLE):
          me.markdown(message)