from langchain import hub
from langchain.chat_models import ChatOpenAI
import os

def document_qa_function(question):
    return "$24B"

def tweet_generator(message):
    answer = f"Tesla's Q2 revenue in 2023 was {message}. #Tesla #2023"
    return answer

prompt = hub.pull("homanp/superagent")

os.environ["OPENAI_API_KEY"] = "Your_OpenAI_Key"
model = ChatOpenAI(model="gpt-3.5-turbo-0301")

runnable = prompt | model
output = runnable.invoke({
         "tools": """Tools:
                  [{
                    "name": "Tesla Q2 2023 earnings",
                    "description": "useful for answering questions about Teslas Q2 2023 earnings report",
                    "function": "document_qa_function",
                    "input_schema" : {
                      "question": <str>
                    },
                    "output_schema": {
                      "answer": <str>,
                    }
                  }, {
                    "name": "Tweet generator",
                    "description": "useful for generating tweets",
                    "function": "tweeet_generator",
                    "input_schema" : {
                      "message": <str>
                    },
                    "output_schema": {
                    "tweet": <str>
                    }
                  }]""",
         "output_format": """{
                              "workflow": "Generate Prompt and Replicate Image",
                              "steps": [
                                {
                                  "name": "Tool name 1",
                                  "function": "function_runner_1",
                                  "input_schema": {
                                    "query": str
                                  },
                                  "ouput_key": "result_1"
                                },
                                {
                                  "name": "Function 2",
                                  "function": "function_runner_2",
                                  "input_schema": {
                                    "input": "{result_1}"
                                  },
                                  "output_key": "result_2"
                                }
                              ]
                            }""",
          "input": "Write a tweet about the Q2 revenue"
})
import ast

data_dict = ast.literal_eval(output.content)

#call document_qa_function()
doc_qa_step = data_dict['steps'][0]
function_name = doc_qa_step['function']
arguments = doc_qa_step['input_schema']
function = globals()[function_name]
result = function(**arguments)

#call tweet_generator()
tweet_step = data_dict['steps'][1]
function_name = tweet_step['function']
arguments = {"message": result}
function = globals()[function_name]
result = function(**arguments)

print("New Tweet: ", result)
