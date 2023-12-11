# To install required packages:
# pip install panel openai==1.3.6 panel==1.3.4
# pip install git+https://github.com/microsoft/autogen.git


import autogen
import panel as pn
import openai
import os
import time
import asyncio
from autogen import config_list_from_json
from autogen.agentchat.contrib.gpt_assistant_agent import GPTAssistantAgent
from openai import OpenAI


os.environ["OPENAI_API_KEY"] = "sk-Your_OpenAI_KEY"
assistant_id = os.environ.get("ASSISTANT_ID", None)
document = ''
client = OpenAI()
config_list = [
    {
        'model': 'gpt-4-1106-preview',
    }
    ]
llm_config = {
    "config_list": config_list,
    "seed": 36,
    "assistant_id": assistant_id,
    "tools": [
            {
                "type": "retrieval"
            }
        ],
    "file_ids": [],
}

input_future = None

class MyConversableAgent(autogen.ConversableAgent):

    async def a_get_human_input(self, prompt: str) -> str:
        global input_future
        chat_interface.send(prompt, user="System", respond=False)
        # Create a new Future object for this input operation if none exists
        if input_future is None or input_future.done():
            input_future = asyncio.Future()

        # Wait for the callback to set a result on the future
        await input_future

        # Once the result is set, extract the value and reset the future for the next input operation
        input_value = input_future.result()
        input_future = None
        return input_value

user_proxy = MyConversableAgent(name="user_proxy",
    code_execution_config=False,
    is_termination_msg=lambda msg: "TERMINATE" in msg["content"],
    human_input_mode="ALWAYS")

gpt_assistant = GPTAssistantAgent(name="assistant",
    instructions="You are adapt at question answering",
    llm_config=llm_config)

avatar = {user_proxy.name:"👨‍💼", gpt_assistant.name:"🤖"}

def print_messages(recipient, messages, sender, config):

    print(f"Messages from: {sender.name} sent to: {recipient.name} | num messages: {len(messages)} | message: {messages[-1]}")
    chat_interface.send(messages[-1]['content'], user=sender.name, avatar=avatar[sender.name], respond=False)
   
    return False, None  # required to ensure the agent communication flow continues

user_proxy.register_reply(
    [autogen.Agent, None],
    reply_func=print_messages, 
    config={"callback": None},
)
gpt_assistant.register_reply(
    [autogen.Agent, None],
    reply_func=print_messages, 
    config={"callback": None},
) 

initiate_chat_task_created = False

async def delayed_initiate_chat(agent, recipient, message):

    global initiate_chat_task_created
    # Indicate that the task has been created
    initiate_chat_task_created = True

    await asyncio.sleep(2)

    # Now initiate the chat
    await agent.a_initiate_chat(recipient, message=message)

    recipient.delete_assistant()

    if llm_config['file_ids'][0]:
        client.files.delete(llm_config['file_ids'][0])
        print(f"Deleted file with ID: {llm_config['file_ids'][0]}")

    time.sleep(5)


async def callback(contents: str, user: str, instance: pn.chat.ChatInterface):

    global initiate_chat_task_created
    global input_future
    global gpt_assistant

    if not initiate_chat_task_created:
        asyncio.create_task(delayed_initiate_chat(user_proxy, gpt_assistant, contents))
        
    else:
        if input_future and not input_future.done():
            input_future.set_result(contents)
        else:
            print("There is currently no input being awaited.")

pn.extension(design="material")

chat_interface = pn.chat.ChatInterface(
    callback=callback,

    show_button_name=False,
    sizing_mode="stretch_both",
    min_height=600,
)

chat_interface.send("Ask your question about the document!!", user="System", respond=False)

uploading = pn.indicators.LoadingSpinner(value=False, size=50, name='No document')
file_input = pn.widgets.FileInput(name="PDF File", accept=".pdf")
text_area = pn.widgets.TextAreaInput(name='File Info', sizing_mode='stretch_both', min_height=600)

def file_callback(*events):

    for event in events:
        if event.name == 'filename':
            file_name = event.new
        if event.name == 'value':
            file_content = event.new
    
    uploading.value = True
    uploading.name = 'Uploading'
    file_path = file_name

    with open(file_path, 'wb') as f:
        f.write(file_content)
    
    response = client.files.create(file=open(file_path, 'rb'), purpose='assistants')

    found = False
    while not found:
        for file in all_files.data:
            if file.id == response.id:
                found = True
                print(f"Uploaded file with ID: {response.id}\n {file}")
                
                global gpt_assistant
                llm_config['file_ids'] = [file.id]
                gpt_assistant.delete_assistant()
                gpt_assistant = GPTAssistantAgent(name="assistant",
                                instructions="You are adept at question answering",
                                llm_config=llm_config)
                gpt_assistant.register_reply(
                                    [autogen.Agent, None],
                                    reply_func=print_messages, 
                                    config={"callback": None},
                                ) 

                text_area.value = str(client.files.retrieve(file.id))

                uploading.value = False
                uploading.name = f"Document uploaded - {file_name}"
                break 
        if not found:
            time.sleep(5)
            all_files = client.files.list()

# Set up a callback on file input value changes
file_input.param.watch(file_callback, ['value', 'filename'])

title = '## Please upload your document for RAG'
file_app = pn.Column(pn.pane.Markdown(title), file_input, uploading, text_area, sizing_mode='stretch_width', min_height=500)

pn.template.FastListTemplate(
    title="📚AutoGen w/ RAG",
    header_background="#2F4F4F",
    accent_base_color="#2F4F4F",
    main=[
        chat_interface
    ],
    sidebar=[file_app],
    sidebar_width=400,
).servable()