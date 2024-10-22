import panel as pn
from swarm import Swarm, Agent, Result
import random
import os
os.environ["OPENAI_API_KEY"] = "sk-your-openai-api-key" # Replace with your key

client = Swarm()

def get_product_info(product_id):
    # Simulated product database
    products = {
        "1": "Smartphone iPhone 16",
        "2": "Laptop MacBook Pro",
        "3": "Wireless Earbuds AirPods"
    }
    return products.get(product_id, "Product not found")

def get_order_status(order_id):
    # Simulated order statuses
    statuses = ["Processing", "Shipped", "Delivered", "Cancelled"]
    return random.choice(statuses)

def process_refund(order_id):
    # Simulated refund process
    success = random.choice([True, False])
    return "Refund processed successfully" if success else "Refund processing failed"

context_variables = {
    'customer_name': None,  # Initialize customer name to None
    'last_order_id': None,
}
def triage_agent_instructions(context_variables):
    return f"""
    Triage agent for e-commerce support. Direct inquiries:
    - Product info: Product Information Agent
    - Order status: Order Status Agent
    - Returns/refunds: Returns and Refunds Agent
    Greet and clarify if needed.
    Customer: {context_variables.get('customer_name', 'Unknown')}
    """

def product_info_agent_instructions(context_variables):
    return f"""
    Product Information Agent. Provide product details using get_product_info.
    Be helpful, informative, suggest related products.
    Customer: {context_variables.get('customer_name', 'Unknown')}
    """

def order_status_agent_instructions(context_variables):
    return f"""
    Order Status Agent. Track orders with get_order_status.
    Explain statuses and delivery times.
    Customer: {context_variables.get('customer_name', 'Unknown')}
    Order ID: {context_variables.get('last_order_id', 'Unknown')}
    """

def returns_refunds_agent_instructions(context_variables):
    return f"""
    Returns and Refunds Agent. Process refunds with process_refund.
    Explain policy, guide through process.
    Customer: {context_variables.get('customer_name', 'Unknown')}
    Order ID: {context_variables.get('last_order_id', 'Unknown')}
    """

def transfer_to_product_info(context_variables):
    return Result(agent=product_info_agent, context_variables=context_variables)

def transfer_to_order_status(context_variables):
    return Result(agent=order_status_agent, context_variables=context_variables)

def transfer_to_returns_refunds(context_variables):
    return Result(agent=returns_refunds_agent, context_variables=context_variables)

triage_agent = Agent(
    name="Triage Agent",
    instructions=triage_agent_instructions,
    functions=[transfer_to_product_info, transfer_to_order_status, transfer_to_returns_refunds]
)

product_info_agent = Agent(
    name="Product Information Agent",
    instructions=product_info_agent_instructions,
    functions=[get_product_info]
)

order_status_agent = Agent(
    name="Order Status Agent",
    instructions=order_status_agent_instructions,
    functions=[get_order_status]
)

returns_refunds_agent = Agent(
    name="Returns and Refunds Agent",
    instructions=returns_refunds_agent_instructions,
    functions=[process_refund]
)

pn.extension(design="material")

chat_interface = pn.chat.ChatInterface()
chat_interface.send("Welcome to our customer support system! Please enter your name:", user="System", respond=False)

current_agent = triage_agent
messages = []
def process_user_message(contents: str, user: str, instance: pn.chat.ChatInterface):
    global current_agent
    global context_variables
    global messages

    if context_variables['customer_name'] is None:
        context_variables['customer_name'] = contents
        chat_interface.send(f"Hello, {contents}! How can I help you today?", user=current_agent.name, avatar="🤖", respond=False)
    else:
        messages.append({"role": "user", "content": contents})

        response = client.run(
            agent=current_agent,
            messages=messages,
            context_variables=context_variables
        )

        for message in response.messages:
            if message['role'] == 'assistant':
                if message['tool_calls']:
                    for tool_call in message['tool_calls']:
                        tool_name = tool_call['function']['name']
                        chat_interface.send(f"Using tool: {tool_name}", user=message['sender'], avatar="🤖", respond=False)
                elif message['content']:
                    chat_interface.send(message['content'], user=message['sender'], avatar="🤖", respond=False)

        messages = response.messages
        current_agent = response.agent
        context_variables = response.context_variables

        if "order" in contents.lower():
            context_variables['last_order_id'] = f"ORD-{random.randint(1000, 9999)}"

chat_interface.callback = process_user_message

chat_interface.servable()