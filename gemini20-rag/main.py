##
## pip install -u google-genai==0.5.0 llama-index==0.12.11 llama-index-llms-gemini==0.4.3 llama-index-embeddings-gemini==0.3.1 websockets
##
import asyncio
import json
import os
import websockets
from google import genai
import base64

from llama_index.core import (
    VectorStoreIndex,
    SimpleDirectoryReader,
    StorageContext,
    load_index_from_storage,
    Settings,
)

from llama_index.embeddings.gemini import GeminiEmbedding
from llama_index.llms.gemini import Gemini
     
# Load API key from environment
os.environ['GOOGLE_API_KEY'] = ''
gemini_api_key = os.environ['GOOGLE_API_KEY']
MODEL = "gemini-2.0-flash-exp"  # use your model ID

text_embedding_model = "text-embedding-004"

client = genai.Client(
  http_options={
    'api_version': 'v1alpha',
  }
)

gemini_embedding_model = GeminiEmbedding(api_key=gemini_api_key, model_name="models/text-embedding-004")

llm = Gemini(api_key=gemini_api_key, model_name="models/gemini-2.0-flash-exp")
     
   
def build_index(doc_path="./downloads"):
    # check if storage already exists
    Settings.llm = llm
    Settings.embed_model = gemini_embedding_model
    PERSIST_DIR = "./storage"
    if not os.path.exists(PERSIST_DIR):
        # load the documents and create the index
        documents = SimpleDirectoryReader(doc_path).load_data()
        
        index = VectorStoreIndex.from_documents(documents)
        # store it for later
        index.storage_context.persist(persist_dir=PERSIST_DIR)
    else:
        # load the existing index
        storage_context = StorageContext.from_defaults(persist_dir=PERSIST_DIR)
        index = load_index_from_storage(storage_context)
    return index


def query_docs(query):
    index = build_index()
    query_engine = index.as_query_engine()
    response = query_engine.query(query)
    
    # Convert the response to a string
    response_text = str(response)
    print(f"RAG response: {response_text}")
    return response_text

# Define the tool (function)
tool_query_docs = {
    "function_declarations": [
        {
            "name": "query_docs",
            "description": "Query the document content with a specific query string.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "query": {
                        "type": "STRING",
                        "description": "The query string to search the document index."
                    }
                },
                "required": ["query"]
            }
        }
    ]
}

