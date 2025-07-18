# 
# pip install --upgrade mesop==0.10.0 ag2==0.2.33
#
import mesop as me
import mesop.labs as mel

import autogen
from autogen import AssistantAgent, ConversableAgent, UserProxyAgent

import os
import time
import asyncio

_DEFAULT_BORDER = me.Border.all(
  me.BorderSide(color="#e0e0e0", width=1, style="solid")
)
_BOX_STYLE = me.Style(display="grid",border=_DEFAULT_BORDER,
                              padding=me.Padding.all(15),
                              overflow_y="scroll",
                              box_shadow=("0 3px 1px -2px #0003, 0 2px 2px #00000024, 0 1px 5px #0000001f"),
                              )

@me.stateclass
class State:
  agent_messages: list[str]

@me.page(
  security_policy=me.SecurityPolicy(
    allowed_iframe_parents=["https://google.github.io"]
  ),
  path="/autogen",
  title="AutoGen Group chat",
)
def app():
  state = me.state(State)
  with me.box():
    mel.text_to_text(
      groupchat_workflow,
      title="AutoGen Group chat",
    )
  with me.box(style=_BOX_STYLE):
      me.text(text="Workflow...", type="headline-6")
      for message in state.agent_messages:
        with me.box(style=_BOX_STYLE):
          me.markdown(message)

gpt4_config = {"config_list": [{'model': 'gpt-4o',}], "temperature":0, "seed": 53}

def print_messages(recipient, messages, sender, config):

    print(f"print - Messages from: {sender.name} sent to: {recipient.name} | num messages: {len(messages)} | message: {messages[-1]}")

    content = messages[-1]['content']
    state = config["state"]

    if all(key in messages[-1] for key in ['name']):
        state.agent_messages.append(f"## {messages[-1]['name']}: \r{content}") 
    else:
        state.agent_messages.append(f"## {recipient.name}: \r{content}") 

    return False, None  # required to ensure the agent communication flow continues

def groupchat_workflow(s: str):
    print("start...")
    state = me.state(State)

    user_proxy = autogen.UserProxyAgent(
        name="User_proxy",
        system_message="A human admin.",
        code_execution_config=False,  
        human_input_mode="NEVER",
        is_termination_msg=lambda msg: "TERMINATE" in msg["content"]
    )
    writer = autogen.AssistantAgent(
        name="Writer",
        system_message="You are a blog post writer who consolidates and writes blog post based on the research content from Researcher. Say TERMINATE after your blog post generated.",
        llm_config=gpt4_config,
        is_termination_msg=lambda msg: "TERMINATE" in msg["content"]
    )
    researcher = autogen.AssistantAgent(
        name="Researcher",
        system_message="You are a tech Researcher who makes in-depth technical research on topics.",
        llm_config=gpt4_config,
        is_termination_msg=lambda msg: "TERMINATE" in msg["content"]
    )
    
    user_proxy.register_reply(
        [autogen.Agent, None],
        reply_func=print_messages, 
        config={"state": state},
    ) 
    writer.register_reply(
        [autogen.Agent, None],
        reply_func=print_messages, 
        config={"state": state},
    )
    researcher.register_reply(
        [autogen.Agent, None],
        reply_func=print_messages, 
        config={"state": state},
    ) 

    groupchat = autogen.GroupChat(agents=[user_proxy, writer, researcher], messages=[], max_round=8)
    manager = autogen.GroupChatManager(groupchat=groupchat, llm_config=gpt4_config)

    response = user_proxy.initiate_chat(
                        manager,
                        message=s,
                        )

    print(response)
    return response.summary