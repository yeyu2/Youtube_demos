from langchain.chat_models import ChatOpenAI, ChatFireworks
from langchain.prompts import ChatPromptTemplate, FewShotChatMessagePromptTemplate
from langchain.schema.output_parser import StrOutputParser
from langchain.output_parsers import CommaSeparatedListOutputParser
from langchain.schema.runnable import RunnableLambda
from langchain.utilities import DuckDuckGoSearchAPIWrapper

import os
import time
import chainlit as cl

os.environ["OPENAI_API_KEY"] = "Your_OpenAI_API_Key"

os.environ["FIREWORKS_API_KEY"] = "Your_Fireworks_API_Key"

chat_fw = ChatFireworks(model="accounts/fireworks/models/llama-v2-70b-chat", temperature=0)
chat_oa = ChatOpenAI(temperature=0)

# Few Shot Examples
examples = [
    {
        "input": "Could the members of The Police perform lawful arrests?",
        "output": "What can the members of The Police do?, What is lawful arrests?"
    },
    {
        "input": "Jan Sindel’s was born in what country?", 
        "output": "what is Jan Sindel’s personal history?, What are the common countries?"
    },
    {
        "input": "Who is taller, Yao Ming or Shaq?", 
        "output": "what is the height of Yao Ming?, What is the height of Shaq?"
    },
]
# We now transform these to example messages
example_prompt = ChatPromptTemplate.from_messages(
    [
        ("human", "{input}"),
        ("ai", "{output}"),
    ]
)
few_shot_prompt = FewShotChatMessagePromptTemplate(
    example_prompt=example_prompt,
    examples=examples,
)
prompt = ChatPromptTemplate.from_messages([
    ("system", """You are an expert at world knowledge. 
              Your task is to step back and abstract the original question 
              to some more generic step-back questions, 
              which are easier to answer. Here are a few examples:"""),
    few_shot_prompt,
    ("user", "{question}"),
])

question_gen_chain = prompt | chat_oa | CommaSeparatedListOutputParser()

'''
question = """If you have 3 moles of nitrogen and 4 moles of hydrogen 
              to produce ammonia, which one will get exhausted first 
              assuming a complete reaction?"""
question_list = question_gen_chain.invoke({"question": question})
print("Question List: ", question_list)
'''
search = DuckDuckGoSearchAPIWrapper(max_results=4)

def retriever_list(query):
    answer = ''
    ques = ''
    for question in query:
        ques += question
        ques += '/'
        if question[-1] == '?':
            ans = search.run(ques)
            ques = ''
            answer += ans
            time.sleep(2)
    print("Answer: ", answer)
    return answer

response_prompt_template = """You are an expert of world knowledge. 
I am going to ask you a question. Your response should be concise 
and referring to the following context if they are relevant. 
If they are not relevant, ignore them.

{step_back_context}
Original Question: {question}
Answer:"""
response_prompt = ChatPromptTemplate.from_template(response_prompt_template)
@cl.on_chat_start
def main():
    chain = {

        "step_back_context": question_gen_chain | retriever_list,
        "question": lambda x: x["question"]
    } | response_prompt | chat_fw | StrOutputParser()

    def retriever(query):
        return search.run(query)

    chain_nostep = {
    
            "step_back_context": RunnableLambda(lambda x: x['question']) | retriever,
            "question": lambda x: x["question"]
        } | response_prompt | chat_fw | StrOutputParser()
    
    cl.user_session.set("chain", chain)
    cl.user_session.set("chain_nostep", chain_nostep)

@cl.on_message
async def main(message: cl.Message):
    chain = cl.user_session.get("chain") 
    chain_nostep = cl.user_session.get("chain_nostep")

    response = await chain.ainvoke({"question": message.content})
    await cl.Message(content="[Step-Back Prompting]\n"+response).send()

    response_nostep = await chain_nostep.ainvoke({"question": message.content})
    await cl.Message(content="[Normal Prompting]\n"+response_nostep).send()
    