async def gemini_session_handler(client_websocket: websockets.WebSocketServerProtocol):
    """Handles the interaction with Gemini API within a websocket session."""
    try:
        config_message = await client_websocket.recv()
        config_data = json.loads(config_message)
        #config = LiveConnectConfig(response_modalities=["AUDIO"])
        config = config_data.get("setup", {})
        config["system_instruction"] = """You are a helpful assistant and you MUST always use the query_docs tool to query the document 
        towards any questions. It is mandatory to base your answers on the information from the output of the query_docs tool, 
        and include the context from the query tool in your response to the user's question.
        Do not mention your operations like "I am searching the document now".
        """

        config["tools"] = [tool_query_docs]

        async with client.aio.live.connect(model=MODEL, config=config) as session:
            print("Connected to Gemini API")

            async def send_to_gemini():
                """Sends messages from the client websocket to the Gemini API."""
                try:
                    async for message in client_websocket:
                        try:
                            data = json.loads(message)
                            if "realtime_input" in data:
                                for chunk in data["realtime_input"]["media_chunks"]:
                                    if chunk["mime_type"] == "audio/pcm":
                                        await session.send(input={
                                            "mime_type": "audio/pcm",
                                            "data": chunk["data"]
                                        })
                                    elif chunk["mime_type"] == "application/pdf":
                                        # Save PDF file to downloads directory
                                        pdf_data = base64.b64decode(chunk["data"])
                                        filename = chunk.get("filename", "uploaded.pdf")
                                        
                                        # Create downloads directory if it doesn't exist
                                        os.makedirs("./downloads", exist_ok=True)
                                        
                                        # Save the PDF file
                                        file_path = os.path.join("./downloads", filename)
                                        with open(file_path, "wb") as f:
                                            f.write(pdf_data)
                                        
                                        print(f"Saved PDF file to {file_path}")
                                        
                                        # Rebuild the index with the new PDF
                                        if os.path.exists("./storage"):
                                            import shutil
                                            shutil.rmtree("./storage")
                                        build_index()
                                        
                                        await client_websocket.send(json.dumps({
                                            "text": f"PDF file {filename} has been uploaded and indexed successfully."
                                        }))
                                        
                        except Exception as e:
                            print(f"Error sending to Gemini: {e}")
                    print("Client connection closed (send)")
                except Exception as e:
                    print(f"Error sending to Gemini: {e}")
                finally:
                    print("send_to_gemini closed")



            async def receive_from_gemini():
                """Receives responses from the Gemini API and forwards them to the client, looping until turn is complete."""
                try:
                    while True:
                        try:
                            print("receiving from gemini")
                            async for response in session.receive():
                                #first_response = True
                                #print(f"response: {response}")
                                if response.server_content is None:
                                    if response.tool_call is not None:
                                          #handle the tool call
                                           print(f"Tool call received: {response.tool_call}")

                                           function_calls = response.tool_call.function_calls
                                           function_responses = []

                                           for function_call in function_calls:
                                                 name = function_call.name
                                                 args = function_call.args
                                                 # Extract the numeric part from Gemini's function call ID
                                                 call_id = function_call.id

                                                 # Validate function name
                                                 if name == "query_docs":
                                                      try:
                                                          result = query_docs(args["query"])
                                                          function_responses.append(
                                                             {
                                                                 "name": name,
                                                                 "response": {"result": result},
                                                                 "id": call_id  
                                                             }
                                                          ) 
                                                          await client_websocket.send(json.dumps({"text": json.dumps(function_responses)}))
                                                          print("Function executed")
                                                      except Exception as e:
                                                          print(f"Error executing function: {e}")
                                                          continue


                                           # Send function response back to Gemini
                                           print(f"function_responses: {function_responses}")
                                           await session.send(input=function_responses)
                                           continue

                                    #print(f'Unhandled server message! - {response}')
                                    #continue

                                model_turn = response.server_content.model_turn
                                if model_turn:
                                    for part in model_turn.parts:
                                        #print(f"part: {part}")
                                        if hasattr(part, 'text') and part.text is not None:
                                            #print(f"text: {part.text}")
                                            await client_websocket.send(json.dumps({"text": part.text}))
                                        elif hasattr(part, 'inline_data') and part.inline_data is not None:
                                            # if first_response:
                                            #print("audio mime_type:", part.inline_data.mime_type)
                                                #first_response = False
                                            base64_audio = base64.b64encode(part.inline_data.data).decode('utf-8')
                                            await client_websocket.send(json.dumps({
                                                "audio": base64_audio,
                                            }))
                                            print("audio received")

                                if response.server_content.turn_complete:
                                    print('\n<Turn complete>')
                        except websockets.exceptions.ConnectionClosedOK:
                            print("Client connection closed normally (receive)")
                            break  # Exit the loop if the connection is closed
                        except Exception as e:
                            print(f"Error receiving from Gemini: {e}")
                            break # exit the lo

                except Exception as e:
                      print(f"Error receiving from Gemini: {e}")
                finally:
                      print("Gemini connection closed (receive)")


            # Start send loop
            send_task = asyncio.create_task(send_to_gemini())
            # Launch receive loop as a background task
            receive_task = asyncio.create_task(receive_from_gemini())
            await asyncio.gather(send_task, receive_task)



    except Exception as e:
        print(f"Error in Gemini session: {e}")
    finally:
        print("Gemini session closed.")


async def main() -> None:
    async with websockets.serve(gemini_session_handler, "localhost", 9084):
        print("Running websocket server localhost:9084...")
        await asyncio.Future()  # Keep the server running indefinitely


if __name__ == "__main__":
    asyncio.run(main())