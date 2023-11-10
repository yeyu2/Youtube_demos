import time
import openai
from openai import OpenAI
import os

client = OpenAI()
file = client.files.create(
  file=open("zephyr.pdf", "rb"),
  purpose='assistants'
)
time.sleep(60)

assistant = client.beta.assistants.create(
  instructions="You are a paper research chatbot. Use your knowledge base to best respond to customer queries.",
  model="gpt-4-1106-preview",
  tools=[{"type": "retrieval"}]
)

thread = client.beta.threads.create()
message = client.beta.threads.messages.create(
  thread_id=thread.id,
  role="user",
  content="What training methods make the Zephyr-7b model better than others?",
  file_ids=[file.id]
)

run = client.beta.threads.runs.create(

    thread_id=thread.id,
    assistant_id=assistant.id,
    instructions="Please address the user as Yeyu."
)

while run.status != "completed":
    run = client.beta.threads.runs.retrieve(
      thread_id=thread.id,
      run_id=run.id
    )
    time.sleep(5)
print(run)
messages = client.beta.threads.messages.list(
  thread_id=thread.id
)

print("\nResponse:", messages.data[0].content[0].text.value)
print(messages)

run_steps = client.beta.threads.runs.steps.list(
    thread_id=thread.id,
    run_id=run.id
)

for step in run_steps.data:
    if step.type == "tool_calls":
        print(step.step_details.tool_calls)
