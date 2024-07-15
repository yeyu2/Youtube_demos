import os
import time
import asyncio
import threading
import autogen
from flask import Flask, request, jsonify
from flask_cors import CORS
from autogen.agentchat.contrib.gpt_assistant_agent import GPTAssistantAgent
from autogen.agentchat import AssistantAgent, UserProxyAgent
import queue

app = Flask(__name__)
cors=CORS(app)

chat_status = "ended"  

# Queues for single-user setup
print_queue = queue.Queue()
user_queue = queue.Queue()

# Replace with your actual OpenAI API key
os.environ["OPENAI_API_KEY"] = "Your_API_Key" 

class MyConversableAgent(autogen.ConversableAgent):
    async def a_get_human_input(self, prompt: str) -> str:
        input_prompt = "Please input your further direction, or type 'approved' to proceed, or type 'exit' to end the conversation"

        print_queue.put({'user': "System", 'message': input_prompt})

        start_time = time.time()
        global chat_status
        chat_status = "inputting"
        while True:
            if not user_queue.empty():
                input_value = user_queue.get()
                chat_status = "Chat ongoing"
                print("input message: ", input_value)
                return input_value

            if time.time() - start_time > 600:  
                chat_status = "ended"
                return "exit"

            await asyncio.sleep(1) 

def print_messages(recipient, messages, sender, config):
    print(f"Messages from: {sender.name} sent to: {recipient.name} | num messages: {len(messages)} | message: {messages[-1]}")

    content = messages[-1]['content']

    if all(key in messages[-1] for key in ['name']):
        print_queue.put({'user': messages[-1]['name'], 'message': content})
    elif messages[-1]['role'] == 'user':
        print_queue.put({'user': sender.name, 'message': content})
    else:
        print_queue.put({'user': recipient.name, 'message': content})

    return False, None #conversation continued  
         
async def initiate_chat(agent, recipient, message):
    result = await agent.a_initiate_chat(recipient, message=message, clear_history=False)
    print(result)

    return result
def run_chat(request_json):
    global chat_status
    manager = None
    assistants = []
    try:
        # a) Data structure for the request
        user_input = request_json.get('message')
        agents_info = request_json.get('agents_info') 
        task_info = request_json.get('task_info')
        # b) UserProxy creation
        userproxy = create_userproxy()
        # c) Chat creation
        manager, assistants = create_groupchat(agents_info, task_info, userproxy) 
        # d) Chat start
        asyncio.run(initiate_chat(userproxy, manager, user_input))

        chat_status = "ended"

    except Exception as e:
        chat_status = "error"
        print_queue.put({'user': "System", 'message': f"An error occurred: {str(e)}"})

def create_userproxy():
    user_proxy = MyConversableAgent(
        name="User_Proxy",
        code_execution_config=False,
        is_termination_msg=lambda msg: "TERMINATE" in msg["content"],
        human_input_mode="ALWAYS",
    )
    user_proxy.register_reply(
        [autogen.Agent, None],
        reply_func=print_messages, 
        config={"callback": None},
    )
    return user_proxy

agent_classes = {
    'GPTAssistantAgent': GPTAssistantAgent,
    'AssistantAgent': AssistantAgent,
    #add more type of agents...
}

def create_groupchat(agents_info, task_info, user_proxy):   
    assistants = []

    for agent_info in agents_info:
        if agent_info["type"] == "UserProxyAgent":
            continue

        llm_config = {
            "config_list": [agent_info["llm"]],
            "temperature": 0,
        }

        AgentClass = agent_classes[agent_info["type"]]
        assistant = AgentClass(
            name=agent_info["name"],                           
            llm_config=llm_config,
            system_message=agent_info["system_message"],
            description=agent_info["description"],
        )

        assistant.register_reply(
            [autogen.Agent, None],
            reply_func=print_messages, 
            config={"callback": None},
        ) 
        assistants.append(assistant)

    if len(assistants) == 1: 
        manager = assistants[0]

    elif len(assistants) > 1: 
        groupchat = autogen.GroupChat(
            agents=[user_proxy] + assistants, 
            messages=[], 
            max_round=task_info["maxMessages"],
            speaker_selection_method=task_info["speakSelMode"]
        )
        manager = autogen.GroupChatManager(
            groupchat=groupchat, 
            llm_config=llm_config, 
            system_message="",
        )

    return manager, assistants

@app.route('/api/start_chat', methods=['POST', 'OPTIONS']) 
def start_chat():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    elif request.method == 'POST':
        global chat_status
        try:

            if chat_status == 'error':
                chat_status = 'ended' 

            with print_queue.mutex:
                print_queue.queue.clear()
            with user_queue.mutex:
                user_queue.queue.clear()

            chat_status = 'Chat ongoing'

            thread = threading.Thread(
                target=run_chat, 
                args=(request.json,)
            )
            thread.start()
    
            return jsonify({'status': chat_status})
        except Exception as e:
            return jsonify({'status': 'Error occurred', 'error': str(e)})
        
@app.route('/api/send_message', methods=['POST'])
def send_message():
    user_input = request.json['message']
    user_queue.put(user_input)
    return jsonify({'status': 'Message Received'})

@app.route('/api/get_message', methods=['GET'])
def get_messages():
    global chat_status 

    if not print_queue.empty():
        msg = print_queue.get()  
        return jsonify({'message': msg, 'chat_status': chat_status}), 200
    else:
        return jsonify({'message': None, 'chat_status': chat_status}), 200
    

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5008, debug=True)