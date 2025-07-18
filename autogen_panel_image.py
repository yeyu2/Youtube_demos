#
#pip install --upgrade ag2==0.2.32 openai==1.36.1 panel==1.4.4
#
import autogen
from autogen import AssistantAgent, ConversableAgent, UserProxyAgent

import openai
from openai import OpenAI

import panel as pn
from panel.chat import ChatMessage

import os
import time
import asyncio

gpt4_config = {"config_list": [{'model': 'gpt-4o',}]}

prompt_assistant = AssistantAgent(
    name="Prompt_Assistant",
    human_input_mode="NEVER",
    llm_config=gpt4_config,
    system_message='''You are a prompt engineer for image generation tasks using the DALL-E model. 
      Your goal is to generate creative and accurate image prompts for the model based on user input.

      **Your Responsibilities:**

      1. **Analyze User Input:** Carefully read the user's message and identify their desired image 
      2. **Understand User Preferences:** Determine the user's preferred style, tone, and overall aesthetic (e.g., realistic, cartoon, abstract, whimsical).
      3. **Generate Image Prompts:** Craft one or more detailed image generation prompts based on the user's message and preferences. 
          - **Clarity is Key:** Make sure your prompts are clear, specific, and easy for the DALL-E model to interpret.
          - **Include Details:** Provide information about subject, setting, action, style, and composition. 
          - **Use Descriptive Language:**  Choose words and phrases that evoke the desired visual style and imagery.

      Please make sure your response only contains prompt sentences, without including any description or introduction of this prompt.
      ''',
)

def print_messages(recipient, messages, sender, config):

    print(f"print - Messages from: {sender.name} sent to: {recipient.name} | num messages: {len(messages)} | message: {messages[-1]}")

    content = messages[-1]['content']

    if all(key in messages[-1] for key in ['name']):
        chat_interface.send(content, user=messages[-1]['name'], respond=False)
    else:
        chat_interface.send(content, user=recipient.name, respond=False)
    
    return False, None  # required to ensure the agent communication flow continues

prompt_assistant.register_reply(
    [autogen.Agent, None],
    reply_func=print_messages, 
    config={"callback": None},
)

dalle_agent = ConversableAgent(
    name="Dalle_Agent",
    default_auto_reply= f"Image URL generated",
)

def generate_image(recipient, messages, sender, config):

    print(f"image - Messages from: {sender.name} sent to: {recipient.name} | num messages: {len(messages)} | message: {messages[-1]}")

    prompt = messages[-1]["content"]

    if all(key in messages[-1] for key in ['name']):
        chat_interface.send(prompt, user=messages[-1]['name'], respond=False)
    else:
        chat_interface.send(prompt, user=recipient.name, respond=False)

    client=OpenAI()
    response = client.images.generate(
        model=config['llm_config']['config_list'][0]['model'],
        prompt=prompt,
        size="1024x1024", 
        quality="standard",
        n=1,
    )
    image_url = response.data[0].url
    print("image_url:", image_url)

    jpg_pane = pn.pane.Image(image_url, width=400)
    content = ChatMessage(jpg_pane, user=dalle_agent.name)
    chat_interface.send(content)

    return False, {"content": content}

dalle3_config = {"config_list": [{"model": "dall-e-3"}]}

dalle_agent.register_reply(
        [autogen.Agent, None],
        reply_func=generate_image, 
        config={"llm_config": dalle3_config},
    )

class MyConversableAgent(autogen.ConversableAgent):

    async def a_get_human_input(self, prompt: str) -> str:
        global input_future

        chat_interface.send(prompt, user="System", respond=False)
        # Create a new Future object for this input operation if none exists
        if input_future is None or input_future.done():
            input_future = asyncio.Future()

        # Wait for the callback to set a result on the future
        await input_future

        input_value = input_future.result()
        input_future = None
        print("input_value: ", input_value)
        return input_value
    
user_proxy = MyConversableAgent(
   name="Admin",
   system_message="A human admin.", 
   code_execution_config=False,
   human_input_mode="ALWAYS",
)

groupchat = autogen.GroupChat(agents=[user_proxy, prompt_assistant, dalle_agent], messages=[], max_round=20)
manager = autogen.GroupChatManager(groupchat=groupchat, llm_config=gpt4_config)

async def delayed_initiate_chat(agent, recipient, message):

    global initiate_chat_task_created
    # Indicate that the task has been created
    initiate_chat_task_created = True

    # Wait for 2 seconds
    await asyncio.sleep(2)

    # Now initiate the chat
    await agent.a_initiate_chat(recipient, message=message)

initiate_chat_task_created = False
input_future = None

async def callback(contents: str, user: str, instance: pn.chat.ChatInterface):
    
    global initiate_chat_task_created
    global input_future

    if not initiate_chat_task_created:
        asyncio.create_task(delayed_initiate_chat(user_proxy, manager, contents))

    else:
        if input_future and not input_future.done():
            input_future.set_result(contents)
        else:
            print("There is currently no input being awaited.")

pn.extension(design="material")

chat_interface = pn.chat.ChatInterface(callback=callback)
chat_interface.send("Send a message!", user="System", respond=False)

pn.template.MaterialTemplate(
    title="Multi-agent with image generation",
    header_background="black",
    main=[chat_interface],
).servable()