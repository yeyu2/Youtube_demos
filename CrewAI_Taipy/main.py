import os
from dotenv import load_dotenv
from taipy.gui import Gui, State, notify, get_state_id, invoke_callback, Icon
from crewai.agents.agent_builder.base_agent_executor_mixin import CrewAgentExecutorMixin
from crewai_taipy.crew import CrewaiTaipy, register_output_handler
import time
import threading
from typing import List

load_dotenv()

# Initialize users for chat
users: List[List[str | Icon]] = [
    ["Human", Icon("images/human_icon.png", "Human")],
    ["Researcher", Icon("images/researcher_icon.png", "Researcher")],
    ["Reporting Analyst", Icon("images/analyst_icon.png", "Analyst")],
    ["System", Icon("images/system_icon.png", "System")]
]

# Initialize global variables
conversation = [
    ["1", "Welcome! I'm your AI Research Assistant. What topic would you like me to research?", "System"]
]

def on_init(state: State) -> None:
    """Initialize the conversation"""
    state.conversation = conversation.copy()

def update_conversation(state: State, sender: str, message: str):
    """Helper function to update conversation state with markdown conversion"""
    global conversation
    conversation += [[
        f"{len(conversation) + 1}",
        message,
        sender
    ]]
    state.conversation = conversation

def create_output_handler(state_id: str):
    return lambda output: invoke_callback(gui, state_id, lambda state: update_conversation(state, output.agent, output.raw))

crew_started = False
def initiate_crew(state_id: str, message: str):
    """Handles the CrewAI research process"""
    global crew_started
    
    try:
        register_output_handler(create_output_handler(state_id))
        
        inputs = {"topic": message}
        crew = CrewaiTaipy().crew()
        result = crew.kickoff(inputs=inputs)
        
    except Exception as e:
        def show_error(state: State):
            update_conversation(state, "System", f"An error occurred: {e}")
        invoke_callback(gui, state_id, show_error)
    
    crew_started = False

user_input = None
current_state_id = None

def custom_ask_human_input(self, final_answer: dict) -> str:
    global user_input, current_state_id
    
    def update(state: State):
        update_conversation(state, "System", final_answer)
        update_conversation(state, "System", "Please provide feedback on the Final Result and the Agent's actions: ")
    
    invoke_callback(gui, current_state_id, update)
    
    while user_input is None:
        time.sleep(1)
    
    feedback = user_input
    user_input = None
    return feedback

CrewAgentExecutorMixin._ask_human_input = custom_ask_human_input

def send_message(state: State, var_name: str, payload: dict = None) -> None:
    """Handles message sending and CrewAI initialization"""
    global crew_started, user_input, current_state_id
    
    if payload:
        args = payload.get("args", [])
        message = args[2]
        sender = args[3]
        
        if not crew_started:
            current_state_id = get_state_id(state)
            update_conversation(state, sender, message)
            
            # Start CrewAI process
            crew_started = True
            thread = threading.Thread(
                target=initiate_crew, 
                args=[current_state_id, message],
                daemon=True
            )
            thread.start()
            
        elif crew_started:
            # Handle human feedback during CrewAI process
            user_input = message
            update_conversation(state, sender, message)

# Taipy page with chat component
page = """
<|{conversation}|chat|users={users}|on_action=send_message|sender_id=Human|show_sender=True|mode=markdown|>
"""

# Initialize Taipy GUI
gui = Gui(page)

if __name__ == "__main__":

    gui.run(dark_mode=True, title="CrewAI Research Assistant")
